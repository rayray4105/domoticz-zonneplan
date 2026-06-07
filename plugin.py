"""
<plugin key="ZonneplanBattery" name="Zonneplan Thuisbatterij" author="rdejager"
        version="1.0.0" externallink="https://github.com/rdejager/domoticz-zonneplan">
    <description>
        <h2>Zonneplan Thuisbatterij</h2><br/>
        Toont je Zonneplan thuisbatterij in Domoticz, inclusief het Energy Dashboard.<br/><br/>
        <b>Eerste gebruik:</b><br/>
        Voer <i>setup_auth.py</i> uit om eenmalig in te loggen en kopieer
        <i>zonneplan_token.json</i> naar de plugin-map.<br/><br/>
        <b>Aangemaakt devices:</b>
        <ul style="list-style-type:square">
            <li>Batterij Laadniveau (SoC %)</li>
            <li>Batterij Vermogen (W)</li>
            <li>Zonneplan Opgeladen (kWh — Energy Dashboard)</li>
            <li>Zonneplan Ontladen (kWh — Energy Dashboard)</li>
            <li>Batterij Status (tekst)</li>
        </ul>
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
    "x-ha-integration": "domoticz-zonneplan/1.0.0",
    "User-Agent": "domoticz-zonneplan/1.0.0",
}

# Domoticz device units
UNIT_SOC = 1          # State of Charge (%)
UNIT_POWER = 2        # Huidig vermogen (W)
UNIT_CHARGED = 3      # Vandaag opgeladen (kWh)
UNIT_DISCHARGED = 4   # Vandaag ontladen (kWh)
UNIT_STATE = 5        # Batterijstatus (tekst)

BATTERY_STATE_NL = {
    "charging": "Opladen",
    "discharging": "Ontladen",
    "idle": "Inactief",
    "standby": "Stand-by",
    "full": "Vol",
    "empty": "Leeg",
}


class BasePlugin:
    def __init__(self):
        self._token = None
        self._heartbeat_count = 0
        self._poll_ticks = 2   # aantal heartbeats (à 30s) tussen polls
        self._debug = False

    # ------------------------------------------------------------------
    # Domoticz lifecycle
    # ------------------------------------------------------------------

    def onStart(self):
        self._debug = Parameters["Mode6"] == "1"
        if self._debug:
            Domoticz.Debugging(1)

        try:
            interval = int(Parameters["Mode1"])
            self._poll_ticks = max(1, interval // 30)
        except (ValueError, KeyError):
            self._poll_ticks = 2

        Domoticz.Heartbeat(30)
        Domoticz.Log(f"Zonneplan plugin gestart (poll elke {self._poll_ticks * 30}s)")

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
        if UNIT_SOC not in Devices:
            Domoticz.Device(
                Name="Batterij Laadniveau",
                Unit=UNIT_SOC,
                TypeName="Percentage",
            ).Create()

        if UNIT_POWER not in Devices:
            # Type 248 = Electric, Subtype 1 = Instant+Counter
            Domoticz.Device(
                Name="Batterij Vermogen",
                Unit=UNIT_POWER,
                Type=248,
                Subtype=1,
            ).Create()

        if UNIT_CHARGED not in Devices:
            # Type 243, Subtype 29 = General / kWh — bruikbaar in Energy Dashboard
            Domoticz.Device(
                Name="Zonneplan Opgeladen",
                Unit=UNIT_CHARGED,
                Type=243,
                Subtype=29,
            ).Create()

        if UNIT_DISCHARGED not in Devices:
            Domoticz.Device(
                Name="Zonneplan Ontladen",
                Unit=UNIT_DISCHARGED,
                Type=243,
                Subtype=29,
            ).Create()

        if UNIT_STATE not in Devices:
            Domoticz.Device(
                Name="Batterij Status",
                Unit=UNIT_STATE,
                TypeName="Text",
            ).Create()

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

        # Vernieuwen als token over minder dan 5 minuten verloopt
        if (time.time() - obtained_at) < (expires_in - 300):
            return True

        Domoticz.Log("Zonneplan token verlopen, vernieuwen...")
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
    # Data ophalen en verwerken
    # ------------------------------------------------------------------

    def _update_data(self):
        if not self._ensure_valid_token():
            return

        try:
            me = self._get("/user-accounts/me")
        except urllib.error.HTTPError as e:
            Domoticz.Error(f"Zonneplan API fout {e.code}: {e.reason}")
            return
        except Exception as e:
            Domoticz.Error(f"Zonneplan verbindingsfout: {e}")
            return

        battery = self._find_battery_contract(me)
        if not battery:
            Domoticz.Error(
                "Geen home_battery_installation gevonden in Zonneplan account."
            )
            return

        self._update_devices(battery.get("meta", {}))

    def _find_battery_contract(self, me_data):
        connections = me_data.get("data", {}).get("connections", [])
        for conn in connections:
            for contract in conn.get("contracts", []):
                if contract.get("contract_type") == "home_battery_installation":
                    return contract
        return None

    def _update_devices(self, meta):
        if self._debug:
            Domoticz.Log(f"Zonneplan meta: {json.dumps(meta)}")

        # State of Charge (%) — raw waarde is tienden van procenten (factor 0.1)
        soc_raw = meta.get("state_of_charge")
        if soc_raw is not None:
            soc = round(float(soc_raw) * 0.1, 1)
            Devices[UNIT_SOC].Update(nValue=0, sValue=str(soc))
        else:
            soc = None

        # Huidig vermogen in Watt — geen conversiefactor
        # power_ac: positief = laden, negatief = ontladen
        power_ac = meta.get("power_ac")
        if power_ac is not None:
            Devices[UNIT_POWER].Update(nValue=0, sValue=f"{round(float(power_ac))};0")

        # Vandaag opgeladen kWh — raw waarde is in Wh (factor 0.001)
        production_raw = meta.get("production_day")
        if production_raw is not None:
            production = round(float(production_raw) * 0.001, 3)
            Devices[UNIT_CHARGED].Update(nValue=0, sValue=f"0;{production}")
        else:
            production = None

        # Vandaag ontladen kWh — raw waarde is in Wh (factor 0.001)
        delivery_raw = meta.get("delivery_day")
        if delivery_raw is not None:
            delivery = round(float(delivery_raw) * 0.001, 3)
            Devices[UNIT_DISCHARGED].Update(nValue=0, sValue=f"0;{delivery}")
        else:
            delivery = None

        # Status tekst
        battery_state = meta.get("battery_state", "")
        state_nl = BATTERY_STATE_NL.get(battery_state, battery_state or "Onbekend")
        inverter = meta.get("inverter_state", "")
        if inverter and inverter != battery_state:
            state_nl += f" ({inverter})"
        Devices[UNIT_STATE].Update(nValue=0, sValue=state_nl)

        Domoticz.Log(
            f"SoC: {soc}% | Vermogen: {power_ac}W | "
            f"Opgeladen: {production}kWh | Ontladen: {delivery}kWh | {state_nl}"
        )


_plugin = BasePlugin()


def onStart():
    _plugin.onStart()


def onStop():
    _plugin.onStop()


def onHeartbeat():
    _plugin.onHeartbeat()
