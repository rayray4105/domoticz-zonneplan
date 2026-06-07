#!/usr/bin/env python3
"""
Zonneplan Domoticz Plugin - Eenmalige authenticatie setup
Voer dit script uit op je Raspberry Pi VOORDAT je de plugin start.

Gebruik:
    python3 setup_auth.py

Het script slaat de tokens op in 'zonneplan_token.json' in dezelfde map.
Kopieer dat bestand naar de plugin-map als je klaar bent.

IMAP (optioneel):
    Als je IMAP instelt, klikt het script automatisch op de bevestigingslink
    in je e-mail. Zonder IMAP wordt de handmatige stap gebruikt.
"""

import urllib.request
import urllib.parse
import json
import os
import time
import imaplib
import email
import re
import getpass
from html.parser import HTMLParser

BASE_URL = "https://app-api.zonneplan.nl"
TOKEN_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "zonneplan_token.json")

HEADERS = {
    "Content-Type": "application/json;charset=utf-8",
    "x-app-version": "5.10.1",
    "x-app-environment": "production",
    "x-ha-integration": "domoticz-zonneplan/1.0.0",
    "User-Agent": "domoticz-zonneplan/1.0.0",
}


# ------------------------------------------------------------------
# HTTP helpers
# ------------------------------------------------------------------

def post(path, data):
    url = BASE_URL + path
    body = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=HEADERS, method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get(path):
    url = BASE_URL + path
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def http_get_url(url):
    """Bezoek een willekeurige URL (voor het klikken op de bevestigingslink)."""
    req = urllib.request.Request(url, headers={"User-Agent": "domoticz-zonneplan/1.0.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.status


# ------------------------------------------------------------------
# IMAP helpers
# ------------------------------------------------------------------

class _LinkFinder(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "a":
            for k, v in attrs:
                if k.lower() == "href" and v:
                    self.links.append(v)


def _find_zonneplan_link_in_mailbox(imap_server, email_addr, email_password, max_messages=30):
    """
    Verbindt via IMAP, scant de laatste e-mails en geeft de
    eerste link terug die 'mijn.zonneplan' bevat. Geeft None
    terug als er geen link gevonden wordt.
    """
    try:
        mail = imaplib.IMAP4_SSL(imap_server)
        mail.login(email_addr, email_password)
        mail.select("INBOX")

        status, data = mail.search(None, "ALL")
        if status != "OK" or not data[0]:
            mail.logout()
            return None

        mail_ids = data[0].split()
        to_check = sorted(mail_ids[-max_messages:], reverse=True)  # nieuwste eerst

        for mid in to_check:
            try:
                status, fetched = mail.fetch(mid, "(BODY.PEEK[])")
                if status != "OK" or not fetched or not fetched[0]:
                    continue

                msg = email.message_from_bytes(fetched[0][1])
                plain_parts, html_parts = [], []

                if msg.is_multipart():
                    for part in msg.walk():
                        payload = part.get_payload(decode=True)
                        if not payload:
                            continue
                        charset = part.get_content_charset() or "utf-8"
                        txt = payload.decode(charset, errors="replace")
                        if part.get_content_type() == "text/plain":
                            plain_parts.append(txt)
                        elif part.get_content_type() == "text/html":
                            html_parts.append(txt)
                else:
                    payload = msg.get_payload(decode=True)
                    if payload:
                        charset = msg.get_content_charset() or "utf-8"
                        plain_parts.append(payload.decode(charset, errors="replace"))

                full_plain = "\n".join(plain_parts)
                full_html  = "\n".join(html_parts)

                # Verzamel links uit HTML en plain text
                links = []
                if full_html:
                    parser = _LinkFinder()
                    parser.feed(full_html)
                    links.extend(parser.links)
                links.extend(re.findall(r"https?://[^\s\"'<>]+", full_plain))
                links.extend(re.findall(r"https?://[^\s\"'<>]+", full_html))

                for link in links:
                    if "mijn.zonneplan" in link.lower():
                        mail.logout()
                        return link
            except Exception:
                continue

        mail.logout()
        return None

    except Exception as e:
        print(f"  IMAP fout: {e}")
        return None


def wait_for_confirmation_link_imap(imap_server, email_addr, email_password,
                                     max_wait=180, poll_interval=5):
    """
    Polt de mailbox totdat een Zonneplan-bevestigingslink gevonden wordt,
    bezoekt de link automatisch en geeft True terug bij succes.
    """
    print(f"  Wachten op bevestigingsmail (max {max_wait}s)...")
    start = time.time()
    while time.time() - start < max_wait:
        link = _find_zonneplan_link_in_mailbox(imap_server, email_addr, email_password)
        if link:
            print(f"  Bevestigingslink gevonden, wordt automatisch geklikt...")
            try:
                status = http_get_url(link)
                print(f"  Link bezocht (HTTP {status}).")
                return True
            except Exception as e:
                print(f"  Kon link niet bezoeken: {e} — probeer handmatig.")
                return False
        time.sleep(poll_interval)

    print("  Geen bevestigingslink gevonden binnen de wachttijd.")
    return False


# ------------------------------------------------------------------
# IMAP configuratie ophalen
# ------------------------------------------------------------------

def ask_imap_config(email_addr):
    """
    Vraag de gebruiker of IMAP gebruikt moet worden.
    Geeft (imap_server, email_password) terug, of (None, None) als IMAP overgeslagen wordt.
    """
    print("\n--- IMAP (optioneel) ---")
    print("Met IMAP klikt het script automatisch op de bevestigingslink.")
    print("Zonder IMAP doe je dat handmatig.")
    keuze = input("IMAP gebruiken? [j/N]: ").strip().lower()
    if keuze not in ("j", "ja", "y", "yes"):
        return None, None

    # Raad IMAP-server op basis van domein
    domain = email_addr.split("@")[-1].lower()
    defaults = {
        "gmail.com":      "imap.gmail.com",
        "googlemail.com": "imap.gmail.com",
        "outlook.com":    "imap-mail.outlook.com",
        "hotmail.com":    "imap-mail.outlook.com",
        "live.com":       "imap-mail.outlook.com",
        "yahoo.com":      "imap.mail.yahoo.com",
        "icloud.com":     "imap.mail.me.com",
        "me.com":         "imap.mail.me.com",
    }
    default_server = defaults.get(domain, "")
    prompt = f"IMAP server [{default_server}]: " if default_server else "IMAP server: "
    imap_server = input(prompt).strip() or default_server

    if not imap_server:
        print("Geen IMAP server opgegeven, handmatige modus wordt gebruikt.")
        return None, None

    print(f"E-mailwachtwoord voor {email_addr}")
    if "gmail" in imap_server:
        print("  (Gmail: gebruik een App Password via myaccount.google.com/apppasswords)")
    email_password = getpass.getpass("Wachtwoord: ")

    # Test de verbinding
    print("  IMAP verbinding testen...")
    try:
        mail = imaplib.IMAP4_SSL(imap_server)
        mail.login(email_addr, email_password)
        mail.logout()
        print("  IMAP verbinding geslaagd.")
        return imap_server, email_password
    except Exception as e:
        print(f"  IMAP verbinding mislukt: {e}")
        print("  Handmatige modus wordt gebruikt.")
        return None, None


# ------------------------------------------------------------------
# Hoofd authenticatieflow
# ------------------------------------------------------------------

def main():
    print("=== Zonneplan Domoticz Plugin - Authenticatie Setup ===\n")
    email_addr = input("Voer je Zonneplan e-mailadres in: ").strip()

    # IMAP configuratie ophalen (optioneel)
    imap_server, email_password = ask_imap_config(email_addr)

    # Stap 1: bevestigingsmail versturen
    print(f"\nAanmeld-link wordt verstuurd naar {email_addr}...")
    resp = post("/auth/request", {"email": email_addr})
    uuid = resp.get("data", {}).get("uuid")
    if not uuid:
        print("Fout: kon geen UUID ophalen. Antwoord:", resp)
        return
    print(f"UUID ontvangen: {uuid}")

    # Stap 2: bevestigingslink klikken (automatisch of handmatig)
    if imap_server:
        clicked = wait_for_confirmation_link_imap(imap_server, email_addr, email_password)
        if not clicked:
            print("Handmatige stap: klik zelf op de link in je e-mail.")
            input("Druk op ENTER nadat je op de link hebt geklikt...\n")
    else:
        print("\nControleer je e-mail en klik op de aanmeldlink.")
        input("Druk op ENTER nadat je op de link hebt geklikt...\n")

    # Stap 3: wacht tot de backend het wachtwoord beschikbaar heeft
    print("Eenmalig wachtwoord ophalen...")
    otp = None
    for attempt in range(20):
        try:
            resp = get(f"/auth/request/{uuid}")
            auth_data = resp.get("data", {})
            if auth_data.get("is_activated") and auth_data.get("password"):
                otp = auth_data["password"]
                print("Eenmalig wachtwoord verkregen.")
                break
            # Fallback voor oudere API-versies
            if auth_data.get("one_time_password"):
                otp = auth_data["one_time_password"]
                print("Eenmalig wachtwoord verkregen (legacy veld).")
                break
        except Exception:
            pass
        print(f"  Nog niet actief, nog eens proberen ({attempt + 1}/20)...")
        time.sleep(5)
    else:
        print("Fout: kon geen eenmalig wachtwoord ophalen. Probeer opnieuw.")
        return

    # Stap 4: wissel wachtwoord in voor access token
    print("Toegangstoken aanvragen...")
    resp = post("/oauth/token", {
        "grant_type": "one_time_password",
        "email": email_addr,
        "password": otp,
    })

    token_data = resp.get("data", resp)
    if "access_token" not in token_data:
        print("Fout: geen access_token ontvangen. Antwoord:", resp)
        return

    token_data["email"] = email_addr
    token_data["obtained_at"] = time.time()

    with open(TOKEN_FILE, "w") as f:
        json.dump(token_data, f, indent=2)

    print(f"\nTokens opgeslagen in: {TOKEN_FILE}")

    # Verificatie
    print("\nVerificatie: gebruikersaccount ophalen...")
    try:
        req = urllib.request.Request(
            BASE_URL + "/user-accounts/me",
            headers={**HEADERS, "Authorization": f"Bearer {token_data['access_token']}"}
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            me = json.loads(r.read().decode())
        connections = me.get("data", {}).get("connections", [])
        print(f"Succesvol ingelogd! {len(connections)} verbinding(en) gevonden.")
        for conn in connections:
            for c in conn.get("contracts", []):
                ctype = c.get("contract_type", "onbekend")
                cuuid = c.get("uuid", "")
                print(f"  - {ctype} ({cuuid[:16]}...)")
    except Exception as e:
        print(f"Waarschuwing: verificatie mislukt: {e}")

    print(f"\nKopieer '{TOKEN_FILE}' naar je Domoticz plugin-map:")
    print(f"  /home/pi/domoticz/plugins/Zonneplan/zonneplan_token.json")
    print("\nSetup voltooid!")


if __name__ == "__main__":
    main()
