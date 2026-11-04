#!/usr/bin/env python3
"""Converteix la clau curta de Facebook en una clau de pàgina que no caduca.

Ús:  python3 scripts/clau-facebook.py

Et demana:
  1. L'identificador de l'aplicació (App ID) i la clau secreta (App Secret):
     tauler de Meta → la teua aplicació → App settings → Basic.
  2. Una clau d'usuari curta amb els permisos pages_show_list, pages_read_engagement
     i pages_manage_posts (Graph API Explorer → Generate Access Token).

Després escriu les dues línies que cal posar en el fitxer .env.
No envies mai estes claus a ningú.
"""
from __future__ import annotations

from getpass import getpass
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

GRAPH = "https://graph.facebook.com/v23.0"


def get(path: str, **params: str) -> dict:
    url = f"{GRAPH}/{path}?{urllib.parse.urlencode(params)}"
    try:
        with urllib.request.urlopen(url, timeout=60) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        detail = json.loads(exc.read().decode() or "{}").get("error", {}).get("message", exc.reason)
        sys.exit(f"Facebook ha contestat amb un error: {detail}")


def main() -> None:
    app_id = input("App ID: ").strip()
    secret = getpass("App Secret (no es veurà mentre l'escrius): ").strip()
    short = getpass("Clau d'usuari curta (no es veurà): ").strip()
    long_lived = get("oauth/access_token", grant_type="fb_exchange_token", client_id=app_id, client_secret=secret, fb_exchange_token=short)["access_token"]
    pages = get("me/accounts", access_token=long_lived, fields="id,name,access_token").get("data", [])
    if not pages:
        sys.exit("No s'ha trobat cap pàgina. Comprova que la clau té el permís pages_show_list i que has triat la pàgina en generar-la.")
    for number, page in enumerate(pages, 1):
        print(f"{number}. {page['name']}")
    choice = pages[0] if len(pages) == 1 else pages[int(input("Quina pàgina? (número): ")) - 1]
    print("\nAfig estes dues línies al fitxer .env de pomodoro-studio:\n")
    print(f"FACEBOOK_PAGE_ID={choice['id']}")
    print(f"FACEBOOK_PAGE_TOKEN={choice['access_token']}")
    print("\nDesprés torna a obrir Pomodoro.")


if __name__ == "__main__":
    main()
