import paramiko
import time
import getpass
import sys
import re
import socket # Added for hostname resolution
import os # Import os module to check for Windows and potentially enable ANSI codes
from switch_config import switch_inventory # Import switch_inventory from config file





"""
This is proposed code by Gemini after the following prompt:

***** Prompt *****
This tool is used to find the switch and port of a bunch of preconfigured switches that a mac address is connected to. 
I would like to add some IP-based features as well, such as being able to enter a hostname (for example "DE11465" or 
"DE11465.koettermann.local") and then the tool is supposed to search the network for the devices ip- and mac-addresses 
and then query the switches for the port.
******************


***** Gemini Answer *****
Okay, I can help you add a feature to your Dell N1500 MAC Finder tool that allows searching for a device based on its 
hostname.

This new functionality will:

Prompt the user for a hostname.
Attempt to resolve this hostname to an IP address.
Query the ARP tables of your preconfigured switches to find the MAC address associated with that IP.
If a MAC address is found, it will then use the existing logic to search for the switch port to which that MAC address 
is connected.
Here are the suggested code changes:

<CODE>

Key changes include:

New Imports: Added import socket for hostname resolution.
New Helper Functions:
resolve_hostname_to_ip(hostname): Resolves a hostname to an IP.
find_mac_from_arp_table(target_ip, arp_table_output): Parses show arp output from a switch.
get_mac_for_ip_via_switches(...): Iterates through switches, executes show arp, and uses find_mac_from_arp_table to 
find the MAC for a given IP.
Refactored MAC Search:
_perform_mac_search_on_switches(...): A new internal function that contains the core logic for searching a MAC address 
across switches and handling the output. This improves the parsing of the show mac address-table address <MAC> command 
for more accuracy.
The existing mac_search_workflow now calls this new internal function.
New Workflow:
hostname_search_workflow(...): Orchestrates the new feature: gets hostname, resolves to IP, finds MAC via switch ARP 
tables, then calls _perform_mac_search_on_switches.
Main Menu Update:
Added "Find device by Hostname" as option 2.
Subsequent menu options have been renumbered.
The switch_details_by_ip dictionary is now passed to the relevant workflow functions to provide context for switch 
identification in messages.
Remember to test this thoroughly in your environment. The success of finding a MAC address from an IP using switch ARP 
tables depends on the IP being present in those tables, which usually means the switch has recently communicated with 
or seen traffic from that IP.
"""





# --- ANSI Color Codes ---
# Check if running on Windows and enable ANSI escape codes if necessary (for older Windows versions)
if os.name == 'nt':
    os.system('') # Enables ANSI escape codes on Windows 10+

GREEN = '\033[92m'
RED = '\033[91m'
BLUE = '\033[94m'
MAGENTA = '\033[95m'
RESET = '\033[0m' # Reset to default color

# Global variable to control debug mode
debug_mode_enabled = False


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
    

def get_switch_identifier(ip, switch_details_map):
    """Returns a formatted string for switch identification (IP, Location, Rack)."""
    details = switch_details_map.get(ip)
    if details:
        return f"{MAGENTA}{ip}{RESET} ({details.get('location', 'N/A')} - {details.get('rack_details', 'N/A')})"
    return f"{MAGENTA}{ip}{RESET}"


# connect to the switch via SSH and the previously specified username and password
# execute the command
# get all the output
# return the output
def exec_ssh_command(command, switch_IP, username, password):
    try:
        ssh_client = paramiko.SSHClient()
        ssh_client.load_system_host_keys()
        ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        # Increased timeout for connect and banner
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
        if debug_mode_enabled: print(f"{BLUE}DEBUG: Raw output for '{command.strip()}' on {get_switch_identifier(switch_IP, switch_details_by_ip)}:{RESET}\n{full_output}")
        if debug_mode_enabled: print(f"{BLUE}DEBUG: Cleaned output for '{command.strip()}' on {get_switch_identifier(switch_IP, switch_details_by_ip)}:{RESET}\n{final_cleaned_output}")
        return final_cleaned_output, None

    except Exception as e:
        # print(f"Error in exec_ssh_command for {get_switch_identifier(switch_IP, switch_details_by_ip)} with command {command}: {e}")
        return "", f"SSH/command execution error: {str(e)}"


def exec_ssh_config_commands(config_commands, switch_IP, username, password):
    try:
        ssh_client = paramiko.SSHClient()
        ssh_client.load_system_host_keys()
        ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh_client.connect(switch_IP, port=22, username=username, password=password, timeout=20, banner_timeout=20) # Increased timeout

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
            if debug_mode_enabled: print(f"{BLUE}DEBUG: Sending config command to {get_switch_identifier(switch_IP, switch_details_by_ip)}: {cmd}{RESET}")
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
                if debug_mode_enabled: print(f"{BLUE}DEBUG: Config error detected on {get_switch_identifier(switch_IP, switch_details_by_ip)}. Full output:{RESET}\n{full_debug_output}")
                # Try to extract a more specific error message part from the output
                error_line_match = re.search(f".*({pattern.replace('% ', '')}).*", full_debug_output, re.IGNORECASE | re.MULTILINE)
                specific_error = error_line_match.group(0).strip() if error_line_match else "Unknown error from output."
                return full_debug_output, f"{RED}Configuration error on {get_switch_identifier(switch_IP, switch_details_by_ip)}: '{specific_error}'{RESET}"

        if debug_mode_enabled: print(f"{BLUE}DEBUG: Config commands successful on {get_switch_identifier(switch_IP, switch_details_by_ip)}. Full output:{RESET}\n{full_debug_output}")
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
        print(f"{RED}Error: The provided MAC address is not in the correct format.{RESET}")
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

    # Simplified: Return empty dict as parsing is too complex/unreliable for now.
    # The display_vlan_names function will show raw output.
    return {}

def display_vlan_names(switch_ip, username, password):
    print(f"\n{BLUE}Fetching VLAN configuration from {get_switch_identifier(switch_ip, switch_details_by_ip)}...{RESET}")
    output, error = exec_ssh_command("show vlan", switch_ip, username, password)
    if error:
        print(f"{RED}Error fetching VLANs from {get_switch_identifier(switch_ip, switch_details_by_ip)}: {error}{RESET}")
        return # Exit the function on error
    
    if not output or output.strip() == "":
        print(f"No output received for 'show vlan' from {switch_ip}.")
    print(f"\n--- VLAN Configuration on {switch_ip} ---")
    print(output)
    print(f"--- End of VLAN Configuration ---")

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
    print(f"\n{BLUE}Configuring VLANs for port {port_id} on switch {get_switch_identifier(switch_ip, switch_details_by_ip)}.{RESET}")

    print(f"{BLUE}Fetching current configuration for port {port_id}...{RESET}")
    current_config_output, error = exec_ssh_command(f"show interfaces switchport {port_id}", switch_ip, username, password)
    if error:
        print(f"{RED}Error fetching current port configuration: {error}{RESET}")
        return
    if not current_config_output:
        print(f"{RED}Could not fetch current configuration for port {port_id}.{RESET}")
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
            print(f"{BLUE}PVID/Untagged VLAN configuration will not be changed, or will be derived if clearing all.{RESET}")
            break
        if new_pvid_str.isdigit() and 1 <= int(new_pvid_str) <= 4094:
            new_pvid = new_pvid_str
            break
        else:
            print(f"{RED}Invalid VLAN ID. Must be a number between 1 and 4094.{RESET}")
            
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
            if v_id.isdigit() and 1 <= int(v_id) <= 4094: # Check only for valid range
                if new_pvid and v_id == new_pvid:
                    print(f"Error: VLAN {v_id} cannot be both untagged (as PVID) and explicitly tagged.")
                    valid_tagged_input = False # Mark as invalid input
                    break
                temp_tagged_list.append(v_id)
            else:
                print(f"{RED}Invalid VLAN ID '{v_id}' in tagged list. Must be a number between 1 and 4094.{RESET}")
                valid_tagged_input = False # Mark as invalid input
                break
        if valid_tagged_input:
            new_tagged_vlans_list = temp_tagged_list
            break
        # else, loop again for tagged VLAN input

    if new_pvid is None and not new_tagged_vlans_str: # User skipped PVID and entered nothing for tagged
        confirm_clear = input("No new PVID and no new tagged VLANs specified. This might clear existing VLANs or set to default. Continue? [y|n]: ").lower()
        if confirm_clear not in ['y', 'yes']:
            print(f"{BLUE}Configuration aborted by user.{RESET}")
            return
        if not new_pvid and not new_tagged_vlans_list: # If user wants to clear, PVID 1 is a safe default
            print(f"{BLUE}Setting PVID to 1 and removing other VLANs as no specific configuration was provided.{RESET}")
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
        print(f"{BLUE}No effective configuration changes to apply based on input.{RESET}")
        return

    print("\nThe following commands will be sent:")
    for cmd in commands: print(f"  {cmd}")

    confirm = input("Proceed with these changes? [y|n]: ").lower()
    if confirm in ['y', 'yes']:
        print(f"{BLUE}Applying configuration...{RESET}")
        output, error = exec_ssh_config_commands(commands, switch_ip, username, password)
        if error:
            print(f"{RED}Error during configuration: {error}{RESET}")
            if "debug" in sys.argv or output: print(f"Full switch output:\n{output}")
        else:
            print(f"{GREEN}Configuration applied successfully.{RESET}")
            if "debug" in sys.argv and output: print(f"Full switch output (debug):\n{output}")
            print("\nFetching updated port configuration...")
            updated_config_output, err = exec_ssh_command(f"show interfaces switchport {port_id}", switch_ip, username, password)
            if err: print(f"Error fetching updated port configuration: {err}")
            else:
                print("Updated configuration:")
                print(updated_config_output)
    else:
        print(f"{BLUE}Configuration aborted by user.{RESET}")


def resolve_hostname_to_ip(hostname):
    """Resolves a hostname to an IP address."""
    try:
        ip_address = socket.gethostbyname(hostname)
        return ip_address
    except socket.gaierror: # getaddrinfo error
        return None

def find_mac_from_arp_table(target_ip, arp_table_output):
    """Parses 'show arp' output to find MAC for a given IP."""
    # Dell MAC format is typically xxxx.xxxx.xxxx but ARP might show other formats
    mac_pattern_dell = r"([0-9A-Fa-f]{4}\.[0-9A-Fa-f]{4}\.[0-9A-Fa-f]{4})"
    mac_pattern_common = r"([0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}"

    for line in arp_table_output.splitlines():
        parts = line.split()
        if not parts or len(parts) < 2:
            continue
        
        # Check if the first part is the target_ip
        if parts[0] == target_ip:
            potential_mac = parts[1]
            # Check if potential_mac matches known MAC address patterns
            if re.fullmatch(mac_pattern_dell, potential_mac, re.IGNORECASE) or \
               re.fullmatch(mac_pattern_common, potential_mac, re.IGNORECASE):
                return potential_mac # Return as found, formatting will be done by format_mac_address
    return None

def get_mac_for_ip_via_switches(target_ip, switch_IPs, username, password, switch_details_map):
    """Attempts to find the MAC address for a given IP by querying ARP tables of switches."""
    print(f"\n{BLUE}Attempting to find MAC address for IP {target_ip} from switch ARP tables...{RESET}")
    for switch_ip in switch_IPs:
        print(f"Querying ARP table on switch {get_switch_identifier(switch_ip, switch_details_map)}...")
        command = "show arp" # General command, could also try "show ip arp"
        
        output, error = exec_ssh_command(command, switch_ip, username, password)
        if error:
            print(f"{RED}Error querying ARP table on {get_switch_identifier(switch_ip, switch_details_map)}: {error}{RESET}")
            continue
        if output:
            if debug_mode_enabled:
                print(f"{BLUE}DEBUG: ARP table from {get_switch_identifier(switch_ip, switch_details_map)}:{RESET}\n{output}")
            mac_address = find_mac_from_arp_table(target_ip, output)
            if mac_address:
                print(f"{GREEN}MAC address {mac_address} for IP {target_ip} found on switch {get_switch_identifier(switch_ip, switch_details_map)}'s ARP table.{RESET}")
                return mac_address
    print(f"{RED}Could not find MAC address for IP {target_ip} in the ARP tables of the queried switches.{RESET}")
    return None


def _perform_mac_search_on_switches(formatted_mac, target_identifier, switch_IPs, username, password, switch_details_map):
    """
    Searches for a formatted MAC address on specified switches.
    target_identifier is a string (e.g., MAC address or IP/hostname) for display purposes.
    Returns True if found and user chose to stop or search completed, False if not found at all.
    """
    device_found_on_port = False
    switches_checked_formatted = []

    for ip_idx, ip in enumerate(switch_IPs):
        print(f"Checking switch {get_switch_identifier(ip, switch_details_map)} for MAC {formatted_mac} (related to {target_identifier})...")
        switches_checked_formatted.append(get_switch_identifier(ip, switch_details_map))
        command = f"show mac address-table address {formatted_mac}"
        output, error = exec_ssh_command(command, ip, username, password)

        if error:
            print(f"{RED}Error when checking {get_switch_identifier(ip, switch_details_map)}: {error}{RESET}")
        else:
            mac_found_in_line = False
            port_on_switch = None
            relevant_line_info = ""

            if output:
                for line_content in output.splitlines():
                    line_lower = line_content.lower()
                    if formatted_mac.lower() in line_lower:
                        parts = line_lower.split()
                        is_dynamic = "dynamic" in parts
                        port_match_in_line = re.search(r"\b(Gi|Te|Po)\d+((/\d+)?/\d+|\d+)\b", line_content, re.IGNORECASE)
                        if is_dynamic and port_match_in_line:
                            potential_port = port_match_in_line.group(0)
                            if potential_port.upper().startswith("GI"):
                                mac_found_in_line = True
                                port_on_switch = potential_port
                                relevant_line_info = line_content.strip()
                                if debug_mode_enabled:
                                    print(f"{BLUE}DEBUG: Matched line for MAC search: '{relevant_line_info}', Extracted port: {port_on_switch}{RESET}")
                                break 
            
            if mac_found_in_line and port_on_switch:
                print(f"\n{GREEN}>>> MAC {formatted_mac} (for {target_identifier}) was found on switch {get_switch_identifier(ip, switch_details_map)} on port {port_on_switch}.{RESET}")
                print(f"Relevant output line: {relevant_line_info}")
                device_found_on_port = True

                answer = input("\nDo you want to see the interface configuration for this port? [y|n] ").lower()
                if answer in ["y", "yes"]:
                    port_config_cmd = f"show interfaces switchport {port_on_switch}"
                    cfg_output, cfg_error = exec_ssh_command(port_config_cmd, ip, username, password)
                    if cfg_error:
                        print(f"{RED}Error fetching port configuration from {get_switch_identifier(ip, switch_details_map)}: {cfg_error}{RESET}")
                    else:
                        print(cfg_output)
                
                if ip_idx < len(switch_IPs) - 1:
                    answer_continue = input(f"\nContinue the search for {formatted_mac} on other switches? [y|n] ").lower()
                    if not (answer_continue in ["y", "yes"]):
                        print(f"Search for {formatted_mac} stopped by user.")
                        return True 
                else:
                    return True 

            elif debug_mode_enabled and output:
                print(f"{BLUE}Debug output for switch {get_switch_identifier(ip, switch_details_map)} (MAC {formatted_mac} for {target_identifier}):{RESET}\n{output}")

    if not device_found_on_port:
        print(f"\n{RED}MAC {formatted_mac} (for {target_identifier}) was not found directly connected to a Gi port on the checked switches.{RESET}")
    
    print(f"Switches checked for {formatted_mac}: {', '.join(switches_checked_formatted)}")
    return device_found_on_port


def mac_search_workflow(switch_IPs, username, password):
    mac = input("Please enter the MAC-address to find: ")
    device_found = False

    if mac.lower() == "test": # Keep test functionality if desired
        if not switch_IPs:
            print("No switches defined for testing.")
            return
        print(f"{BLUE}{get_switch_identifier(switch_IPs[0], switch_details_by_ip)} will now be queried for its MAC-address-table. This can take some time!{RESET}")
        ssh_test_output, ssh_test_error = ssh_test(switch_IPs[0], username, password)
        if ssh_test_error:
            print(f"{RED}Error during ssh_test: {ssh_test_error}{RESET}")
        return

    formatted_mac = format_mac_address(mac)
    if not formatted_mac:
        return

    print(f"Searching for MAC: {formatted_mac}")
    # switch_details_by_ip is globally available in main, but better to pass explicitly if refactoring further
    _perform_mac_search_on_switches(formatted_mac, formatted_mac, switch_IPs, username, password, switch_details_by_ip)


def hostname_search_workflow(switch_IPs, username, password, switch_details_map):
    hostname_input = input("Please enter the hostname to find (e.g., DE11465 or DE11465.example.com): ").strip()
    if not hostname_input:
        print(f"{RED}No hostname entered.{RESET}")
        return

    print(f"\n{BLUE}Resolving hostname '{hostname_input}'...{RESET}")
    target_ip = resolve_hostname_to_ip(hostname_input)

    if not target_ip:
        print(f"{RED}Could not resolve hostname '{hostname_input}' to an IP address.{RESET}")
        return
    
    print(f"{GREEN}Hostname '{hostname_input}' resolved to IP address: {target_ip}{RESET}")

    mac_address_raw = get_mac_for_ip_via_switches(target_ip, switch_IPs, username, password, switch_details_map)

    if not mac_address_raw:
        print(f"{RED}Failed to find a MAC address for IP {target_ip} using switch ARP tables.{RESET}")
        print(f"You can try finding the MAC address manually and use option 1 (Find MAC address).")
        return

    formatted_mac = format_mac_address(mac_address_raw)
    if not formatted_mac:
        # format_mac_address already prints an error if MAC is invalid
        print(f"The MAC address '{mac_address_raw}' (from IP {target_ip} for hostname '{hostname_input}') could not be formatted correctly.")
        return
    
    print(f"MAC address for IP {target_ip} (from hostname '{hostname_input}') is {mac_address_raw}, formatted as {formatted_mac}.")
    print(f"\n{BLUE}Now searching for port connected to MAC {formatted_mac} (from {hostname_input} / {target_ip})...{RESET}")
    
    _perform_mac_search_on_switches(formatted_mac, f"{hostname_input}/{target_ip}", switch_IPs, username, password, switch_details_map)

    

def display_switch_inventory(inventory_data):
    """Displays the switch inventory information in a formatted table."""
    if not inventory_data:
        print("No switch inventory data available.")
        return

    print("\nSwitch Inventory:")
    print("--------------------------------------------------------------------------------------------------------------------")
    print(f"{'IP Address':<18} | {'Location':<15} | {'Rack/Details':<20} | {'Model':<15} | {'Notes':<40}")
    print("--------------------------------------------------------------------------------------------------------------------")
    for switch in inventory_data:
        ip = switch.get('ip', 'N/A')
        location = switch.get('location', '')
        rack_details = switch.get('rack_details', '')
        model = switch.get('model', '')
        notes = switch.get('notes', '')
        print(f"{ip:<18} | {location:<15} | {rack_details:<20} | {model:<15} | {notes:<40}")
    print("--------------------------------------------------------------------------------------------------------------------")


def main_menu(switch_IPs_list, user, passwd):
    global debug_mode_enabled

    while True:
        print("\nDell N1500 MAC Finder & VLAN Configurator")
        print("------------------------------------------")
        print("1. Find MAC address")
        print("2. Find device by Hostname")
        print("3. Configure VLANs on a port")
        print("4. Show VLAN configuration of a switch")
        print("5. Show Switch Inventory")
        
        # Display current debug mode status in the menu
        debug_status = f"{GREEN}ON{RESET}" if debug_mode_enabled else f"{RED}OFF{RESET}"
        print(f"6. Toggle Debug Mode ({debug_status})")
        
        print("7. Exit")
        
        # Adjust available choices based on menu options
        valid_choices = ['1', '2', '3', '4', '5', '6', '7']
        
        choice = input("Enter your choice: ")

        if choice == '1':
            mac_search_workflow(switch_IPs_list, user, passwd) # switch_details_by_ip is passed implicitly via _perform_mac_search
        elif choice == '2':
            hostname_search_workflow(switch_IPs_list, user, passwd, switch_details_by_ip)
        elif choice == '3':
            if not switch_IPs_list: print("No switches defined."); continue
            target_ip = input(f"Enter IP of the switch to configure (available: {', '.join(switch_IPs_list)}): ").strip()
            # Find the switch details for the prompt
            switch_info_for_prompt = switch_details_by_ip.get(target_ip)
            if target_ip not in switch_IPs_list:
                print(f"Invalid switch IP. Please choose from the predefined list or add to script.")
                # Optionally print available switches again
                display_switch_inventory(switch_inventory)
                continue
            port_str = input("Enter port to configure (e.g., Gi1/0/8): ").strip()
            if not port_id_pattern.match(port_str):
                 print(f"Invalid port format: '{port_str}'. Expected format like 'Gi1/0/1', 'Te1/0/1', 'Po1'.")
                 continue
            configure_vlans_on_port(target_ip, port_str, user, passwd)
        elif choice == '4':
            if not switch_IPs_list: print("No switches defined."); continue
            target_ip_show = input(f"Enter IP of the switch to show VLANs from (available: {', '.join(switch_IPs_list)}): ").strip()
            # Find the switch details for the prompt
            switch_info_for_prompt_show = switch_details_by_ip.get(target_ip_show)
            if target_ip_show not in switch_IPs_list:
                print(f"Invalid switch IP. Please choose from the predefined list or add to script.")
                # Optionally print available switches again
                display_switch_inventory(switch_inventory)
                continue
            display_vlan_names(target_ip_show, user, passwd)
        elif choice == '5':
            # Pass the global switch_inventory list
            display_switch_inventory(switch_inventory)
        elif choice == '6':
            # Toggle debug mode
            debug_mode_enabled = not debug_mode_enabled
            status = "enabled" if debug_mode_enabled else "disabled"
            print(f"{BLUE}Debug mode is now {status}.{RESET}")
        elif choice == '7':
            print("Exiting.")
            sys.exit()
        else:
            print("Invalid choice. Please try again.")
        print("--------------------------------------------------")


if __name__ == "__main__":
    # Check if debug mode was enabled via command line initially
    # This allows starting with debug enabled if desired
    if "debug" in sys.argv:
        debug_mode_enabled = True
        sys.argv.remove("debug") # Remove it so it doesn't interfere later

    username = "admin"

    # get password once from user and store encrypted for runtime
    password = getpass.getpass(prompt='Enter SSH password for switches: ')

    # Create a dictionary for quick lookup of switch details by IP
    # Filter out entries with 'no IP set'
    # Also create a list of IPs to be queried
    switch_details_by_ip = {}
    queryable_switch_ips = []
    for s_info in switch_inventory:
        if s_info.get('ip') and s_info['query'] == 'yes':
            switch_details_by_ip[s_info['ip']] = s_info
            queryable_switch_ips.append(s_info['ip'])

    main_menu(queryable_switch_ips, username, password)


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
