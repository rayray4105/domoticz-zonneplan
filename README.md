# Domoticz Zonneplan Thuisbatterij Plugin

Een Python plugin voor [Domoticz](https://www.domoticz.com/) die je Zonneplan thuisbatterij uitleest en weergeeft, inclusief ondersteuning voor het **Energy Dashboard**.

## Functionaliteit

De plugin maakt automatisch de volgende devices aan:

| Device | Type | Omschrijving |
|---|---|---|
| Batterij Laadniveau | Percentage | Huidige laadtoestand (SoC) in % |
| Batterij Vermogen | Electric (W) | Huidig laad- of ontlaadvermogen |
| Zonneplan Opgeladen | kWh | Energie in de batterij geladen vandaag |
| Zonneplan Ontladen | kWh | Energie uit de batterij geleverd vandaag |
| Batterij Status | Tekst | Opladen / Ontladen / Inactief / Stand-by |

De kWh-devices zijn van type `General/kWh` (Type 243, Subtype 29) en kunnen direct worden toegevoegd aan het **Energy Dashboard** van Domoticz.

## Vereisten

- Domoticz met Python plugin support (versie 2020.2 of nieuwer)
- Raspberry Pi of andere Linux-machine
- Python 3.7+
- Een actief Zonneplan account met thuisbatterij

## Installatie

### Stap 1 — Bestanden downloaden

```bash
cd /home/pi/domoticz/plugins
git clone https://github.com/rdejager/domoticz-zonneplan Zonneplan
cd Zonneplan
```

### Stap 2 — Eenmalige authenticatie

```bash
python3 setup_auth.py
```

- Voer je Zonneplan e-mailadres in
- Klik op de link in de e-mail die Zonneplan stuurt
- Druk op Enter — het script haalt automatisch je tokens op
- Het bestand `zonneplan_token.json` wordt aangemaakt in de plugin-map

### Stap 3 — Domoticz herstarten

```bash
sudo systemctl restart domoticz
```

### Stap 4 — Hardware toevoegen in Domoticz

1. Ga naar **Setup → Hardware**
2. Klik **Add**
3. Kies type: **Zonneplan Thuisbatterij**
4. Stel het gewenste polling interval in
5. Klik **Add**

De 5 devices verschijnen nu onder **Setup → Devices**.

## Energy Dashboard instellen

1. Ga naar **Setup → More Options → Energy Dashboard**
2. Klik op het potlood bij **Accu / Batterij**
3. Voeg toe:
   - **Zonneplan Opgeladen** → als *Verbruik* (energie die in de accu gaat)
   - **Zonneplan Ontladen** → als *Levering* (energie die uit de accu komt)

## Token vernieuwen

De plugin vernieuwt tokens automatisch via de refresh token. Tokens zijn normaal 30 dagen geldig. Als het vernieuwen mislukt (bijv. na een lange offline periode), voer dan `setup_auth.py` opnieuw uit:

```bash
cd /home/pi/domoticz/plugins/Zonneplan
python3 setup_auth.py
sudo systemctl restart domoticz
```

## Probleemoplossing

**Plugin verschijnt niet in de hardware-lijst**
→ Controleer of Domoticz Python plugins zijn ingeschakeld. Voeg toe aan `domoticz.cfg`:
```
PythonPluginsPath=/home/pi/domoticz/plugins
```

**"Geen token gevonden"**
→ Voer `setup_auth.py` uit en controleer of `zonneplan_token.json` in de plugin-map staat.

**"Geen home_battery_installation gevonden"**
→ Controleer of je Zonneplan account een thuisbatterij-contract heeft.

**Debug inschakelen**
→ Zet *Debug* op *Ja* in de hardware-instellingen. Alle API-data verschijnt dan in het Domoticz logboek.

## Gerelateerd

- [Zonneplan Home Assistant integratie](https://github.com/fsaris/home-assistant-zonneplan-one) — de HA plugin waarop dit gebaseerd is
- [Domoticz Python Plugin Framework](https://www.domoticz.com/wiki/Developing_a_Python_plugin)

## Disclaimer

Dit is een onofficiële community plugin. Zonneplan B.V. is hier niet bij betrokken.
