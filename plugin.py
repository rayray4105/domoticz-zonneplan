"""
<plugin key="ZonneplanEnergy" name="Zonneplan Energie" author="rayray4105"
        version="3.1.0" externallink="https://github.com/rayray4105/domoticz-zonneplan">
    <description>
        <h2>Zonneplan Energie</h2><br/>
        Integreert Zonneplan thuisbatterij (Nexus) en elektriciteitscontract in Domoticz,
        inclusief ondersteuning voor het Energy Dashboard.<br/><br/>
        <b>Eerste gebruik:</b> voer <i>setup_auth.py</i> uit en kopieer
        <i>zonneplan_token.json</i> naar de plugin-map.<br/><br/>
        Niet alle devices zijn actief — activeer ze via Setup &gt; Devices indien gewenst.
    </description>
    <params>
        <param field="Mode1" label="Polling interval" width="150px" required="true">
            <options>
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
from datetime import datetime, timezone

BASE_URL = "https://app-api.zonneplan.nl"
PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN_FILE = os.path.join(PLUGIN_DIR, "zonneplan_token.json")

HEADERS = {
    "Content-Type": "application/json;charset=utf-8",
    "x-app-version": "5.10.1",
    "x-app-environment": "production",
    "x-ha-integration": "domoticz-zonneplan/3.0.0",
    "User-Agent": "domoticz-zonneplan/3.0.0",
}

# ============================================================
# Device unit nummers
# ============================================================

# --- Batterij (1-30) ---
UNIT_SOC            = 1
UNIT_POWER          = 2
UNIT_CHARGED        = 3
UNIT_DISCHARGED     = 4
UNIT_STATE          = 5
UNIT_INVERTER       = 6
UNIT_MODEL          = 7
UNIT_CYCLES         = 8
UNIT_LAST_MEAS      = 9
UNIT_FIRST_MEAS     = 10
UNIT_BACKUP_CAP     = 11
UNIT_TODAY_EUR      = 12
UNIT_AVG_EUR        = 13
UNIT_TOTAL_EUR      = 14
UNIT_THIS_MONTH_EUR = 15
UNIT_LAST_MONTH_EUR = 16
UNIT_THIS_YEAR_EUR  = 17
UNIT_LAST_YEAR_EUR  = 18
UNIT_DYN_CHARGING   = 20
UNIT_DYN_LB_OVL     = 21
UNIT_DYN_LB_ON      = 22
UNIT_MANUAL_CTRL    = 23
UNIT_GRID_CONG      = 24
UNIT_HOME_OPT_ACT   = 25
UNIT_HOME_OPT_ON    = 26
UNIT_SELF_CONS      = 27
UNIT_BACKUP_ACT     = 28
UNIT_CTRL_MODE      = 30

# --- Elektriciteit (40-70) ---
UNIT_ELEC_TARIFF        = 40   # Huidig tarief (€/kWh)
UNIT_ELEC_TARIFF_GROUP  = 41   # Huidige tariefgroep
UNIT_ELEC_USAGE         = 42   # Huidig verbruik (W)   [standaard uitgeschakeld]
UNIT_ELEC_USAGE_AT      = 43   # Verbruik gemeten om   [standaard uitgeschakeld]
UNIT_ELEC_SUSTAIN       = 44   # Duurzaamheidsscore (%)
UNIT_ELEC_STATUS_MSG    = 45   # Statusbericht         [standaard uitgeschakeld]
UNIT_ELEC_STATUS_TIP    = 46   # Statustip
# Forecast tarieven uur +1 t/m +8                       [standaard uitgeschakeld]
UNIT_ELEC_FC_T1         = 47
UNIT_ELEC_FC_T2         = 48
UNIT_ELEC_FC_T3         = 49
UNIT_ELEC_FC_T4         = 50
UNIT_ELEC_FC_T5         = 51
UNIT_ELEC_FC_T6         = 52
UNIT_ELEC_FC_T7         = 53
UNIT_ELEC_FC_T8         = 54
# Forecast tariefgroepen uur +1 t/m +8                  [standaard uitgeschakeld]
UNIT_ELEC_FC_G1         = 55
UNIT_ELEC_FC_G2         = 56
UNIT_ELEC_FC_G3         = 57
UNIT_ELEC_FC_G4         = 58
UNIT_ELEC_FC_G5         = 59
UNIT_ELEC_FC_G6         = 60
UNIT_ELEC_FC_G7         = 61
UNIT_ELEC_FC_G8         = 62

BATTERY_STATE_NL = {
    "charging":    "Opladen",
    "discharging": "Ontladen",
    "idle":        "Inactief",
    "standby":     "Stand-by",
    "full":        "Vol",
    "empty":       "Leeg",
}

TARIFF_GROUP_NL = {
    "off_peak": "Dal",
    "peak":     "Piek",
    "normal":   "Normaal",
}


class BasePlugin:
    def __init__(self):
        self._token = None
        self._heartbeat_count = 0
        self._poll_ticks = 2
        self._debug = False

        # Batterij
        self._battery_contract_uuid = None
        self._battery_connection_uuid = None
        self._has_battery = False

        # Elektriciteit
        self._elec_connection_uuid = None
        self._has_electricity = False
        self._last_summary_hour = -1   # tarieven alleen vernieuwen bij nieuw uur

        # Rate limiting (discussie #89): bij 429 pauzeren we minimaal 60s
        self._rate_limited_until = 0

    # ------------------------------------------------------------------
    # Domoticz lifecycle
    # ------------------------------------------------------------------

    def onStart(self):
        self._debug = Parameters["Mode6"] == "1"
        if self._debug:
            Domoticz.Debugging(1)

        try:
            self._poll_ticks = max(2, int(Parameters["Mode1"]) // 30)  # min 60s
        except (ValueError, KeyError):
            self._poll_ticks = 2

        Domoticz.Heartbeat(30)
        Domoticz.Log(f"Zonneplan plugin v3.1 gestart (poll elke {self._poll_ticks * 30}s)")

        self._create_devices()
        self._load_token()

        if self._token:
            self._discover_contracts()
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
    # Contract detectie
    # ------------------------------------------------------------------

    def _discover_contracts(self):
        if not self._ensure_valid_token():
            return
        try:
            me = self._get("/user-accounts/me")
        except Exception as e:
            Domoticz.Error(f"Contract detectie mislukt: {e}")
            return

        connections = me.get("data", {}).get("connections", [])
        for conn in connections:
            conn_uuid = conn.get("uuid", "")
            for contract in conn.get("contracts", []):
                ctype = contract.get("contract_type", "")

                if ctype == "home_battery_installation" and not self._has_battery:
                    self._battery_contract_uuid = contract.get("uuid")
                    self._battery_connection_uuid = conn_uuid
                    self._has_battery = True
                    Domoticz.Log(f"Batterijcontract gevonden: {self._battery_contract_uuid[:16]}...")

                if ctype in ("electricity", "electricity_without_feed_in") and not self._has_electricity:
                    self._elec_connection_uuid = conn_uuid
                    self._has_electricity = True
                    Domoticz.Log(f"Elektriciteitscontract gevonden: verbinding {conn_uuid[:16]}...")

        if not self._has_battery:
            Domoticz.Log("Geen batterijcontract gevonden — batterij-devices worden overgeslagen.")
        if not self._has_electricity:
            Domoticz.Log("Geen elektriciteitscontract gevonden — elektriciteits-devices worden overgeslagen.")

    # ------------------------------------------------------------------
    # Device aanmaken
    # ------------------------------------------------------------------

    def _create_devices(self):
        # Batterij devices
        battery_specs = [
            (UNIT_SOC,            "Batterij Laadniveau",           "",         0,   0,   True),
            (UNIT_POWER,          "Batterij Vermogen",             "",         248, 1,   True),
            (UNIT_CHARGED,        "Zonneplan Opgeladen",           "",         243, 29,  True),
            (UNIT_DISCHARGED,     "Zonneplan Ontladen",            "",         243, 29,  True),
            (UNIT_STATE,          "Batterij Status",               "Text",     0,   0,   True),
            (UNIT_INVERTER,       "Inverter Status",               "Text",     0,   0,   True),
            (UNIT_MODEL,          "Batterij Model",                "Text",     0,   0,   True),
            (UNIT_CYCLES,         "Batterij Cycli",                "Custom",   0,   0,   True),
            (UNIT_LAST_MEAS,      "Laatste Meting",                "Text",     0,   0,   True),
            (UNIT_FIRST_MEAS,     "Eerste Meting",                 "Text",     0,   0,   True),
            (UNIT_BACKUP_CAP,     "Backup Capaciteit",             "Custom",   0,   0,   True),
            (UNIT_TODAY_EUR,      "Verdiend Vandaag",              "Custom",   0,   0,   True),
            (UNIT_AVG_EUR,        "Gemiddeld per Dag",             "Custom",   0,   0,   True),
            (UNIT_TOTAL_EUR,      "Totaal Verdiend",               "Custom",   0,   0,   True),
            (UNIT_THIS_MONTH_EUR, "Resultaat Deze Maand",          "Custom",   0,   0,   True),
            (UNIT_LAST_MONTH_EUR, "Resultaat Vorige Maand",        "Custom",   0,   0,   True),
            (UNIT_THIS_YEAR_EUR,  "Resultaat Dit Jaar",            "Custom",   0,   0,   True),
            (UNIT_LAST_YEAR_EUR,  "Resultaat Vorig Jaar",          "Custom",   0,   0,   True),
            (UNIT_DYN_CHARGING,   "Dynamic Charging",              "Switch",   0,   0,   True),
            (UNIT_DYN_LB_OVL,     "Load Balancing Overload",       "Switch",   0,   0,   True),
            (UNIT_DYN_LB_ON,      "Load Balancing",                "Switch",   0,   0,   True),
            (UNIT_MANUAL_CTRL,    "Handmatige Bediening",          "Switch",   0,   0,   True),
            (UNIT_GRID_CONG,      "Netcongestie",                  "Switch",   0,   0,   True),
            (UNIT_HOME_OPT_ACT,   "Home Optimalisatie Actief",     "Switch",   0,   0,   True),
            (UNIT_HOME_OPT_ON,    "Home Optimalisatie",            "Switch",   0,   0,   True),
            (UNIT_SELF_CONS,      "Zelfconsumptie",                "Switch",   0,   0,   True),
            (UNIT_BACKUP_ACT,     "Backup Stroom Actief",          "Switch",   0,   0,   True),
            (UNIT_CTRL_MODE,      "Besturingsmodus",               "Text",     0,   0,   True),
        ]

        # Elektriciteit devices (enabled=False = standaard uitgeschakeld in Domoticz)
        elec_specs = [
            (UNIT_ELEC_TARIFF,       "Huidig Tarief",              "Custom",   0,   0,   True),
            (UNIT_ELEC_TARIFF_GROUP, "Tariefgroep",                "Text",     0,   0,   True),
            (UNIT_ELEC_USAGE,        "Huidig Verbruik",            "",         248, 1,   False),
            (UNIT_ELEC_USAGE_AT,     "Verbruik Gemeten Om",        "Text",     0,   0,   False),
            (UNIT_ELEC_SUSTAIN,      "Duurzaamheidsscore",         "Percentage", 0, 0,  True),
            (UNIT_ELEC_STATUS_MSG,   "Status Bericht",             "Text",     0,   0,   False),
            (UNIT_ELEC_STATUS_TIP,   "Status Tip",                 "Text",     0,   0,   True),
            (UNIT_ELEC_FC_T1,        "Forecast Tarief +1u",        "Custom",   0,   0,   False),
            (UNIT_ELEC_FC_T2,        "Forecast Tarief +2u",        "Custom",   0,   0,   False),
            (UNIT_ELEC_FC_T3,        "Forecast Tarief +3u",        "Custom",   0,   0,   False),
            (UNIT_ELEC_FC_T4,        "Forecast Tarief +4u",        "Custom",   0,   0,   False),
            (UNIT_ELEC_FC_T5,        "Forecast Tarief +5u",        "Custom",   0,   0,   False),
            (UNIT_ELEC_FC_T6,        "Forecast Tarief +6u",        "Custom",   0,   0,   False),
            (UNIT_ELEC_FC_T7,        "Forecast Tarief +7u",        "Custom",   0,   0,   False),
            (UNIT_ELEC_FC_T8,        "Forecast Tarief +8u",        "Custom",   0,   0,   False),
            (UNIT_ELEC_FC_G1,        "Forecast Tariefgroep +1u",   "Text",     0,   0,   False),
            (UNIT_ELEC_FC_G2,        "Forecast Tariefgroep +2u",   "Text",     0,   0,   False),
            (UNIT_ELEC_FC_G3,        "Forecast Tariefgroep +3u",   "Text",     0,   0,   False),
            (UNIT_ELEC_FC_G4,        "Forecast Tariefgroep +4u",   "Text",     0,   0,   False),
            (UNIT_ELEC_FC_G5,        "Forecast Tariefgroep +5u",   "Text",     0,   0,   False),
            (UNIT_ELEC_FC_G6,        "Forecast Tariefgroep +6u",   "Text",     0,   0,   False),
            (UNIT_ELEC_FC_G7,        "Forecast Tariefgroep +7u",   "Text",     0,   0,   False),
            (UNIT_ELEC_FC_G8,        "Forecast Tariefgroep +8u",   "Text",     0,   0,   False),
        ]

        for specs in [battery_specs, elec_specs]:
            for unit, name, typename, devtype, subtype, _enabled in specs:
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
            Domoticz.Log("Token geladen.")
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
        if time.time() < self._rate_limited_until:
            raise Exception("Rate limited — wacht even")
        url = BASE_URL + path
        h = dict(HEADERS)
        h["Authorization"] = f"Bearer {self._token['access_token']}"
        req = urllib.request.Request(url, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 429:
                retry_after = int(e.headers.get("Retry-After", 60))
                self._rate_limited_until = time.time() + retry_after
                Domoticz.Error(
                    f"Zonneplan API rate limit (429) — wacht {retry_after}s voor volgende poging."
                )
            raise

    def _post(self, path, data):
        url = BASE_URL + path
        body = json.dumps(data).encode("utf-8")
        req = urllib.request.Request(url, data=body, headers=HEADERS, method="POST")
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))

    # ------------------------------------------------------------------
    # Hoofd update loop
    # ------------------------------------------------------------------

    def _update_data(self):
        if not self._ensure_valid_token():
            return

        # Herdetecteer contracts als nog niet gevonden
        if not self._has_battery and not self._has_electricity:
            self._discover_contracts()

        if self._has_battery:
            self._update_battery()

        if self._has_electricity:
            self._update_electricity()

    # ==================================================================
    # BATTERIJ
    # ==================================================================

    def _update_battery(self):
        try:
            me = self._get("/user-accounts/me")
        except Exception as e:
            Domoticz.Error(f"Batterij API fout: {e}")
            return

        for conn in me.get("data", {}).get("connections", []):
            if conn.get("uuid") != self._battery_connection_uuid:
                continue
            for contract in conn.get("contracts", []):
                if contract.get("contract_type") == "home_battery_installation":
                    meta = contract.get("meta", {})
                    self._update_battery_sensors(meta)
                    self._update_battery_binary(meta)
                    self._update_battery_charts()
                    self._update_control_mode()
                    return

    def _update_battery_sensors(self, meta):
        if self._debug:
            Domoticz.Log(f"battery meta: {json.dumps(meta)}")

        def get(key, factor=1):
            v = meta.get(key)
            return round(float(v) * factor, 4) if v is not None else None

        soc    = get("state_of_charge", 0.1)
        power  = get("power_ac")
        prod   = get("production_day", 0.001)
        deliv  = get("delivery_day", 0.001)
        today  = get("total_day", 0.0000001)
        avg    = get("average_day", 0.0000001)
        total  = get("total_earned", 0.0000001)
        cycles = get("cycle_count")
        backup = get("backup_power_usable_capacity_wh")

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

        inverter = meta.get("inverter_state") or "Onbekend"
        Devices[UNIT_INVERTER].Update(nValue=0, sValue=inverter)

        model = meta.get("host_device_model_name")
        if model:
            Devices[UNIT_MODEL].Update(nValue=0, sValue=str(model))

        last = meta.get("last_measured_at")
        if last:
            Devices[UNIT_LAST_MEAS].Update(nValue=0, sValue=str(last))

        first = meta.get("first_measured_at")
        if first:
            Devices[UNIT_FIRST_MEAS].Update(nValue=0, sValue=str(first))

        Domoticz.Log(
            f"[Batterij] SoC: {soc}% | {power}W | "
            f"Opgeladen: {prod}kWh | Ontladen: {deliv}kWh | {state_nl}"
        )

    def _update_battery_binary(self, meta):
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
                Devices[unit].Update(nValue=1 if val else 0, sValue="On" if val else "Off")

    def _update_battery_charts(self):
        if not self._battery_contract_uuid:
            return
        try:
            data = self._get(
                f"/contracts/{self._battery_contract_uuid}/home_battery_installation/charts/year"
            )
            charts = data.get("data", {})

            def eur(section):
                v = charts.get(section, {}).get("total_result")
                return round(float(v) * 0.0000001, 2) if v is not None else None

            vals = {
                UNIT_THIS_MONTH_EUR: eur("this_month"),
                UNIT_LAST_MONTH_EUR: eur("last_month"),
                UNIT_THIS_YEAR_EUR:  eur("this_year"),
                UNIT_LAST_YEAR_EUR:  eur("last_year"),
            }
            for unit, val in vals.items():
                if val is not None:
                    Devices[unit].Update(nValue=0, sValue=str(val))
        except Exception as e:
            Domoticz.Error(f"Batterij charts fout: {e}")

    def _update_control_mode(self):
        if not self._battery_contract_uuid:
            return
        try:
            data = self._get(
                f"/api/contracts/{self._battery_contract_uuid}/home-battery/control-mode"
            )
            mode = data.get("data", {}).get("control_mode") or ""
            if mode:
                Devices[UNIT_CTRL_MODE].Update(nValue=0, sValue=str(mode))
        except Exception as e:
            Domoticz.Error(f"Control mode fout: {e}")

    # ==================================================================
    # ELEKTRICITEIT
    # ==================================================================

    def _update_electricity(self):
        try:
            data = self._get(f"/connections/{self._elec_connection_uuid}/summary")
        except Exception as e:
            Domoticz.Error(f"Elektriciteit API fout: {e}")
            return

        summary = data.get("data", {})
        if self._debug:
            Domoticz.Log(f"summary: {json.dumps(summary)}")

        now_utc = datetime.now(timezone.utc)
        current_hour = now_utc.hour

        # Gebruik (verandert vaker, altijd updaten)
        usage = summary.get("usage", {})
        if usage:
            self._update_elec_usage(usage)

        # Status (altijd updaten)
        self._update_elec_status(summary)

        # Tarieven alleen vernieuwen bij nieuw uur
        if current_hour != self._last_summary_hour:
            self._last_summary_hour = current_hour
            price_data = summary.get("price_per_date_and_hour", {})
            self._update_elec_tariffs(price_data, now_utc)

    def _update_elec_usage(self, usage):
        value = usage.get("value")
        if value is not None:
            Devices[UNIT_ELEC_USAGE].Update(nValue=0, sValue=f"{round(float(value))};0")

        measured_at = usage.get("measured_at") or usage.get("timestamp")
        if measured_at:
            Devices[UNIT_ELEC_USAGE_AT].Update(nValue=0, sValue=str(measured_at))

        score = usage.get("sustainability_score")
        if score is not None:
            Devices[UNIT_ELEC_SUSTAIN].Update(nValue=0, sValue=str(round(float(score) * 0.1, 1)))

    def _update_elec_status(self, summary):
        # Status bericht en tip — key kan variëren; probeer meerdere paden
        msg = (summary.get("status_message")
               or summary.get("status", {}).get("message")
               or summary.get("message"))
        if msg:
            Devices[UNIT_ELEC_STATUS_MSG].Update(nValue=0, sValue=str(msg))

        tip = (summary.get("status_tip")
               or summary.get("status", {}).get("tip")
               or summary.get("tip"))
        if tip:
            Devices[UNIT_ELEC_STATUS_TIP].Update(nValue=0, sValue=str(tip))

    def _update_elec_tariffs(self, price_data, now_utc):
        def hour_key(offset=0):
            from datetime import timedelta
            t = now_utc + timedelta(hours=offset)
            return t.strftime("%Y-%m-%d %-H")   # "2024-06-07 9" (geen voorloopnul, zoals de API)

        def get_price(offset=0):
            entry = price_data.get(hour_key(offset), {})
            raw = entry.get("electricity_price")
            return round(float(raw) * 0.0000001, 6) if raw is not None else None

        def get_group(offset=0):
            entry = price_data.get(hour_key(offset), {})
            grp = entry.get("tariff_group") or ""
            return TARIFF_GROUP_NL.get(grp, grp)

        # Huidig tarief en groep
        tariff = get_price(0)
        group  = get_group(0)

        if tariff is not None:
            Devices[UNIT_ELEC_TARIFF].Update(nValue=0, sValue=str(tariff))
        if group:
            Devices[UNIT_ELEC_TARIFF_GROUP].Update(nValue=0, sValue=group)

        # Forecast uur +1 t/m +8
        forecast_tariff_units = [
            UNIT_ELEC_FC_T1, UNIT_ELEC_FC_T2, UNIT_ELEC_FC_T3, UNIT_ELEC_FC_T4,
            UNIT_ELEC_FC_T5, UNIT_ELEC_FC_T6, UNIT_ELEC_FC_T7, UNIT_ELEC_FC_T8,
        ]
        forecast_group_units = [
            UNIT_ELEC_FC_G1, UNIT_ELEC_FC_G2, UNIT_ELEC_FC_G3, UNIT_ELEC_FC_G4,
            UNIT_ELEC_FC_G5, UNIT_ELEC_FC_G6, UNIT_ELEC_FC_G7, UNIT_ELEC_FC_G8,
        ]
        for i, (tu, gu) in enumerate(zip(forecast_tariff_units, forecast_group_units), start=1):
            fc_tariff = get_price(i)
            fc_group  = get_group(i)
            if fc_tariff is not None and tu in Devices:
                Devices[tu].Update(nValue=0, sValue=str(fc_tariff))
            if fc_group and gu in Devices:
                Devices[gu].Update(nValue=0, sValue=fc_group)

        Domoticz.Log(
            f"[Elektriciteit] Tarief: €{tariff}/kWh | Groep: {group} | "
            f"Forecast +1u: €{get_price(1)}/kWh"
        )


# Domoticz entry points
_plugin = BasePlugin()

def onStart():     _plugin.onStart()
def onStop():      _plugin.onStop()
def onHeartbeat(): _plugin.onHeartbeat()
