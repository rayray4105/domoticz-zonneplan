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
from datetime import datetime, timezone, timedelta

BASE_URL = "https://app-api.zonneplan.nl"
TOKEN_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "zonneplan_token.json")

HEADERS = {
    "Content-Type": "application/json;charset=utf-8",
    "x-app-version": "5.10.1",
    "x-app-environment": "production",
    "x-ha-integration": "domoticz-zonneplan/3.0.0",
    "User-Agent": "domoticz-zonneplan/3.0.0",
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
    return f"{round(float(raw) * factor, 6)}  (raw: {raw})"


def main():
    token = load_token()
    expires_in = token.get("expires_in", 3600)
    obtained_at = token.get("obtained_at", 0)
    if (time.time() - obtained_at) >= (expires_in - 300):
        token = refresh_token(token)

    # ----------------------------------------------------------------
    section("GET /user-accounts/me — contracten detecteren")
    me = api_get("/user-accounts/me", token)
    if not me:
        sys.exit(1)

    connections = me.get("data", {}).get("connections", [])
    print(f"Verbindingen: {len(connections)}\n")

    battery_contract_uuid = None
    battery_connection_uuid = None
    elec_connection_uuid = None

    for i, conn in enumerate(connections):
        conn_uuid = conn.get("uuid", "")
        print(f"Verbinding {i+1}: {conn_uuid[:20]}...")
        for j, c in enumerate(conn.get("contracts", [])):
            ctype = c.get("contract_type", "onbekend")
            cuuid = c.get("uuid", "")
            print(f"  Contract {j+1}: {ctype} ({cuuid[:16]}...)")

            if ctype == "home_battery_installation":
                battery_contract_uuid = cuuid
                battery_connection_uuid = conn_uuid

            if ctype in ("electricity", "electricity_without_feed_in"):
                elec_connection_uuid = conn_uuid

    # ================================================================
    # BATTERIJ
    # ================================================================
    if battery_contract_uuid:
        section(f"BATTERIJ — meta velden (raw)")
        battery_meta = {}
        for conn in connections:
            for c in conn.get("contracts", []):
                if c.get("uuid") == battery_contract_uuid:
                    battery_meta = c.get("meta", {})

        for key, val in sorted(battery_meta.items()):
            print(f"  {key:<50} {val}")

        section("BATTERIJ — sensoren na conversie")
        sensors = [
            ("state_of_charge",                 "Laadniveau (%)",                0.1),
            ("power_ac",                        "Vermogen (W)",                  1),
            ("battery_state",                   "Status",                        None),
            ("inverter_state",                  "Inverter status",               None),
            ("host_device_model_name",          "Model",                         None),
            ("production_day",                  "Opgeladen vandaag (kWh)",       0.001),
            ("delivery_day",                    "Ontladen vandaag (kWh)",        0.001),
            ("total_day",                       "Verdiend vandaag (€)",          0.0000001),
            ("average_day",                     "Gemiddeld per dag (€)",         0.0000001),
            ("total_earned",                    "Totaal verdiend (€)",           0.0000001),
            ("cycle_count",                     "Cycli",                         1),
            ("backup_power_usable_capacity_wh", "Backup capaciteit (Wh)",        1),
            ("last_measured_at",                "Laatste meting",                None),
            ("first_measured_at",               "Eerste meting",                 None),
        ]
        for key, label, factor in sensors:
            print(f"  {label:<35} {fmt(battery_meta.get(key), factor)}")

        section("BATTERIJ — binary sensoren")
        binaries = [
            ("dynamic_charging_enabled",        "Dynamic charging"),
            ("load_balancing_overload_active",  "Load balancing overload"),
            ("load_balancing_enabled",          "Load balancing"),
            ("manual_control_enabled",          "Handmatige bediening"),
            ("grid_congestion_active",          "Netcongestie"),
            ("home_optimization_active",        "Home optimalisatie actief"),
            ("home_optimization_enabled",       "Home optimalisatie"),
            ("self_consumption_enabled",        "Zelfconsumptie"),
            ("backup_power_active",             "Backup stroom"),
        ]
        for key, label in binaries:
            val = battery_meta.get(key)
            status = "⚠ niet aanwezig" if val is None else ("Aan" if val else "Uit")
            print(f"  {label:<35} {status}")

        section(f"BATTERIJ — charts")
        charts_data = api_get(
            f"/contracts/{battery_contract_uuid}/home_battery_installation/charts/year", token
        )
        if charts_data:
            charts = charts_data.get("data", {})
            for period in ["this_month", "last_month", "this_year", "last_year"]:
                raw = charts.get(period, {}).get("total_result")
                print(f"  {period:<20} {fmt(raw, 0.0000001)}")
        else:
            print("  Niet beschikbaar")

        section(f"BATTERIJ — control mode")
        ctrl_data = api_get(
            f"/api/contracts/{battery_contract_uuid}/home-battery/control-mode", token
        )
        if ctrl_data:
            print(json.dumps(ctrl_data.get("data", {}), indent=4, ensure_ascii=False))
        else:
            print("  Niet beschikbaar")

        section(f"BATTERIJ — home optimization")
        opt_data = api_get(
            f"/api/contracts/{battery_contract_uuid}/home-battery/control-mode/home_optimization",
            token
        )
        if opt_data:
            print(json.dumps(opt_data.get("data", {}), indent=4, ensure_ascii=False))
        else:
            print("  Niet beschikbaar")

    else:
        print("\n⚠ Geen batterijcontract gevonden.")

    # ================================================================
    # ELEKTRICITEIT
    # ================================================================
    if elec_connection_uuid:
        section(f"ELEKTRICITEIT — GET /connections/{elec_connection_uuid[:16]}…/summary")
        summary_data = api_get(f"/connections/{elec_connection_uuid}/summary", token)

        if summary_data:
            summary = summary_data.get("data", {})

            section("ELEKTRICITEIT — alle top-level keys in summary")
            for key, val in summary.items():
                if key == "price_per_date_and_hour":
                    print(f"  {key:<40} (dict met {len(val)} uren)")
                elif isinstance(val, dict):
                    print(f"  {key:<40} (dict: {list(val.keys())[:5]}...)")
                elif isinstance(val, list):
                    print(f"  {key:<40} (lijst met {len(val)} items)")
                else:
                    print(f"  {key:<40} {val}")

            section("ELEKTRICITEIT — usage")
            usage = summary.get("usage", {})
            if usage:
                for k, v in usage.items():
                    print(f"  {k:<40} {v}")
            else:
                print("  (leeg of niet aanwezig)")

            section("ELEKTRICITEIT — tarieven huidig uur + forecast +1 t/m +8")
            now_utc = datetime.now(timezone.utc)
            price_data = summary.get("price_per_date_and_hour", {})

            print(f"  {'Uur':<25} {'Tarief (€/kWh)':<20} {'Tariefgroep'}")
            print(f"  {'-'*60}")
            for offset in range(9):
                t = now_utc + timedelta(hours=offset)
                # probeer zowel met als zonder voorloopnul
                key1 = t.strftime("%Y-%m-%d %-H")   # "2024-06-07 9"
                key2 = t.strftime("%Y-%m-%d %H")    # "2024-06-07 09"
                entry = price_data.get(key1) or price_data.get(key2) or {}
                raw_price = entry.get("electricity_price")
                group = entry.get("tariff_group", "?")
                label = "Nu" if offset == 0 else f"+{offset}u"
                if raw_price is not None:
                    price_eur = round(float(raw_price) * 0.0000001, 6)
                    print(f"  {label:<6} {t.strftime('%H:%M')} UTC  {price_eur:<20} {group}")
                else:
                    print(f"  {label:<6} {t.strftime('%H:%M')} UTC  ⚠ geen data  (geprobeerd: '{key1}' en '{key2}')")

            section("ELEKTRICITEIT — status velden (zoeken)")
            for key in ["status_message", "status_tip", "status", "message", "tip",
                        "sustainability_score", "tariff_group", "current_tariff_group"]:
                val = summary.get(key)
                if val is not None:
                    print(f"  {key:<40} {val}")
                else:
                    print(f"  {key:<40} ⚠ niet aanwezig")

            section("ELEKTRICITEIT — eerste 2 price_per_date_and_hour entries (raw)")
            for i, (k, v) in enumerate(price_data.items()):
                print(f"  '{k}': {v}")
                if i >= 1:
                    break

        else:
            print("  Niet beschikbaar")
    else:
        print("\n⚠ Geen elektriciteitscontract gevonden.")


if __name__ == "__main__":
    main()
