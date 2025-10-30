#!/bin/bash
# ===============================================
# checkwifi.sh
# -----------------------------------------------
# Controleert of de Raspberry Pi nog verbinding
# met internet heeft via Wi-Fi.
# Als de verbinding is weggevallen, wordt de
# Wi-Fi-interface (wlan0) automatisch herstart.
#
# Maak het bestand met: sudo nano /usr/local/bin/checkwifi.sh
# Maak het script uitvoerbaar door: sudo chmod +x /usr/local/bin/check>
#
# Om dit script automatisch elke 5 minuten te laten
# draaien, voeg de volgende regel toe aan de root-crontab:
#
#   sudo crontab -e
#
# Voeg dan onderaan toe:
#   */5 * * * * /usr/local/bin/checkwifi.sh
#
# Dat betekent:
#   - */5 : elke 5 minuten
#   - * * * * : elk uur, elke dag, elke maand
# ===============================================

# Test of er een internetverbinding is door 1x te pingen
# naar 8.8.8.8 (Google DNS) met een timeout van 1 seconde
if ! ping -c1 -W1 8.8.8.8 > /dev/null; then
    # Geen verbinding → herstart Wi-Fi-interface
    sudo ifconfig wlan0 down
    sleep 2
    sudo ifconfig wlan0 up
fi
