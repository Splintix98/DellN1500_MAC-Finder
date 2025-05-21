import paramiko
import time
import getpass
import sys
import re


############ TODO ############
#
# - add the functionality to enter multiple MAC addresses simultaneously to let the script search the switches for those all at once
#     - output a summary after the search has finished
#
##############################


############ Known Switch Commands ############
# (these are not neccessarily used in this program)
#
# show interfaces switchport Gi1/0/11
# configure terminal
#   interface Gi1/0/11
#       switchport mode general
#       switchport general allowed vlan add 1722 untagged
#       switchport general pvid 1030
# show mac address-table
# show vlan
#
###############################################


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
        # Clear initial banner/prompt
        time.sleep(0.5) # Wait for shell to be ready
        while channel.recv_ready():
            channel.recv(1024)

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
            output_t = ""
            # Read available data without blocking indefinitely
            start_time = time.time()
            while time.time() - start_time < 1.0: # Try to read for up to 1 second
                if channel.recv_ready():
                    output_t += channel.recv(1024).decode('utf-8', errors='ignore')
                else:
                    time.sleep(0.05) # Brief pause if no data
                # Break if prompt-like pattern appears at end of output_t, or if --More--
                if "--More--" in output_t or (output_t.strip().endswith("#") and len(output_t.strip()) > 1) :
                    break

            output = output + output_t

            # check if there is more output available for the given command
            if not "--More--" in output_t:
                # Check again if there's really no more, sometimes prompt is delayed
                if not channel.recv_ready():
                    time.sleep(0.2)
                    if not channel.recv_ready():
                        break
                # if still data, continue loop
                if channel.recv_ready():
                    continue
                break

            # print a dot every second so that the user knows the program is still running
            temp_time = round(time.time() * 1000)
            if temp_time - time_in_millis > 1000: 
                sys.stdout.write('.')
                sys.stdout.flush()
                time_in_millis = temp_time
                
            # get the rest of the output
            channel.send(" ") # Send space for --More--
            time.sleep(0.2) # Give switch time to send next page

        if sys.stdout.isatty() and '.' in output: sys.stdout.write('\n')
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
        # Increased timeout for connect
        ssh_client.connect(switch_IP, port=22, username=username, password=password, timeout=20, banner_timeout=20)

        channel = ssh_client.invoke_shell(width=200, height=1000) # Set large term size

        # Wait for initial prompt and clear buffer
        output_buffer = ""
        time.sleep(1) # Wait for shell to be ready
        while channel.recv_ready():
            output_buffer += channel.recv(4096).decode('utf-8', errors='ignore')
        # print(f"DEBUG: Initial buffer from {switch_IP}: {output_buffer}")

        channel.send("enable\n")
        time.sleep(0.5)
        enable_output_buffer = ""
        while channel.recv_ready(): # Clear enable output
            enable_output_buffer += channel.recv(4096).decode('utf-8', errors='ignore')
        # print(f"DEBUG: Enable output from {switch_IP}: {enable_output_buffer}")


        channel.send("terminal length 0\n") # Disable pagination
        time.sleep(0.5)
        term_len_buffer = ""
        while channel.recv_ready(): # Clear terminal length output
            term_len_buffer += channel.recv(4096).decode('utf-8', errors='ignore')
        # print(f"DEBUG: Term len output from {switch_IP}: {term_len_buffer}")

        channel.send(command + "\n")

        full_output = ""
        end_time = time.time() + 30 # Timeout for command execution (e.g., 30 seconds for show commands)

        # Read output until no more data for a certain period or prompt detected
        # This loop tries to ensure all output is captured.
        read_chunk = ""
        last_data_time = time.time()
        while time.time() < end_time:
            if channel.recv_ready():
                read_chunk = channel.recv(8192).decode('utf-8', errors='ignore')
                full_output += read_chunk
                last_data_time = time.time()
                # print(f"DEBUG: exec_ssh_command received chunk: {read_chunk}")
            else:
                # If no data, wait a bit. If no data for ~1s after last receive, assume done.
                if time.time() - last_data_time > 1.5:
                    break
                time.sleep(0.1)

        ssh_client.close()

        # Clean up the output: remove command echo and prompt
        lines = full_output.splitlines()
        cleaned_lines = []

        # Normalize the command sent for matching in output (e.g. remove extra spaces)
        normalized_command_sent = ' '.join(command.strip().split())

        command_echo_found = False
        # Regex for typical switch prompts (e.g., switch#, switch(config)#, switch>)
        prompt_pattern = re.compile(r"^\S+(?:\([^\)]+\))?[#>] ?$")

        for i, line_content in enumerate(lines):
            stripped_line = line_content.strip()
            # Attempt to remove command echo more reliably
            if not command_echo_found and normalized_command_sent in stripped_line:
                 # Check if this line is ONLY the command or command + prompt
                if stripped_line == normalized_command_sent or prompt_pattern.match(stripped_line.replace(normalized_command_sent, "").strip()):
                    command_echo_found = True
                    # If next line is blank, skip it too (often follows command echo)
                    if i + 1 < len(lines) and not lines[i+1].strip():
                        lines[i+1] = "" # Mark for skipping
                    continue

            if prompt_pattern.match(stripped_line):
                continue # Skip prompt lines

            if line_content: # Add non-empty, non-prompt, non-echo lines
                 cleaned_lines.append(line_content)

        final_cleaned_output = '\n'.join(cleaned_lines).strip()
        # print(f"DEBUG: Raw output for '{command.strip()}' on {switch_IP}:\n{full_output}")
        # print(f"DEBUG: Cleaned output for '{command.strip()}' on {switch_IP}:\n{final_cleaned_output}")
        return final_cleaned_output, None

    except Exception as e:
        # print(f"Error in exec_ssh_command for {switch_IP} with command {command}: {e}")
        return "", f"SSH/command execution error: {str(e)}"


def exec_ssh_config_commands(config_commands, switch_IP, username, password):
    try:
        ssh_client = paramiko.SSHClient()
        ssh_client.load_system_host_keys()
        ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh_client.connect(switch_IP, port=22, username=username, password=password, timeout=20, banner_timeout=20)

        channel = ssh_client.invoke_shell(width=200, height=1000)

        full_debug_output = ""

        def read_channel_buffer(timeout=0.5):
            nonlocal full_debug_output
            buffer = ""
            start_time = time.time()
            while time.time() - start_time < timeout:
                if channel.recv_ready():
                    data = channel.recv(4096).decode('utf-8', errors='ignore')
                    buffer += data
                    full_debug_output += data
                else:
                    time.sleep(0.05) # Small pause
            return buffer

        read_channel_buffer(timeout=1.5) # Clear initial banner

        channel.send("enable\n")
        read_channel_buffer()

        channel.send("configure terminal\n")
        read_channel_buffer() # Capture (config)# prompt and any messages

        for i, cmd in enumerate(config_commands):
            # print(f"DEBUG: Sending config command to {switch_IP}: {cmd}")
            channel.send(cmd + "\n")
            # Wait slightly longer after the last command or for commands that might take time
            sleep_time = 0.7 if i == len(config_commands) -1 else 0.4
            read_channel_buffer(timeout=sleep_time) # Read output/prompt after each command

        channel.send("end\n")
        read_channel_buffer()

        ssh_client.close()

        # More specific Dell error patterns
        error_patterns = [
            r"invalid input detected",
            r"% (error|invalid|incomplete|ambiguous)",
            r"command rejected"
        ]
        for pattern in error_patterns:
            if re.search(pattern, full_debug_output, re.IGNORECASE):
                # print(f"DEBUG: Config error detected on {switch_IP}. Full output:\n{full_debug_output}")
                # Try to extract a more specific error message part
                error_line_match = re.search(f".*({pattern.replace('% ', '')}).*", full_debug_output, re.IGNORECASE | re.MULTILINE)
                specific_error = error_line_match.group(0).strip() if error_line_match else "Unknown error from output."
                return full_debug_output, f"Configuration error: '{specific_error}'"

        # print(f"DEBUG: Config commands successful on {switch_IP}. Full output:\n{full_debug_output}")
        return full_debug_output, None

    except Exception as e:
        # print(f"DEBUG: Exception in exec_ssh_config_commands for {switch_IP}: {e}")
        return "", f"SSH/Configuration exception: {str(e)}"


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
    
port_id_pattern = re.compile(r"^(Gi|Te|Po)\d+((/\d+)?/\d+|\d+)$") # Gi1/0/1, Te1/0/1, Po1, Gi1/0/10, Po12

def parse_vlan_info(output_show_vlan):
    """
    Parses the output of 'show vlan' to extract VLAN IDs and Names.
    Uses an iterative approach based on column positions determined from the header/separator lines.
    """
    vlans = {} # id -> name
    lines = output_show_vlan.splitlines()
    header_found = False
    separator_line = None
    data_lines_start_index = -1

    # Find header and separator lines to determine column positions
    # VLAN ID  Name                             Type    Ports
    # -------  -------------------------------- ------- -------------------
    # 1        default                          Default Gi1/0/1-24,Po1-8
    for line in lines:
        line = line.rstrip() # Keep leading spaces for alignment if needed, but strip trailing
        if not header_found:
            if "VLAN ID" in line and "Name" in line and "Type" in line:
                header_found = True
            continue
        if header_found and "-------" in line:
            separator_line = line
            data_lines_start_index = lines.index(line) + 1
            break # Found header and separator, stop searching

    if not header_found or not separator_line or data_lines_start_index == -1:
        # Could not find the expected header/separator format
        print("DEBUG: Could not find VLAN header or separator.")
        return {} # Return empty dict, indicating failure to parse

    # Determine column start indices based on the separator line
    # Look for at least two spaces separating the column separators (---)
    name_start_index = -1
    ports_start_index = -1
    type_start_index = -1

    # Find the positions of the column separators in the separator line
    vlan_sep_end = separator_line.find("-----") + 5
    name_sep_end = separator_line.find("---------------") + 15
    ports_sep_end = separator_line.find("-------------") + 13

    # Find the start of the next column by looking for >=2 spaces after the previous separator ends
    match_name_sep = re.search(r"\s{2,}", separator_line[vlan_sep_end:])
    if match_name_sep: name_start_index = vlan_sep_end + match_name_sep.start() + len(match_name_sep.group(0))

    match_ports_sep = re.search(r"\s{2,}", separator_line[name_sep_end:])
    if match_ports_sep: ports_start_index = name_sep_end + match_ports_sep.start() + len(match_ports_sep.group(0))

    match_type_sep = re.search(r"\s{2,}", separator_line[ports_sep_end:])
    if match_type_sep: type_start_index = ports_sep_end + match_type_sep.start() + len(match_type_sep.group(0))

    if name_start_index == -1 or ports_start_index == -1 or type_start_index == -1:
        print("DEBUG: Could not determine column positions from separator line.")
        print(f"DEBUG: Separator line: '{separator_line}'")
        print(f"DEBUG: name_start_index={name_start_index}, ports_start_index={ports_start_index}, type_start_index={type_start_index}")
        return {} # Return empty dict, indicating failure to parse

    # Regex to find VLAN ID at the start of a line (only digits followed by space)
    vlan_id_line_re = re.compile(r"^\s*(\d+)\s+")

    # Process data lines starting from the line after the separator
    for i in range(data_lines_start_index, len(lines)):
        line = lines[i]
        # Check if the line starts with a VLAN ID
        match_id = vlan_id_line_re.match(line)

        if match_id:
            # This line starts a new VLAN entry
            vlan_id_str = match_id.group(1)
            try:
                vlan_id = int(vlan_id_str)
            except ValueError:
                # Should not happen with the regex, but as a safeguard
                continue

            # Extract the name using the determined column indices
            # The name is between the end of the VLAN ID part and the start of the Ports column
            # Ensure slicing doesn't go beyond the line length
            name_end_index = min(len(line), ports_start_index)
            vlan_name = line[name_start_index:name_end_index].strip()

            vlans[vlan_id] = vlan_name
        # else: This line does not start with a VLAN ID, assume it's a continuation
        # of the Ports list from the previous VLAN entry. Ignore for ID/Name mapping.

    return vlans

def display_vlan_names(switch_ip, username, password):
    print(f"\nFetching VLAN information from {switch_ip}...")
    output, error = exec_ssh_command("show vlan", switch_ip, username, password)
    if error:
        print(f"Error fetching VLANs from {switch_ip}: {error}")
        return

    if not output or output.strip() == "":
        print(f"No output received for 'show vlan' from {switch_ip}.")
        if "debug" in sys.argv:
             print("Raw output from 'show vlan':\n", output)
        return

    vlan_info = parse_vlan_info(output)
    if not vlan_info:
        print("Could not parse VLAN information or no VLANs found.")
        if "debug" in sys.argv:
            print("Raw output from 'show vlan':\n", output)
            return

    print("\nAvailable VLANs on the switch:")
    for vlan_id, name in sorted(vlan_info.items()):
        print(f"  ID: {vlan_id:<5} Name: {name}")
    print("")

def parse_port_vlan_config(output_show_int_switchport):
    config = {
        'pvid': None,
        'untagged_vlans': [],
        'tagged_vlans': []
    }
    for line in output_show_int_switchport.splitlines():
        line = line.strip()
        if line.startswith("General Mode PVID:"):
            match = re.search(r'General Mode PVID:\s*(\d+)', line)
            if match:
                config['pvid'] = match.group(1)
        elif line.startswith("General Mode Untagged VLANs:"):
            match = re.search(r'General Mode Untagged VLANs:\s*(.*)', line)
            if match:
                vlans_str = match.group(1).strip()
                if vlans_str: # Check if not empty
                    config['untagged_vlans'] = [v.strip() for v in vlans_str.split(',') if v.strip().isdigit()]
        elif line.startswith("General Mode Tagged VLANs:"):
            match = re.search(r'General Mode Tagged VLANs:\s*(.*)', line)
            if match:
                vlans_str = match.group(1).strip()
                if vlans_str: # Check if not empty
                    config['tagged_vlans'] = [v.strip() for v in vlans_str.split(',') if v.strip().isdigit()]
    return config

def configure_vlans_on_port(switch_ip, port_id, username, password):
    print(f"\nConfiguring VLANs for port {port_id} on switch {switch_ip}.")

    print(f"Fetching current configuration for port {port_id}...")
    current_config_output, error = exec_ssh_command(f"show interfaces switchport {port_id}", switch_ip, username, password)
    if error:
        print(f"Error fetching current port configuration: {error}")
        return
    if not current_config_output:
        print(f"Could not fetch current configuration for port {port_id}.")
        return

    current_vlans = parse_port_vlan_config(current_config_output)
    print("Current VLAN configuration:")
    print(f"  PVID: {current_vlans.get('pvid', 'Not set')}")
    print(f"  Untagged VLANs: {', '.join(current_vlans.get('untagged_vlans', [])) or 'None'}")
    print(f"  Tagged VLANs: {', '.join(current_vlans.get('tagged_vlans', [])) or 'None'}")

    new_pvid_str = ""
    while True:
        new_pvid_str = input("Enter new PVID (this will be the untagged VLAN ID, e.g., 1010, press Enter to skip PVID change): ").strip()
        if not new_pvid_str:
            new_pvid = None
            print("PVID/Untagged VLAN configuration will not be changed, or will be derived if clearing all.")
            break
        if new_pvid_str.isdigit() and 1 <= int(new_pvid_str) <= 4094:
            new_pvid = new_pvid_str
            break
        else:
            print("Invalid VLAN ID. Must be a number between 1 and 4094.")

    new_tagged_vlans_list = []
    while True:
        new_tagged_vlans_str = input("Enter new Tagged VLAN IDs (comma-separated, e.g., 1020,1030, press Enter for none/to clear existing): ").strip()
        if not new_tagged_vlans_str:
            print("No new tagged VLANs specified. Existing tagged VLANs (if any, not matching new PVID) will be removed.")
            break
        
        temp_tagged_list = []
        valid_tagged_input = True
        for v_id_str in new_tagged_vlans_str.split(','):
            v_id = v_id_str.strip()
            if v_id.isdigit() and 1 <= int(v_id) <= 4094:
                if new_pvid and v_id == new_pvid:
                    print(f"Error: VLAN {v_id} cannot be both untagged (as PVID) and explicitly tagged.")
                    valid_tagged_input = False
                    break
                temp_tagged_list.append(v_id)
            else:
                print(f"Invalid VLAN ID '{v_id}' in tagged list. Must be a number between 1 and 4094.")
                valid_tagged_input = False
                break
        if valid_tagged_input:
            new_tagged_vlans_list = temp_tagged_list
            break
        # else, loop again for tagged VLAN input

    if new_pvid is None and not new_tagged_vlans_str: # User skipped PVID and entered nothing for tagged
        confirm_clear = input("No new PVID and no new tagged VLANs specified. This might clear existing VLANs or set to default. Continue? [y|n]: ").lower()
        if confirm_clear not in ['y', 'yes']:
            print("Configuration aborted by user.")
            return
        if not new_pvid and not new_tagged_vlans_list: # If user wants to clear, PVID 1 is a safe default
            print("Setting PVID to 1 and removing other VLANs as no specific configuration was provided.")
            new_pvid = "1"

    commands = []
    commands.append(f"interface {port_id}")
    commands.append("switchport mode general")

    old_vlans_on_port = set()
    if current_vlans.get('pvid'): old_vlans_on_port.add(current_vlans['pvid'])
    for v in current_vlans.get('untagged_vlans', []): old_vlans_on_port.add(v)
    for v in current_vlans.get('tagged_vlans', []): old_vlans_on_port.add(v)

    all_new_final_vlans = set()
    if new_pvid:
        commands.append(f"switchport general pvid {new_pvid}")
        commands.append(f"switchport general allowed vlan add {new_pvid} untagged")
        all_new_final_vlans.add(new_pvid)

    for vlan_id in new_tagged_vlans_list:
        commands.append(f"switchport general allowed vlan add {vlan_id} tagged")
        all_new_final_vlans.add(vlan_id)

    vlans_to_remove = old_vlans_on_port - all_new_final_vlans
    for v_rem in vlans_to_remove:
        if v_rem == "1" and new_pvid == "1": # Don't try to remove VLAN 1 if it's the new PVID
             continue
        commands.append(f"switchport general allowed vlan remove {v_rem}")

    if not commands[2:]: # Only interface and switchport mode general
        print("No effective configuration changes to apply based on input.")
        return

    print("\nThe following commands will be sent:")
    for cmd in commands: print(f"  {cmd}")

    confirm = input("Proceed with these changes? [y|n]: ").lower()
    if confirm == 'y' or confirm == 'yes':
        print("Applying configuration...")
        output, error = exec_ssh_config_commands(commands, switch_ip, username, password)
        if error:
            print(f"Error during configuration: {error}")
            if "debug" in sys.argv or output: print(f"Full switch output:\n{output}")
        else:
            print("Configuration applied successfully.")
            if "debug" in sys.argv and output: print(f"Full switch output (debug):\n{output}")
            print("\nFetching updated port configuration...")
            updated_config_output, err = exec_ssh_command(f"show interfaces switchport {port_id}", switch_ip, username, password)
            if err: print(f"Error fetching updated port configuration: {err}")
            else:
                print("Updated configuration:")
                print(updated_config_output)
    else:
        print("Configuration aborted by user.")


def mac_search_workflow(switch_IPs, username, password):
    mac = input("Please enter the MAC-address to find: ")
    device_found = False

    if mac.lower() == "test": # Keep test functionality if desired
        if not switch_IPs:
            print("No switches defined for testing.")
            return
        print(f"{switch_IPs[0]} will now be queried for its MAC-address-table. This can take some time!")
        ssh_test_output, ssh_test_error = ssh_test(switch_IPs[0], username, password)
        if ssh_test_error:
            print(f"Error during ssh_test: {ssh_test_error}")
        return

    formatted_mac = format_mac_address(mac)
    if not formatted_mac:
        return

    print(f"Formatted MAC: {formatted_mac}")

    switches_checked = []
    for ip in switch_IPs:
        print(f"Checking switch {ip}...")
        switches_checked.append(ip)
        command = f"show mac address-table address {formatted_mac}"
        output, error = exec_ssh_command(command, ip, username, password)

        if error:
            print(f"Error when checking {ip}: {error}")
        else:
            port_on_switch = get_port_from_output(output)
            # Check if MAC is found, is dynamic, and on a Gi port
            if formatted_mac.lower() in output.lower() and \
               "dynamic" in output.lower().split() and \
               port_on_switch and port_on_switch.startswith("Gi"):

                print(f"\n>>> {formatted_mac} was found on switch {ip} on port {port_on_switch}.")
                print(f"Relevant output line(s):")
                for line in output.splitlines():
                    if formatted_mac.lower() in line.lower() and port_on_switch in line:
                        print(line.strip())

                device_found = True
                answer = input("\nDo you want to see the interface configuration for this port? [y|n] ").lower()
                if answer == "y" or answer == "yes":
                    port_config_cmd = f"show interfaces switchport {port_on_switch}"
                    cfg_output, cfg_error = exec_ssh_command(port_config_cmd, ip, username, password)
                    if cfg_error:
                        print(f"Error fetching port configuration from {ip}: {cfg_error}")
                    else:
                        print(cfg_output)

                if ip != switch_IPs[-1]: # If not the last switch
                    answer_continue = input("\nContinue the search on other switches? [y|n] ").lower()
                    if not (answer_continue == "y" or answer_continue == "yes"):
                        return # Found, and user does not want to continue
                else: # Last switch checked
                    return # Found on last switch, end search

            elif "debug" in sys.argv and output:
                print(f"Debug output for switch {ip} (MAC {formatted_mac}):\n{output}")

    if not device_found:
        print(f"\n{formatted_mac} was not found directly connected to a Gi port on the checked switches.")
    print(f"Switches checked: {', '.join(switches_checked)}")


def main_menu(switch_IPs_list, user, passwd):
    while True:
        print("\nDell N1500 MAC Finder & VLAN Configurator")
        print("------------------------------------------")
        print("1. Find MAC address")
        print("2. Configure VLANs on a port")
        print("3. Show VLAN names on a switch")
        print("4. Exit")
        choice = input("Enter your choice: ")

        if choice == '1':
            mac_search_workflow(switch_IPs_list, user, passwd)
        elif choice == '2':
            if not switch_IPs_list: print("No switches defined."); continue
            target_ip = input(f"Enter IP of the switch to configure (available: {', '.join(switch_IPs_list)}): ").strip()
            if target_ip not in switch_IPs_list:
                print(f"Invalid switch IP. Please choose from the predefined list or add to script.")
                continue
            port_str = input("Enter port to configure (e.g., Gi1/0/8): ").strip()
            if not port_id_pattern.match(port_str):
                 print(f"Invalid port format: '{port_str}'. Expected format like 'Gi1/0/1', 'Te1/0/1', 'Po1'.")
                 continue
            configure_vlans_on_port(target_ip, port_str, user, passwd)
        elif choice == '3':
            if not switch_IPs_list: print("No switches defined."); continue
            target_ip_show = input(f"Enter IP of the switch to show VLANs from (available: {', '.join(switch_IPs_list)}): ").strip()
            if target_ip_show not in switch_IPs_list:
                print(f"Invalid switch IP. Please choose from the predefined list or add to script.")
                continue
            display_vlan_names(target_ip_show, user, passwd)
        elif choice == '4':
            print("Exiting.")
            sys.exit()
        else:
            print("Invalid choice. Please try again.")
        print("--------------------------------------------------")

if __name__ == "__main__":
    # define your switches that you want to be checked here as a string array
    # die .41 ist der zweite Switch im Dispo-Stack und muss nicht separat geprüft werden!
    switch_IPs = ["192.168.23.31", "192.168.23.32", "192.168.23.33", "192.168.23.34", "192.168.23.35", "192.168.23.38", "192.168.23.39", "192.168.23.40", "192.168.23.42", "192.168.23.43", "192.168.23.44"]
    username = "admin"

    # get password once from user and store encrypted for runtime
    password = getpass.getpass(prompt='Enter SSH password for switches: ')

    main_menu(switch_IPs, username, password)


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
