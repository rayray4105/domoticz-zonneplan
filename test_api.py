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
    "x-ha-integration": "domoticz-zonneplan/1.0.0",
    "User-Agent": "domoticz-zonneplan/1.0.0",
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
    print("Token vernieuwd en opgeslagen.\n")
    return token


def get(path, token):
    url = BASE_URL + path
    h = dict(HEADERS)
    h["Authorization"] = f"Bearer {token['access_token']}"
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print('='*60)


def main():
    token = load_token()

    expires_in = token.get("expires_in", 3600)
    obtained_at = token.get("obtained_at", 0)
    if (time.time() - obtained_at) >= (expires_in - 300):
        token = refresh_token(token)

    section("GET /user-accounts/me")
    try:
        me = get("/user-accounts/me", token)
    except urllib.error.HTTPError as e:
        print(f"FOUT {e.code}: {e.reason}")
        sys.exit(1)

    connections = me.get("data", {}).get("connections", [])
    print(f"Aantal verbindingen: {len(connections)}\n")

    battery_found = False
    for i, conn in enumerate(connections):
        print(f"Verbinding {i+1}: uuid={conn.get('uuid', '?')[:16]}...")
        contracts = conn.get("contracts", [])
        for j, contract in enumerate(contracts):
            ctype = contract.get("contract_type", "onbekend")
            cuuid = contract.get("uuid", "")
            print(f"  Contract {j+1}: {ctype} (uuid={cuuid[:16]}...)")

            if ctype == "home_battery_installation":
                battery_found = True
                section(f"Batterij contract gevonden — meta velden")
                meta = contract.get("meta", {})
                if not meta:
                    print("  (geen meta data)")
                else:
                    for key, value in sorted(meta.items()):
                        print(f"  {key:<40} = {value}")

                section("Relevante waarden voor Domoticz (na conversie)")
                # (key, label, factor)
                fields = [
                    ("state_of_charge",              "Laadniveau (%)",          0.1),
                    ("power_ac",                     "Vermogen (W)",            1),
                    ("battery_state",                "Status",                  None),
                    ("inverter_state",               "Inverter status",         None),
                    ("production_day",               "Opgeladen vandaag (kWh)", 0.001),
                    ("delivery_day",                 "Ontladen vandaag (kWh)",  0.001),
                    ("total_earned",                 "Totaal verdiend (€)",     0.0000001),
                    ("total_day",                    "Verdiend vandaag (€)",    0.0000001),
                    ("average_day",                  "Gemiddeld per dag (€)",   0.0000001),
                    ("cycle_count",                  "Cycli",                   1),
                    ("backup_power_usable_capacity_wh", "Backup capaciteit (Wh)", 1),
                    ("last_measured_at",             "Laatste meting",          None),
                ]
                for key, label, factor in fields:
                    raw = meta.get(key)
                    if raw is None:
                        val = "⚠ niet aanwezig in API"
                    elif factor is None:
                        val = raw
                    else:
                        val = f"{round(float(raw) * factor, 4)}  (raw: {raw})"
                    print(f"  {label:<35} {val}")

    if not battery_found:
        print("\n⚠ Geen home_battery_installation gevonden in dit account.")
        print("Volledige ruwe data:")
        print(json.dumps(me, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
