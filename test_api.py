#!/usr/bin/env python3
"""
Zonneplan API test — voer uit om de ruwe API-data te bekijken.
Vereist: zonneplan_token.json in dezelfde map (aangemaakt door setup_auth.py).

Gebruik:
    python3 test_api.py
"""

import json
import os
import sys
import time
import urllib.request
import urllib.error

BASE_URL = "https://app-api.zonneplan.nl"
TOKEN_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "zonneplan_token.json")

HEADERS = {
    "Content-Type": "application/json;charset=utf-8",
    "x-app-version": "5.10.1",
    "x-app-environment": "production",
    "x-ha-integration": "domoticz-zonneplan/2.0.0",
    "User-Agent": "domoticz-zonneplan/2.0.0",
}


def load_token():
    if not os.path.exists(TOKEN_FILE):
        print(f"FOUT: {TOKEN_FILE} niet gevonden. Voer eerst setup_auth.py uit.")
        sys.exit(1)
    with open(TOKEN_FILE) as f:
        return json.load(f)


def refresh_token(token):
    print("Token vernieuwen...")
    url = BASE_URL + "/oauth/token"
    body = json.dumps({
        "grant_type": "refresh_token",
        "refresh_token": token["refresh_token"],
    }).encode()
    req = urllib.request.Request(url, data=body, headers=HEADERS, method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode())
    token.update(data.get("data", data))
    token["obtained_at"] = time.time()
    with open(TOKEN_FILE, "w") as f:
        json.dump(token, f, indent=2)
    print("Token vernieuwd.\n")
    return token


def api_get(path, token):
    url = BASE_URL + path
    h = dict(HEADERS)
    h["Authorization"] = f"Bearer {token['access_token']}"
    req = urllib.request.Request(url, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"  HTTP {e.code}: {e.reason}")
        return None


def section(title):
    print(f"\n{'='*60}\n  {title}\n{'='*60}")


def fmt(raw, factor):
    if raw is None:
        return "⚠ niet aanwezig in API"
    if factor is None:
        return str(raw)
    converted = round(float(raw) * factor, 4)
    return f"{converted}  (raw: {raw})"


def main():
    token = load_token()
    expires_in = token.get("expires_in", 3600)
    obtained_at = token.get("obtained_at", 0)
    if (time.time() - obtained_at) >= (expires_in - 300):
        token = refresh_token(token)

    # ----------------------------------------------------------------
    section("GET /user-accounts/me")
    me = api_get("/user-accounts/me", token)
    if not me:
        sys.exit(1)

    connections = me.get("data", {}).get("connections", [])
    print(f"Verbindingen: {len(connections)}")

    contract_uuid = None
    connection_uuid = None

    for i, conn in enumerate(connections):
        print(f"\nVerbinding {i+1}: {conn.get('uuid', '?')[:16]}...")
        for j, c in enumerate(conn.get("contracts", [])):
            ctype = c.get("contract_type", "onbekend")
            cuuid = c.get("uuid", "")
            print(f"  Contract {j+1}: {ctype} ({cuuid[:16]}...)")

            if ctype == "home_battery_installation":
                contract_uuid = cuuid
                connection_uuid = conn.get("uuid")
                meta = c.get("meta", {})

                section("Alle meta velden (raw)")
                for key, val in sorted(meta.items()):
                    print(f"  {key:<50} {val}")

                section("Sensoren na conversie")
                sensors = [
                    ("state_of_charge",                  "Laadniveau (%)",                   0.1),
                    ("power_ac",                         "Vermogen (W)",                     1),
                    ("battery_state",                    "Batterijstatus",                   None),
                    ("inverter_state",                   "Inverter status",                  None),
                    ("host_device_model_name",           "Model",                            None),
                    ("production_day",                   "Opgeladen vandaag (kWh)",          0.001),
                    ("delivery_day",                     "Ontladen vandaag (kWh)",           0.001),
                    ("total_day",                        "Verdiend vandaag (€)",             0.0000001),
                    ("average_day",                      "Gemiddeld per dag (€)",            0.0000001),
                    ("total_earned",                     "Totaal verdiend (€)",              0.0000001),
                    ("cycle_count",                      "Cycli",                            1),
                    ("backup_power_usable_capacity_wh",  "Backup capaciteit (Wh)",           1),
                    ("last_measured_at",                 "Laatste meting",                   None),
                    ("first_measured_at",                "Eerste meting",                    None),
                ]
                for key, label, factor in sensors:
                    print(f"  {label:<35} {fmt(meta.get(key), factor)}")

                section("Binary sensoren")
                binaries = [
                    ("dynamic_charging_enabled",         "Dynamic charging"),
                    ("load_balancing_overload_active",   "Load balancing overload"),
                    ("load_balancing_enabled",           "Load balancing"),
                    ("manual_control_enabled",           "Handmatige bediening"),
                    ("grid_congestion_active",           "Netcongestie"),
                    ("home_optimization_active",         "Home optimalisatie actief"),
                    ("home_optimization_enabled",        "Home optimalisatie"),
                    ("self_consumption_enabled",         "Zelfconsumptie"),
                    ("backup_power_active",              "Backup stroom"),
                ]
                for key, label in binaries:
                    val = meta.get(key)
                    status = "⚠ niet aanwezig" if val is None else ("Aan" if val else "Uit")
                    print(f"  {label:<35} {status}")

    if not contract_uuid:
        print("\n⚠ Geen home_battery_installation gevonden.")
        return

    # ----------------------------------------------------------------
    section(f"GET charts (contract {contract_uuid[:16]}...)")
    charts_data = api_get(
        f"/contracts/{contract_uuid}/home_battery_installation/charts/year", token
    )
    if charts_data:
        charts = charts_data.get("data", {})
        for period in ["this_month", "last_month", "this_year", "last_year"]:
            raw = charts.get(period, {}).get("total_result")
            print(f"  {period:<20} {fmt(raw, 0.0000001)}")
    else:
        print("  Niet beschikbaar")

    # ----------------------------------------------------------------
    section(f"GET control-mode (contract {contract_uuid[:16]}...)")
    ctrl_data = api_get(
        f"/api/contracts/{contract_uuid}/home-battery/control-mode", token
    )
    if ctrl_data:
        mode = ctrl_data.get("data", {}).get("control_mode", "?")
        print(f"  control_mode: {mode}")
        print(f"\n  Volledige response:")
        print(json.dumps(ctrl_data.get("data", {}), indent=4, ensure_ascii=False))
    else:
        print("  Niet beschikbaar")

    # ----------------------------------------------------------------
    section(f"GET home optimization (contract {contract_uuid[:16]}...)")
    opt_data = api_get(
        f"/api/contracts/{contract_uuid}/home-battery/control-mode/home_optimization", token
    )
    if opt_data:
        print(json.dumps(opt_data.get("data", {}), indent=4, ensure_ascii=False))
    else:
        print("  Niet beschikbaar")


if __name__ == "__main__":
    main()
