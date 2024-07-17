# DellN1500_MAC-Finder
Script that connects with a bunch of Dell N1500 Series networking switches via SSH to find a previously specified MAC address that is connected with the switches.

The script uses python as I wasn't able to get the automated SSH access to work in a powershell script using Kitty or PoshSSH.

I have created an executable using PyInstaller which I would strongly recommend. You'll get a single executable that you can use on any system, regardless of whether it has python or the imported libraries installed as PyInstaller bundles everything up. 
That executable will then launch a console window where you can comfortably enter the password and the MAC that you're searching for.


![Demo showing the executable generated from the script using PyInstaller](https://github.com/Splintix98/DellN1500_MAC-Finder/blob/main/Demo.png)
