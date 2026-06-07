# Domoticz Zonneplan Energie Plugin

Een Python plugin voor [Domoticz](https://www.domoticz.com/) die je Zonneplan thuisbatterij (Nexus) en elektriciteitscontract integreert, inclusief ondersteuning voor het **Energy Dashboard**.

> Onofficiële community plugin — niet gelieerd aan Zonneplan B.V.

---

## Inhoud

- [Functionaliteit](#functionaliteit)
- [Vereisten](#vereisten)
- [Installatie](#installatie)
- [Energy Dashboard instellen](#energy-dashboard-instellen)
- [Devices](#devices)
- [Token vernieuwen](#token-vernieuwen)
- [Probleemoplossing](#probleemoplossing)

---

## Functionaliteit

### Zonneplan Nexus Thuisbatterij

| Device | Eenheid | Omschrijving |
|---|---|---|
| Batterij Laadniveau | % | Huidige laadtoestand (SoC) |
| Batterij Vermogen | W | Huidig laad-/ontlaadvermogen |
| Zonneplan Opgeladen | kWh | Energie in de batterij geladen vandaag |
| Zonneplan Ontladen | kWh | Energie uit de batterij geleverd vandaag |
| Batterij Status | tekst | Opladen / Ontladen / Inactief / Stand-by |
| Inverter Status | tekst | Status van de inverter |
| Batterij Model | tekst | Apparaatmodel |
| Batterij Cycli | — | Totaal aantal laadcycli |
| Backup Capaciteit | Wh | Bruikbare backup-capaciteit |
| Verdiend Vandaag | € | Opbrengst vandaag |
| Gemiddeld per Dag | € | Gemiddelde dagopbrengst |
| Totaal Verdiend | € | Totale opbrengst |
| Resultaat Deze Maand | € | Financieel resultaat deze maand |
| Resultaat Vorige Maand | € | Financieel resultaat vorige maand |
| Resultaat Dit Jaar | € | Financieel resultaat dit jaar |
| Resultaat Vorig Jaar | € | Financieel resultaat vorig jaar |
| Laatste / Eerste Meting | datum | Tijdstip van meting |
| Besturingsmodus | tekst | home_optimization / dynamic_charging / self_consumption |

**Binary schakelaars (aan/uit):**
Dynamic Charging · Load Balancing · Load Balancing Overload · Handmatige Bediening · Netcongestie · Home Optimalisatie · Home Optimalisatie Actief · Zelfconsumptie · Backup Stroom Actief

---

### Zonneplan Elektriciteitscontract

| Device | Eenheid | Omschrijving |
|---|---|---|
| Huidig Tarief | €/kWh | Actueel dynamisch tarief (update elk uur) |
| Tariefgroep | tekst | Dal / Piek / Normaal |
| Duurzaamheidsscore | % | Duurzaamheid van huidig stroomverbruik |
| Status Tip | tekst | Tip op basis van huidig tarief |
| Huidig Verbruik ⁽*⁾ | W | Gemeten verbruik op dit moment |
| Verbruik Gemeten Om ⁽*⁾ | datum | Tijdstip van verbruiksmeting |
| Status Bericht ⁽*⁾ | tekst | Statusmelding van Zonneplan |
| Forecast Tarief +1u t/m +8u ⁽*⁾ | €/kWh | Verwacht tarief komende uren |
| Forecast Tariefgroep +1u t/m +8u ⁽*⁾ | tekst | Dal/Piek/Normaal komende uren |

*⁽*⁾ Standaard uitgeschakeld — activeer via **Setup → Devices → gebruik het oog-icoon**.*

---

## Vereisten

- Domoticz met Python plugin support (versie 2020.2 of nieuwer)
- Python 3.7+
- Een actief Zonneplan account met thuisbatterij en/of elektriciteitscontract

---

## Installatie

### Stap 1 — Plugin downloaden

```bash
git clone https://github.com/rayray4105/domoticz-zonneplan.git /home/pi/domoticz/plugins/Zonneplan
cd /home/pi/domoticz/plugins/Zonneplan
```

### Stap 2 — Eenmalige authenticatie

```bash
python3 setup_auth.py
```

- Voer je Zonneplan e-mailadres in
- Klik op de link in de e-mail die Zonneplan stuurt
- Druk op Enter — het script haalt automatisch je tokens op
- Het bestand `zonneplan_token.json` wordt opgeslagen in de plugin-map

### Stap 3 — Domoticz herstarten

```bash
sudo systemctl restart domoticz
```

### Stap 4 — Hardware toevoegen

1. Ga naar **Setup → Hardware**
2. Klik **Add**
3. Kies type: **Zonneplan Energie**
4. Stel het gewenste polling interval in
5. Klik **Add**

De plugin detecteert automatisch welke contracten aanwezig zijn (batterij en/of elektriciteit) en maakt de bijbehorende devices aan.

---

## Energy Dashboard instellen

1. Ga naar **Setup → More Options → Energy Dashboard**
2. Klik op het potlood bij **Accu / Batterij**
3. Voeg toe:
   - **Zonneplan Opgeladen** → als *Verbruik* (energie die in de accu gaat)
   - **Zonneplan Ontladen** → als *Levering* (energie die uit de accu komt)

---

## Token vernieuwen

De plugin vernieuwt tokens automatisch via de refresh token. Als het vernieuwen mislukt (bijv. na een lange offline periode), voer dan `setup_auth.py` opnieuw uit:

```bash
cd /home/pi/domoticz/plugins/Zonneplan
python3 setup_auth.py
sudo systemctl restart domoticz
```

---

## Probleemoplossing

**Plugin verschijnt niet in de hardware-lijst**
Controleer of Python plugins zijn ingeschakeld in Domoticz. Zorg dat de map heet `Zonneplan` (hoofdlettergevoelig) en dat `plugin.py` er direct in staat.

**"Geen token gevonden"**
Voer `setup_auth.py` uit en controleer of `zonneplan_token.json` in de plugin-map staat.

**Tarieven komen niet binnen**
Voer `python3 test_api.py` uit. Het script toont de exacte sleutelnotatie van de API zodat eventuele afwijkingen zichtbaar worden.

**Debug inschakelen**
Zet *Debug* op *Ja* in de hardware-instellingen. Alle ruwe API-data verschijnt dan in **Setup → Log**.

**API testen zonder Domoticz**
```bash
cd /home/pi/domoticz/plugins/Zonneplan
python3 test_api.py
```
Toont alle ruwe en geconverteerde waarden van batterij én elektriciteitscontract.

---

## Gerelateerd

- [Zonneplan Home Assistant integratie](https://github.com/fsaris/home-assistant-zonneplan-one) — de HA plugin waarop dit gebaseerd is
- [Domoticz Python Plugin Framework](https://www.domoticz.com/wiki/Developing_a_Python_plugin)
