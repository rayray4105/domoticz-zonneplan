# Domoticz Zonneplan Energy Plugin

An unofficial Python plugin for [Domoticz](https://www.domoticz.com/) that integrates your Zonneplan home battery (Nexus) and electricity contract, including support for the **Energy Dashboard**.

> Unofficial community plugin — not affiliated with Zonneplan B.V.

---

## Contents

- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Energy Dashboard setup](#energy-dashboard-setup)
- [Devices](#devices)
- [Token renewal](#token-renewal)
- [Troubleshooting](#troubleshooting)

---

## Features

### Zonneplan Nexus Home Battery

| Device | Unit | Description |
|---|---|---|
| Battery Level | % | Current state of charge (SoC) |
| Battery Power | W | Current charge/discharge power |
| Zonneplan Charged | kWh | Energy charged into battery today |
| Zonneplan Discharged | kWh | Energy delivered from battery today |
| Battery State | text | Charging / Discharging / Idle / Standby |
| Inverter State | text | Current inverter status |
| Battery Model | text | Device model name |
| Battery Cycles | — | Total charge cycle count |
| Backup Capacity | Wh | Usable backup power capacity |
| Earned Today | € | Revenue today |
| Average per Day | € | Average daily revenue |
| Total Earned | € | Total lifetime revenue |
| Result This Month | € | Financial result this month |
| Result Last Month | € | Financial result last month |
| Result This Year | € | Financial result this year |
| Result Last Year | € | Financial result last year |
| Last / First Measurement | datetime | Timestamp of measurement |
| Control Mode | text | home_optimization / dynamic_charging / self_consumption |

**Binary switches (on/off):**
Dynamic Charging · Load Balancing · Load Balancing Overload · Manual Control · Grid Congestion · Home Optimization · Home Optimization Active · Self Consumption · Backup Power Active

---

### Zonneplan Electricity Contract

| Device | Unit | Description |
|---|---|---|
| Current Tariff | €/kWh | Live dynamic tariff (updated every hour) |
| Tariff Group | text | Off-peak / Peak / Normal |
| Sustainability Score | % | Sustainability of current electricity usage |
| Status Tip | text | Tip based on current tariff |
| Current Usage ⁽*⁾ | W | Real-time power consumption |
| Usage Measured At ⁽*⁾ | datetime | Timestamp of usage measurement |
| Status Message ⁽*⁾ | text | Status message from Zonneplan |
| Forecast Tariff +1h to +8h ⁽*⁾ | €/kWh | Expected tariff for the next 8 hours |
| Forecast Tariff Group +1h to +8h ⁽*⁾ | text | Off-peak/Peak/Normal for next hours |

*⁽*⁾ Disabled by default — enable via **Setup → Devices** (click the eye icon).*

---

## Requirements

- Domoticz with Python plugin support (version 2020.2 or newer)
- Python 3.7+
- An active Zonneplan account with a home battery and/or electricity contract

---

## Installation

### Step 1 — Download the plugin

```bash
git clone https://github.com/rayray4105/domoticz-zonneplan.git /home/pi/domoticz/plugins/Zonneplan
cd /home/pi/domoticz/plugins/Zonneplan
```

### Step 2 — One-time authentication

```bash
python3 setup_auth.py
```

- Enter your Zonneplan email address
- Click the link in the email Zonneplan sends you
- Press Enter — the script will automatically retrieve your tokens
- The file `zonneplan_token.json` is saved in the plugin folder

### Step 3 — Restart Domoticz

```bash
sudo systemctl restart domoticz
```

### Step 4 — Add hardware

1. Go to **Setup → Hardware**
2. Click **Add**
3. Select type: **Zonneplan Energie**
4. Set the desired polling interval
5. Click **Add**

The plugin automatically detects which contracts are present (battery and/or electricity) and creates the corresponding devices.

---

## Energy Dashboard setup

1. Go to **Setup → More Options → Energy Dashboard**
2. Click the pencil icon next to **Battery**
3. Add:
   - **Zonneplan Charged** → as *Usage* (energy going into the battery)
   - **Zonneplan Discharged** → as *Return* (energy coming out of the battery)

---

## Token renewal

The plugin automatically renews tokens using the refresh token. If renewal fails (e.g. after a long offline period), run `setup_auth.py` again:

```bash
cd /home/pi/domoticz/plugins/Zonneplan
python3 setup_auth.py
sudo systemctl restart domoticz
```

---

## Troubleshooting

**Plugin does not appear in the hardware list**
Make sure Python plugins are enabled in Domoticz. The folder must be named `Zonneplan` (case-sensitive) and `plugin.py` must be directly inside it.

**"No token found"**
Run `setup_auth.py` and verify that `zonneplan_token.json` exists in the plugin folder.

**Tariffs are not updating**
Run `python3 test_api.py` — it shows the exact key format used by the API so any mismatches are visible.

**Enable debug logging**
Set *Debug* to *Yes* in the hardware settings. All raw API data will appear in **Setup → Log**.

**Test the API without Domoticz**
```bash
cd /home/pi/domoticz/plugins/Zonneplan
python3 test_api.py
```
Shows all raw and converted values for both battery and electricity contract.

---

## Related

- [Zonneplan Home Assistant integration](https://github.com/fsaris/home-assistant-zonneplan-one) — the HA plugin this is based on
- [Domoticz Python Plugin Framework](https://www.domoticz.com/wiki/Developing_a_Python_plugin)
