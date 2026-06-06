#!/usr/bin/env python3
"""
Zonneplan Domoticz Plugin - Eenmalige authenticatie setup
Voer dit script uit op je Raspberry Pi VOORDAT je de plugin start.

Gebruik:
    python3 setup_auth.py

Het script slaat de tokens op in 'zonneplan_token.json' in dezelfde map.
Kopieer dat bestand naar de plugin-map als je klaar bent.
"""

import urllib.request
import urllib.parse
import json
import os
import time

BASE_URL = "https://app-api.zonneplan.nl"
TOKEN_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "zonneplan_token.json")

HEADERS = {
    "Content-Type": "application/json;charset=utf-8",
    "x-app-version": "5.10.1",
    "x-app-environment": "production",
    "x-ha-integration": "domoticz-zonneplan/1.0.0",
    "User-Agent": "domoticz-zonneplan/1.0.0",
}


def post(path, data):
    url = BASE_URL + path
    body = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=HEADERS, method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get(path, token=None):
    url = BASE_URL + path
    h = dict(HEADERS)
    if token:
        h["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main():
    print("=== Zonneplan Domoticz Plugin - Authenticatie Setup ===\n")
    email = input("Voer je Zonneplan e-mailadres in: ").strip()

    print(f"\nAanmeld-link wordt verstuurd naar {email}...")
    resp = post("/auth/request", {"email": email})
    uuid = resp.get("data", {}).get("uuid")
    if not uuid:
        print("Fout: kon geen UUID ophalen. Antwoord:", resp)
        return

    print(f"UUID ontvangen: {uuid}")
    print("\nControleer je e-mail en klik op de aanmeldlink.")
    input("Druk op ENTER nadat je op de link hebt geklikt...\n")

    print("Eenmalig wachtwoord ophalen...")
    for attempt in range(10):
        try:
            resp = get(f"/auth/request/{uuid}")
            otp = resp.get("data", {}).get("one_time_password")
            if otp:
                print(f"Eenmalig wachtwoord verkregen.")
                break
        except Exception as e:
            pass
        print(f"  Nog niet actief, nog eens proberen ({attempt + 1}/10)...")
        time.sleep(3)
    else:
        print("Fout: kon geen eenmalig wachtwoord ophalen. Probeer opnieuw.")
        return

    print("Toegangstoken aanvragen...")
    resp = post("/oauth/token", {
        "grant_type": "one_time_password",
        "one_time_password": otp,
    })

    token_data = resp.get("data", resp)
    if "access_token" not in token_data:
        print("Fout: geen access_token ontvangen. Antwoord:", resp)
        return

    token_data["email"] = email
    token_data["obtained_at"] = time.time()

    with open(TOKEN_FILE, "w") as f:
        json.dump(token_data, f, indent=2)

    print(f"\nTokens opgeslagen in: {TOKEN_FILE}")
    print("\nVerificatie: gebruikersaccount ophalen...")
    try:
        me = get("/user-accounts/me", token_data["access_token"])
        connections = me.get("data", {}).get("connections", [])
        print(f"Succesvol ingelogd! {len(connections)} verbinding(en) gevonden.")
        for conn in connections:
            contracts = conn.get("contracts", [])
            for c in contracts:
                ctype = c.get("contract_type", "onbekend")
                uuid_c = c.get("uuid", "")
                print(f"  - Contract: {ctype} ({uuid_c[:8]}...)")
    except Exception as e:
        print(f"Waarschuwing: verificatie mislukt: {e}")

    print(f"\nKopieer '{TOKEN_FILE}' naar je Domoticz plugin-map:")
    print(f"  /home/pi/domoticz/plugins/Zonneplan/zonneplan_token.json")
    print("\nSetup voltooid!")


if __name__ == "__main__":
    main()
