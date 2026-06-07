"""
<plugin key="ZonneplanBattery" name="Zonneplan Thuisbatterij" author="rdejager"
        version="2.0.0" externallink="https://github.com/rayray4105/domoticz-zonneplan">
    <description>
        <h2>Zonneplan Thuisbatterij (Nexus)</h2><br/>
        Toont alle beschikbare sensorwaarden van je Zonneplan thuisbatterij in Domoticz,
        inclusief ondersteuning voor het Energy Dashboard.<br/><br/>
        <b>Eerste gebruik:</b> voer <i>setup_auth.py</i> uit en kopieer
        <i>zonneplan_token.json</i> naar de plugin-map.<br/><br/>
        <b>Devices die worden aangemaakt:</b> laadniveau, vermogen, opgeladen/ontladen kWh,
        financiële resultaten, cycli, statussen, binary schakelaars en control mode.
    </description>
    <params>
        <param field="Mode1" label="Polling interval" width="150px" required="true">
            <options>
                <option label="30 seconden" value="30"/>
                <option label="1 minuut" value="60" default="true"/>
                <option label="2 minuten" value="120"/>
                <option label="5 minuten" value="300"/>
            </options>
        </param>
        <param field="Mode6" label="Debug" width="100px">
            <options>
                <option label="Nee" value="0" default="true"/>
                <option label="Ja" value="1"/>
            </options>
        </param>
    </params>
</plugin>
"""

import Domoticz
import json
import os
import time
import urllib.request
import urllib.error

BASE_URL = "https://app-api.zonneplan.nl"
PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN_FILE = os.path.join(PLUGIN_DIR, "zonneplan_token.json")

HEADERS = {
    "Content-Type": "application/json;charset=utf-8",
    "x-app-version": "5.10.1",
    "x-app-environment": "production",
    "x-ha-integration": "domoticz-zonneplan/2.0.0",
    "User-Agent": "domoticz-zonneplan/2.0.0",
}

# --- Device unit nummers ---
# Hoofd sensoren
UNIT_SOC            = 1   # Laadniveau (%)
UNIT_POWER          = 2   # Vermogen (W)
UNIT_CHARGED        = 3   # Vandaag opgeladen (kWh)
UNIT_DISCHARGED     = 4   # Vandaag ontladen (kWh)
UNIT_STATE          = 5   # Batterijstatus (tekst)
UNIT_INVERTER       = 6   # Inverter status (tekst)
UNIT_MODEL          = 7   # Apparaatmodel (tekst)
UNIT_CYCLES         = 8   # Cycli
UNIT_LAST_MEAS      = 9   # Laatste meting (tekst)
UNIT_FIRST_MEAS     = 10  # Eerste meting (tekst)
UNIT_BACKUP_CAP     = 11  # Backup capaciteit (Wh)

# Financieel
UNIT_TODAY_EUR      = 12  # Verdiend vandaag (€)
UNIT_AVG_EUR        = 13  # Gemiddeld per dag (€)
UNIT_TOTAL_EUR      = 14  # Totaal verdiend (€)
UNIT_THIS_MONTH_EUR = 15  # Resultaat deze maand (€)
UNIT_LAST_MONTH_EUR = 16  # Resultaat vorige maand (€)
UNIT_THIS_YEAR_EUR  = 17  # Resultaat dit jaar (€)
UNIT_LAST_YEAR_EUR  = 18  # Resultaat vorig jaar (€)

# Binary sensoren (aan/uit)
UNIT_DYN_CHARGING   = 20  # Dynamic charging ingeschakeld
UNIT_DYN_LB_OVL     = 21  # Dynamic load balancing overload actief
UNIT_DYN_LB_ON      = 22  # Dynamic load balancing ingeschakeld
UNIT_MANUAL_CTRL    = 23  # Handmatige bediening ingeschakeld
UNIT_GRID_CONG      = 24  # Netcongestie actief
UNIT_HOME_OPT_ACT   = 25  # Home optimalisatie actief
UNIT_HOME_OPT_ON    = 26  # Home optimalisatie ingeschakeld
UNIT_SELF_CONS      = 27  # Zelfconsumptie ingeschakeld
UNIT_BACKUP_ACT     = 28  # Backup stroom actief

# Control mode
UNIT_CTRL_MODE      = 30  # Besturingsmodus (tekst)

BATTERY_STATE_NL = {
    "charging":    "Opladen",
    "discharging": "Ontladen",
    "idle":        "Inactief",
    "standby":     "Stand-by",
    "full":        "Vol",
    "empty":       "Leeg",
}


class BasePlugin:
    def __init__(self):
        self._token = None
        self._heartbeat_count = 0
        self._poll_ticks = 2
        self._debug = False
        self._contract_uuid = None
        self._connection_uuid = None

    # ------------------------------------------------------------------
    # Domoticz lifecycle
    # ------------------------------------------------------------------

    def onStart(self):
        self._debug = Parameters["Mode6"] == "1"
        if self._debug:
            Domoticz.Debugging(1)

        try:
            self._poll_ticks = max(1, int(Parameters["Mode1"]) // 30)
        except (ValueError, KeyError):
            self._poll_ticks = 2

        Domoticz.Heartbeat(30)
        Domoticz.Log(f"Zonneplan plugin v2.0 gestart (poll elke {self._poll_ticks * 30}s)")

        self._create_devices()
        self._load_token()

        if self._token:
            self._update_data()
        else:
            Domoticz.Error(
                "Geen token gevonden. Voer setup_auth.py uit en kopieer "
                "zonneplan_token.json naar de plugin-map."
            )

    def onStop(self):
        Domoticz.Log("Zonneplan plugin gestopt.")

    def onHeartbeat(self):
        self._heartbeat_count += 1
        if self._heartbeat_count >= self._poll_ticks:
            self._heartbeat_count = 0
            self._update_data()

    # ------------------------------------------------------------------
    # Devices aanmaken
    # ------------------------------------------------------------------

    def _create_devices(self):
        specs = [
            # (unit, naam, TypeName, Type, Subtype)
            # TypeName heeft voorrang; Type/Subtype alleen als TypeName leeg is
            (UNIT_SOC,            "Batterij Laadniveau",              "Percentage",  0,   0),
            (UNIT_POWER,          "Batterij Vermogen",                "",            248, 1),
            (UNIT_CHARGED,        "Zonneplan Opgeladen",              "",            243, 29),
            (UNIT_DISCHARGED,     "Zonneplan Ontladen",               "",            243, 29),
            (UNIT_STATE,          "Batterij Status",                  "Text",        0,   0),
            (UNIT_INVERTER,       "Inverter Status",                  "Text",        0,   0),
            (UNIT_MODEL,          "Batterij Model",                   "Text",        0,   0),
            (UNIT_CYCLES,         "Batterij Cycli",                   "Custom",      0,   0),
            (UNIT_LAST_MEAS,      "Laatste Meting",                   "Text",        0,   0),
            (UNIT_FIRST_MEAS,     "Eerste Meting",                    "Text",        0,   0),
            (UNIT_BACKUP_CAP,     "Backup Capaciteit",                "Custom",      0,   0),
            (UNIT_TODAY_EUR,      "Verdiend Vandaag",                 "Custom",      0,   0),
            (UNIT_AVG_EUR,        "Gemiddeld per Dag",                "Custom",      0,   0),
            (UNIT_TOTAL_EUR,      "Totaal Verdiend",                  "Custom",      0,   0),
            (UNIT_THIS_MONTH_EUR, "Resultaat Deze Maand",             "Custom",      0,   0),
            (UNIT_LAST_MONTH_EUR, "Resultaat Vorige Maand",           "Custom",      0,   0),
            (UNIT_THIS_YEAR_EUR,  "Resultaat Dit Jaar",               "Custom",      0,   0),
            (UNIT_LAST_YEAR_EUR,  "Resultaat Vorig Jaar",             "Custom",      0,   0),
            (UNIT_DYN_CHARGING,   "Dynamic Charging",                 "Switch",      0,   0),
            (UNIT_DYN_LB_OVL,     "Load Balancing Overload",          "Switch",      0,   0),
            (UNIT_DYN_LB_ON,      "Load Balancing",                   "Switch",      0,   0),
            (UNIT_MANUAL_CTRL,    "Handmatige Bediening",             "Switch",      0,   0),
            (UNIT_GRID_CONG,      "Netcongestie",                     "Switch",      0,   0),
            (UNIT_HOME_OPT_ACT,   "Home Optimalisatie Actief",        "Switch",      0,   0),
            (UNIT_HOME_OPT_ON,    "Home Optimalisatie",               "Switch",      0,   0),
            (UNIT_SELF_CONS,      "Zelfconsumptie",                   "Switch",      0,   0),
            (UNIT_BACKUP_ACT,     "Backup Stroom Actief",             "Switch",      0,   0),
            (UNIT_CTRL_MODE,      "Besturingsmodus",                  "Text",        0,   0),
        ]

        for unit, name, typename, devtype, subtype in specs:
            if unit not in Devices:
                if typename:
                    Domoticz.Device(Name=name, Unit=unit, TypeName=typename).Create()
                else:
                    Domoticz.Device(Name=name, Unit=unit, Type=devtype, Subtype=subtype).Create()
                Domoticz.Log(f"Device aangemaakt: {name}")

    # ------------------------------------------------------------------
    # Token beheer
    # ------------------------------------------------------------------

    def _load_token(self):
        if not os.path.exists(TOKEN_FILE):
            Domoticz.Error(f"Token bestand niet gevonden: {TOKEN_FILE}")
            return
        try:
            with open(TOKEN_FILE) as f:
                self._token = json.load(f)
            Domoticz.Log("Zonneplan token geladen.")
        except Exception as e:
            Domoticz.Error(f"Token laden mislukt: {e}")

    def _save_token(self):
        try:
            with open(TOKEN_FILE, "w") as f:
                json.dump(self._token, f, indent=2)
        except Exception as e:
            Domoticz.Error(f"Token opslaan mislukt: {e}")

    def _ensure_valid_token(self):
        if not self._token:
            return False
        expires_in = self._token.get("expires_in", 3600)
        obtained_at = self._token.get("obtained_at", 0)
        if (time.time() - obtained_at) < (expires_in - 300):
            return True
        Domoticz.Log("Token verlopen, vernieuwen...")
        try:
            data = self._post("/oauth/token", {
                "grant_type": "refresh_token",
                "refresh_token": self._token["refresh_token"],
            })
            self._token.update(data.get("data", data))
            self._token["obtained_at"] = time.time()
            self._save_token()
            Domoticz.Log("Token vernieuwd.")
            return True
        except Exception as e:
            Domoticz.Error(f"Token vernieuwen mislukt: {e}")
            return False

    # ------------------------------------------------------------------
    # HTTP
    # ------------------------------------------------------------------

    def _get(self, path):
        url = BASE_URL + path
        h = dict(HEADERS)
        h["Authorization"] = f"Bearer {self._token['access_token']}"
        req = urllib.request.Request(url, headers=h)
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _post(self, path, data):
        url = BASE_URL + path
        body = json.dumps(data).encode("utf-8")
        req = urllib.request.Request(url, data=body, headers=HEADERS, method="POST")
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))

    # ------------------------------------------------------------------
    # Data ophalen
    # ------------------------------------------------------------------

    def _update_data(self):
        if not self._ensure_valid_token():
            return

        try:
            me = self._get("/user-accounts/me")
        except urllib.error.HTTPError as e:
            Domoticz.Error(f"API fout {e.code}: {e.reason}")
            return
        except Exception as e:
            Domoticz.Error(f"Verbindingsfout: {e}")
            return

        battery, conn_uuid = self._find_battery_contract(me)
        if not battery:
            Domoticz.Error("Geen home_battery_installation gevonden in Zonneplan account.")
            return

        self._contract_uuid = battery.get("uuid")
        self._connection_uuid = conn_uuid

        self._update_devices(battery.get("meta", {}))
        self._update_binary(battery.get("meta", {}))
        self._update_charts()
        self._update_control_mode()

    def _find_battery_contract(self, me_data):
        connections = me_data.get("data", {}).get("connections", [])
        for conn in connections:
            for contract in conn.get("contracts", []):
                if contract.get("contract_type") == "home_battery_installation":
                    return contract, conn.get("uuid")
        return None, None

    # ------------------------------------------------------------------
    # Device updates
    # ------------------------------------------------------------------

    def _update_devices(self, meta):
        if self._debug:
            Domoticz.Log(f"meta: {json.dumps(meta)}")

        def get(key, factor=1):
            v = meta.get(key)
            return round(float(v) * factor, 4) if v is not None else None

        soc     = get("state_of_charge", 0.1)
        power   = get("power_ac")
        prod    = get("production_day", 0.001)
        deliv   = get("delivery_day", 0.001)
        today   = get("total_day", 0.0000001)
        avg     = get("average_day", 0.0000001)
        total   = get("total_earned", 0.0000001)
        cycles  = get("cycle_count")
        backup  = get("backup_power_usable_capacity_wh")

        if soc    is not None: Devices[UNIT_SOC].Update(nValue=0, sValue=str(soc))
        if power  is not None: Devices[UNIT_POWER].Update(nValue=0, sValue=f"{round(power)};0")
        if prod   is not None: Devices[UNIT_CHARGED].Update(nValue=0, sValue=f"0;{prod}")
        if deliv  is not None: Devices[UNIT_DISCHARGED].Update(nValue=0, sValue=f"0;{deliv}")
        if today  is not None: Devices[UNIT_TODAY_EUR].Update(nValue=0, sValue=str(round(today, 2)))
        if avg    is not None: Devices[UNIT_AVG_EUR].Update(nValue=0, sValue=str(round(avg, 2)))
        if total  is not None: Devices[UNIT_TOTAL_EUR].Update(nValue=0, sValue=str(round(total, 2)))
        if cycles is not None: Devices[UNIT_CYCLES].Update(nValue=0, sValue=str(int(cycles)))
        if backup is not None: Devices[UNIT_BACKUP_CAP].Update(nValue=0, sValue=str(int(backup)))

        battery_state = meta.get("battery_state", "")
        state_nl = BATTERY_STATE_NL.get(battery_state, battery_state or "Onbekend")
        Devices[UNIT_STATE].Update(nValue=0, sValue=state_nl)

        inverter = meta.get("inverter_state") or ""
        Devices[UNIT_INVERTER].Update(nValue=0, sValue=inverter or "Onbekend")

        model = meta.get("host_device_model_name") or ""
        if model:
            Devices[UNIT_MODEL].Update(nValue=0, sValue=model)

        last = meta.get("last_measured_at") or ""
        if last:
            Devices[UNIT_LAST_MEAS].Update(nValue=0, sValue=str(last))

        first = meta.get("first_measured_at") or ""
        if first:
            Devices[UNIT_FIRST_MEAS].Update(nValue=0, sValue=str(first))

        Domoticz.Log(
            f"SoC: {soc}% | {power}W | Opgeladen: {prod}kWh | Ontladen: {deliv}kWh | {state_nl}"
        )

    def _update_binary(self, meta):
        binary_map = {
            UNIT_DYN_CHARGING:  "dynamic_charging_enabled",
            UNIT_DYN_LB_OVL:   "load_balancing_overload_active",
            UNIT_DYN_LB_ON:    "load_balancing_enabled",
            UNIT_MANUAL_CTRL:  "manual_control_enabled",
            UNIT_GRID_CONG:    "grid_congestion_active",
            UNIT_HOME_OPT_ACT: "home_optimization_active",
            UNIT_HOME_OPT_ON:  "home_optimization_enabled",
            UNIT_SELF_CONS:    "self_consumption_enabled",
            UNIT_BACKUP_ACT:   "backup_power_active",
        }
        for unit, key in binary_map.items():
            val = meta.get(key)
            if val is not None and unit in Devices:
                nval = 1 if val else 0
                sval = "On" if val else "Off"
                Devices[unit].Update(nValue=nval, sValue=sval)

    def _update_charts(self):
        if not self._contract_uuid:
            return
        try:
            data = self._get(
                f"/contracts/{self._contract_uuid}/home_battery_installation/charts/year"
            )
            charts = data.get("data", {})

            def eur(section, key="total_result"):
                v = charts.get(section, {}).get(key)
                return round(float(v) * 0.0000001, 2) if v is not None else None

            this_month = eur("this_month")
            last_month = eur("last_month")
            this_year  = eur("this_year")
            last_year  = eur("last_year")

            if this_month is not None: Devices[UNIT_THIS_MONTH_EUR].Update(nValue=0, sValue=str(this_month))
            if last_month is not None: Devices[UNIT_LAST_MONTH_EUR].Update(nValue=0, sValue=str(last_month))
            if this_year  is not None: Devices[UNIT_THIS_YEAR_EUR].Update(nValue=0, sValue=str(this_year))
            if last_year  is not None: Devices[UNIT_LAST_YEAR_EUR].Update(nValue=0, sValue=str(last_year))

        except Exception as e:
            Domoticz.Error(f"Charts ophalen mislukt: {e}")

    def _update_control_mode(self):
        if not self._contract_uuid:
            return
        try:
            data = self._get(
                f"/api/contracts/{self._contract_uuid}/home-battery/control-mode"
            )
            mode = data.get("data", {}).get("control_mode") or ""
            if mode and UNIT_CTRL_MODE in Devices:
                Devices[UNIT_CTRL_MODE].Update(nValue=0, sValue=str(mode))
        except Exception as e:
            Domoticz.Error(f"Control mode ophalen mislukt: {e}")


# Domoticz entry points
_plugin = BasePlugin()

def onStart():    _plugin.onStart()
def onStop():     _plugin.onStop()
def onHeartbeat(): _plugin.onHeartbeat()
