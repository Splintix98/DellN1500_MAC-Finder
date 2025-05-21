# Dell N1500 MAC Finder & VLAN Configurator

A Python script designed to connect to Dell N1500 series networking switches via SSH. It provides functionalities such as locating MAC addresses, configuring VLANs on specific ports, displaying switch VLAN configurations, and managing a switch inventory.

![Demo showing the executable generated from the script using PyInstaller](https://github.com/Splintix98/DellN1500_MAC-Finder/blob/main/Demo.png)

## Features

*   **MAC Address Finder**: Searches specified switches for a given MAC address and reports the switch and port where it's found.
*   **VLAN Configuration**:
    *   Set PVID (untagged VLAN).
    *   Set tagged VLANs.
    *   Ensures only user-defined VLANs are active on the port post-configuration.
*   **Display VLAN Configuration**: Shows the raw output of `show vlan` for a specified switch.
*   **Switch Inventory Display**: Lists details of configured switches (IP, location, model, notes) from an external configuration file.
*   **Interactive Menu**: Easy-to-use command-line menu for accessing different functionalities.
*   **Debug Mode**: Toggleable debug mode for verbose output during script execution.
*   **Colorized Output**: Enhanced terminal output with colors for better readability.

## Prerequisites

*   Python 3.x
*   Paramiko library: `pip install paramiko`
*   Access to Dell N1500 series switches via SSH with enable privileges.

## Setup & Installation

1.  **Clone the repository (or download the files):**
    ```bash
    git clone <your-repository-url>
    cd DellN1500_MAC-Finder
    ```

2.  **Install dependencies:**
    ```bash
    pip install paramiko
    ```

3.  **Configure Switches:**
    *   Create a file named `switch_config.py` in the same directory as `MAC_Finder_DELL_N1500.py`.
    *   Populate `switch_config.py` with your switch inventory. 

## Configuration

The script relies on a `switch_config.py` file for its switch inventory and list of IPs to query.

**`switch_config.py` Example:**

```python
# switch_config.py

# Define switch inventory data
# This list will be imported by the main script.
switch_inventory = [
    {'ip': '192.168.23.39', 'location': 'Academy', 'rack_details': 'Medienraum EG', 'model': 'Dell N1548P', 'query': 'yes', 'notes': ''},
    {'ip': '192.168.23.40', 'location': 'Fertigung', 'rack_details': 'Verteiler 1.1', 'model': 'Dell N1548P', 'query': 'yes', 'notes': 'oberer Switch Dispo-Büro'},
    {'ip': '192.168.23.41', 'location': 'Fertigung', 'rack_details': 'Verteiler 1.2', 'model': 'Dell N1548P', 'query': 'no', 'notes': 'unterer Switch Dispo-Büro'},  # part of stack, don't query
    {'ip': '192.168.23.42', 'location': 'Fertigung', 'rack_details': 'Verteiler 2', 'model': 'Dell N1548P', 'query': 'yes', 'notes': 'hinter der Beschichtung südl. Aussenwand'},
]

# IPs from this list (excluding 'query' == 'no') will be used for operations
# like MAC finding and as options for VLAN configuration.
