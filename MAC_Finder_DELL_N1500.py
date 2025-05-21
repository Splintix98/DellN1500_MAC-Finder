import paramiko
import time
import getpass
import sys
import re


############# V2 #############
#
# Added option to also output the port configuration for the found port which includes VLANs
#
##############################


############ TODO ############
#
# - add the functionality to enter multiple MAC addresses simultaneously to let the script search the switches for those all at once
#     - output a summary after the search has finished
#
##############################



# This function is not really in use, it was just a test to get very long outputs to work
# The dell switches truncate output as soon as it gets too long and then you'll have to press enter (possibly multiple times)
#   to get all of the output.
# This function implements this enter-pressing exemplary using the "show mac address-table"-command which results in a very long
#   output showing all mac-addresses known to the switch from the complete network.
# While collecting the output, a loading indicator is being shown to the user.
def ssh_test(ip, username, password):
    try:
        ssh_client = paramiko.SSHClient()
        ssh_client.load_system_host_keys()
        ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh_client.connect(ip, port=22, username=username, password=password)
        time.sleep(1)
        
        channel = ssh_client.invoke_shell()
        channel.send("enable\n")
        time.sleep(1)
        while not channel.recv_ready():
            pass
        channel.recv(1024)

        channel.send("show mac address-table\n")
        time.sleep(1)
        output = ""
        time_in_millis = round(time.time() * 1000)
        while True:
            # Read the complete response from the channel
            output_t = ""
            while True:
                if channel.recv_ready():
                    output_t += channel.recv(1024).decode('utf-8')
                else:
                    break
            
            # print(f"Output so far: {output_t}")
            output = output + output_t

            # check if there is more output available for the given command
            if not "--More--" in output_t:
                break

            # print a dot every second so that the user knows the program is still running
            temp_time = round(time.time() * 1000)
            if temp_time - time_in_millis > 1000: 
                sys.stdout.write('.')
                sys.stdout.flush()
                time_in_millis = temp_time
                
            
            # get the rest of the output
            channel.send("\n")
            time.sleep(0.1)
        
        print(f"\nReceived output: {output}")
        
        ssh_client.close()
        return output, None

    except Exception as e:
        return str(e), None
    

# connect to the switch via SSH and the previously specified username and password
# execute the command
# get all the output
# return the output
def exec_ssh_command(command, switch_IP, username, password):
    try:
        ssh_client = paramiko.SSHClient()
        ssh_client.load_system_host_keys()
        ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh_client.connect(switch_IP, port=22, username=username, password=password)
        time.sleep(1)
        # print("Connection established")

        channel = ssh_client.invoke_shell()
        channel.send("enable\n")
        time.sleep(1)
        while not channel.recv_ready():
            pass
        channel.recv(1024)
        # print("Enabled")

        # print(f"command: {command}")
        channel.send(command)
        time.sleep(1)
        # Read the complete response from the channel
        output = ""
        while True:
            if channel.recv_ready():
                output += channel.recv(1024).decode('utf-8')
            else:
                break
        # print(f"Received output: {output}")

        ssh_client.close()
        return output, None
    
    except Exception as e:
        return str(e), None
   

# the Dell Switches need MAC addresses in a specific format (XXXX.XXXX.XXXX) where X can be a digit or an uppercase letter from the range A-F (hex)
# this function brings the MAC address that the user entered into the correct format for further processing
def format_mac_address(mac):
    # Remove all non-hexadecimal characters
    mac = ''.join(c for c in mac if c.isalnum())
    
    mac = mac.upper()

    # Format the MAC address in xxxx.xxxx.xxxx format
    if len(mac) == 12:
        formatted_mac = f"{mac[:4]}.{mac[4:8]}.{mac[8:]}"
        return formatted_mac
    else:
        print("The provided MAC address is not in the correct format.")
        return None
    

# get port ("Gi1/0/32") based on regex pattern
def get_port_from_output(output):
    port_regex_pattern = r"\bGi\d+/\d+/\d+\b"  # supports stacks where the port might be "Gi2/0/xx"
    match = re.search(port_regex_pattern, output)
    if match:
        port = match.group(0)
        print(f"Port found using regex pattern: {port}")
        return port
    else:
        print("No port found in output.")
        return
    

# asks for the mac address to search for from the user
# brings the received mac address in the correct format
# checks switches one by one
# if mac is found on current switch:
#   print the output containing the port and vlan
#   ask user whether he wants to also see the port configuration
#   ask user whether the other switches should be searched for the mac regardless of the hit
# ask whether to search again
# if mac wasn't found, print the list of switches that were searched
def check_switches(switch_IPs, password):
    mac = input("Please enter the MAC-address to find: ")
    device_found = False
        
    # just for test purposes
    if mac == "test":
        print("192.168.23.31 will now be queried for its MAC-address-table. This can take some time!")
        ssh_test(switch_IPs[0], username, password)
        answer = input("\nSearch again? [y|n] ")
        if answer.lower() == "y" or answer.lower() == "yes":
            print("--------------------------------------------------")
            return 1
        else: quit()
    
    mac = format_mac_address(mac)
    print(f"Formatted MAC: {mac}")

    switches_checked = []
    for ip in switch_IPs:
        print(f"Checking switch {ip}...")
        switches_checked.append(ip)
        command = "show mac address-table address " + mac + "\n"
        output, error = exec_ssh_command(command, ip, username, password)

        if error:
            print(f"Error when testing {ip}: ", error)
        else:
            # MAC is connected to the current switch
            # First I had the script react to "Forwarding Database Empty" and "Po1" being in the output in separate ways but I found it to be unreliable
            #   When I got "Forwarding Database Empty" I assumed the device is not present in the network at all
            #   When I got "Po1" I assumed the device is present somewhere, just not on the currently searched switch
            #   Now I simply search all switches until I find the device
            if not ("Forwarding Database Empty" in output or "Po1" in output or "Te1/" in output):
                print(f"\n{mac} was found on switch {ip}, see full output:\n{output}")  # exemplary output shown at the very bottom
                device_found = True

                answer = input("\nDo you want to see the interface configuration for that port? [y|n] ")
                if answer.lower() == "y" or answer.lower() == "yes":
                    port = get_port_from_output(output) # "Gi1/0/32"
                    command = "show interfaces switchport " + port + "\n"
                    output, error = exec_ssh_command(command, ip, username, password)
                    if error:
                        print(f"Error when asking for port config of switch {ip}: ", error)
                    else:
                        print(output)  # exemplary output shown at the very bottom                        

                if ip != switch_IPs[-1]:
                    answer = input("\nContinue the search? [y|n] ")
                    if answer.lower() == "y" or answer.lower() == "yes":
                        continue

                answer = input("\nSearch again? [y|n] ")
                if answer.lower() == "y" or answer.lower() == "yes":
                    print("--------------------------------------------------")
                    return 1
                else: quit()
                
            # user can add "debug" to the call of the script and then every output of the switch gets printed to the console regardless of whether the device is found or not
            elif "debug" in sys.argv:
                print(f"Output for switch {ip}:\n{output}")
    
    if not device_found: print(f"\n{mac} was not found in the network. \nChecked these switches: {switches_checked}")
    answer = input("\nSearch again? [y|n] ")
    if answer.lower() == "y" or answer.lower() == "yes":
        print("--------------------------------------------------")
        return 1
    else: quit()


if __name__ == "__main__":
    # define your switches that you want to be checked here as a string array
    # die .41 ist der zweite Switch im Dispo-Stack und muss nicht separat geprüft werden!
    switch_IPs = ["192.168.23.31", "192.168.23.32", "192.168.23.33", "192.168.23.34", "192.168.23.35", "192.168.23.38", "192.168.23.39", "192.168.23.40", "192.168.23.42", "192.168.23.43", "192.168.23.44"]
    port = 22  # Default SSH port
    username = "admin"

    # get password once from user and store encrypted for runtime
    password = getpass.getpass(prompt='Enter SSH password for switches: ')

    while True:
        check_switches(switch_IPs, password)



"""
EXEMPLARY OUTPUT:
show interfaces switchport Gi1/0/32

Port: Gi1/0/32
VLAN Membership Mode: General Mode
Member of VLANs : (1722),1010,1030
Access Mode VLAN: 1 (default)
General Mode PVID: 1722
General Mode Ingress Filtering: Enabled
General Mode Acceptable Frame Type: Admit All
General Mode Dynamically Added VLANs:
General Mode Untagged VLANs: 1722
General Mode Tagged VLANs: 1010,1030
General Mode Forbidden VLANs:
Trunking Mode Native VLAN: 1 (default)
Trunking Mode Native VLAN Tagging: Disabled
Trunking Mode VLANs Enabled: All
Private VLAN Host Association: none
Private VLAN Mapping:
Private VLAN Operational Bindings:
Default Priority: 0
Protected: Disabled


dell-n1548p-3#
"""



"""
OUTPUT WHEN MAC IS DIRECTLY CONNECTED TO SWITCH:
--------------------
dell-n1548p-1#show mac address-table address 0000.0000.0000

Aging time is 300 Sec

Vlan     Mac Address           Type        Port
-------- --------------------- ----------- ---------------------
1010     0000.0000.0000        Dynamic     Gi1/0/8


--------------------



OUTPUT WHEN MAC IS NOT DIRECTLY CONNECTED TO THIS SWITCH BUT APPARENTLY KNOWN IN THE NETWORK:
--------------------
dell-n1548p-1#show mac address-table address 0000.0000.0000

Aging time is 300 Sec

Vlan     Mac Address           Type        Port
-------- --------------------- ----------- ---------------------
1        0000.0000.0000        Dynamic     Po1


--------------------



OUTPUT WHEN MAC IS NOT KNOWN TO THE NETWORK ACCORDING TO THIS SWITCH:
--------------------
dell-n1548p-1#show mac address-table address 0000.0000.0000

Aging time is 300 Sec

Vlan     Mac Address           Type        Port
-------- --------------------- ----------- ---------------------

Forwarding Database Empty.

--------------------
"""
