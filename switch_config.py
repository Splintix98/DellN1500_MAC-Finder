# switch_config.py

# Define switch inventory data
# This list will be imported by the main script.
switch_inventory = [
    {'ip': '192.168.23.31', 'location': 'Serverraum', 'rack_details': '1', 'model': 'Dell N1548P', 'query': 'yes', 'notes': ''},
    {'ip': '192.168.23.32', 'location': 'Serverraum', 'rack_details': '2', 'model': 'Dell N1548P', 'query': 'yes', 'notes': ''},
    {'ip': '192.168.23.33', 'location': 'Serverraum', 'rack_details': '3', 'model': 'Dell N1548P', 'query': 'yes', 'notes': ''},
    {'ip': '192.168.23.34', 'location': 'Serverraum', 'rack_details': '4', 'model': 'Dell N1548P', 'query': 'yes', 'notes': ''},
    {'ip': '192.168.23.35', 'location': 'Serverraum', 'rack_details': '5', 'model': 'Dell N1548P', 'query': 'yes', 'notes': ''},
    {'ip': '192.168.23.38', 'location': 'Verwaltung', 'rack_details': 'Heizungsraum', 'model': 'Dell N1524P', 'query': 'yes', 'notes': ''},
    {'ip': '192.168.23.39', 'location': 'Academy', 'rack_details': 'Medienraum EG', 'model': 'Dell N1548P', 'query': 'yes', 'notes': ''},
    {'ip': '192.168.23.40', 'location': 'Fertigung', 'rack_details': 'Verteiler 1.1', 'model': 'Dell N1548P', 'query': 'yes', 'notes': 'oberer Switch Dispo-Büro'},
    {'ip': '192.168.23.41', 'location': 'Fertigung', 'rack_details': 'Verteiler 1.2', 'model': 'Dell N1548P', 'query': 'no', 'notes': 'unterer Switch Dispo-Büro'},  # part of stack, don't query
    {'ip': '192.168.23.42', 'location': 'Fertigung', 'rack_details': 'Verteiler 2', 'model': 'Dell N1548P', 'query': 'yes', 'notes': 'hinter der Beschichtung südl. Aussenwand'},
    {'ip': '192.168.23.43', 'location': 'Fertigung', 'rack_details': 'Verteiler 3.1', 'model': 'Dell N1548P', 'query': 'yes', 'notes': 'Versand-Halle Mitte'},
    {'ip': 'no IP set', 'location': 'Fertigung', 'rack_details': 'Verteiler 3.2', 'model': 'Dell N1524P', 'query': 'no', 'notes': 'Versand-Halle Mitte'},  # part of stack, don't query
    {'ip': '192.168.23.44', 'location': 'Fertigung', 'rack_details': 'Verteiler 4', 'model': 'Dell N1548P', 'query': 'yes', 'notes': 'Magazin unter der Decke'},
    {'ip': '192.168.23.49', 'location': 'Fertigung', 'rack_details': 'SmartBunker', 'model': 'Dell N1548P', 'query': 'yes', 'notes': 'SmartBunker'},
]

# IPs from this list (excluding 'query' == 'no') will be used for operations 
