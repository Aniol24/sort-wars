"""
TikTok OAuth — one-time token acquisition.

Run this on a machine with a browser (Windows/Mac).
It will open TikTok's authorization page, you log in, and the
access + refresh tokens are saved to data/tiktok_token.json.

Usage:
    python tiktok_auth.py
"""

import base64
import hashlib
import json
import os
import secrets
import webbrowser
from pathlib import Path
from urllib.parse import urlencode, urlparse, parse_qs

import requests
from dotenv import load_dotenv

load_dotenv()

CLIENT_KEY    = os.environ["TIKTOK_CLIENT_KEY"]
CLIENT_SECRET = os.environ["TIKTOK_CLIENT_SECRET"]
REDIRECT_URI  = "https://localhost:8080/callback"
SCOPES        = "user.info.basic,video.upload"
TOKEN_PATH    = Path("data/tiktok_token.json")

AUTH_URL   = "https://www.tiktok.com/v2/auth/authorize/"
TOKEN_URL  = "https://open.tiktokapis.com/v2/oauth/token/"


def _pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).rstrip(b"=").decode()
    return verifier, challenge


def build_auth_url(state: str, code_challenge: str) -> str:
    params = {
        "client_key":            CLIENT_KEY,
        "scope":                 SCOPES,
        "response_type":         "code",
        "redirect_uri":          REDIRECT_URI,
        "state":                 state,
        "code_challenge":        code_challenge,
        "code_challenge_method": "S256",
    }
    return AUTH_URL + "?" + urlencode(params)


def exchange_code(code: str, code_verifier: str) -> dict:
    resp = requests.post(TOKEN_URL, data={
        "client_key":     CLIENT_KEY,
        "client_secret":  CLIENT_SECRET,
        "code":           code,
        "grant_type":     "authorization_code",
        "redirect_uri":   REDIRECT_URI,
        "code_verifier":  code_verifier,
    })
    resp.raise_for_status()
    return resp.json()


def main():
    state = secrets.token_urlsafe(16)
    code_verifier, code_challenge = _pkce_pair()
    url = build_auth_url(state, code_challenge)

    print("Abriendo el navegador para autorizar la app en TikTok...")
    print(f"\nSi no se abre automáticamente, ve a:\n{url}\n")
    webbrowser.open(url)

    print("Después de autorizar, el navegador intentará ir a:")
    print(f"  {REDIRECT_URI}?code=...&state=...")
    print("Dará un error de conexión (normal). Copia la URL completa de la barra del navegador.")
    print()

    raw = input("Pega aquí la URL completa: ").strip()

    parsed = urlparse(raw)
    params = parse_qs(parsed.query)

    if "error" in params:
        print(f"Error de TikTok: {params['error']}")
        return

    if params.get("state", [None])[0] != state:
        print("State no coincide — posible CSRF. Abortando.")
        return

    code = params["code"][0]
    print(f"\nCódigo obtenido: {code[:10]}...")

    print("Intercambiando código por token...")
    data = exchange_code(code, code_verifier)

    if "access_token" not in data:
        print(f"Error: {json.dumps(data, indent=2)}")
        return

    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(TOKEN_PATH, "w") as f:
        json.dump(data, f, indent=2)

    print(f"\nToken guardado en {TOKEN_PATH}")
    print(f"  access_token:  {data['access_token'][:20]}...")
    print(f"  expires_in:    {data.get('expires_in')} s")
    print(f"  scope:         {data.get('scope')}")


if __name__ == "__main__":
    main()
