"""
TikTok OAuth — one-time token acquisition.

Run this on a machine with a browser (Windows/Mac).
Opens TikTok's authorization page, captures the callback automatically
via a local HTTP server, and saves the access + refresh tokens to
data/tiktok_token.json.

Usage:
    python tiktok_auth.py
"""

import hashlib
import json
import os
import secrets
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import requests
from dotenv import load_dotenv

load_dotenv()

CLIENT_KEY    = os.environ["TIKTOK_CLIENT_KEY"]
CLIENT_SECRET = os.environ["TIKTOK_CLIENT_SECRET"]
REDIRECT_URI  = "http://localhost:8080/callback"
SCOPES        = "user.info.basic,video.upload,video.publish"
TOKEN_PATH    = Path("data/tiktok_token.json")

AUTH_URL  = "https://www.tiktok.com/v2/auth/authorize/"
TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"


def _pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_hex(32)  # 64 hex chars, [0-9a-f] only
    # TikTok requires hex encoding of SHA256 (not standard base64url)
    challenge = hashlib.sha256(verifier.encode("ascii")).hexdigest()
    return verifier, challenge


def build_auth_url(state: str, challenge: str) -> str:
    params = {
        "client_key":            CLIENT_KEY,
        "scope":                 SCOPES,
        "response_type":         "code",
        "redirect_uri":          REDIRECT_URI,
        "state":                 state,
        "code_challenge":        challenge,
        "code_challenge_method": "S256",
    }
    return AUTH_URL + "?" + urlencode(params)


def exchange_code(code: str, verifier: str) -> dict:
    body = {
        "client_key":    CLIENT_KEY,
        "client_secret": CLIENT_SECRET,
        "code":          code,
        "grant_type":    "authorization_code",
        "redirect_uri":  REDIRECT_URI,
        "code_verifier": verifier,
    }
    print(f"  [debug] verifier ({len(verifier)} chars): {verifier[:20]}...")
    resp = requests.post(
        TOKEN_URL, data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    print(f"  [debug] status: {resp.status_code}")
    return resp.json()


def _wait_for_callback(state: str) -> dict:
    """Start a local HTTP server and block until TikTok redirects to it."""
    result = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query, keep_blank_values=True)
            result.update({k: v[0] for k, v in params.items()})
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                b"<h2>Autorizado. Puedes cerrar esta ventana.</h2>"
            )

        def log_message(self, *args):
            pass  # suppress server logs

    server = HTTPServer(("localhost", 8080), Handler)
    server.handle_request()  # serve exactly one request then stop
    server.server_close()
    return result


def main():
    state = secrets.token_urlsafe(16)
    verifier, challenge = _pkce_pair()
    url = build_auth_url(state, challenge)

    print("Abriendo el navegador para autorizar la app en TikTok...")
    print(f"\nSi no se abre automáticamente, ve a:\n{url}\n")
    webbrowser.open(url)
    print("Esperando callback en http://localhost:8080/callback ...")

    params = _wait_for_callback(state)

    if "error" in params:
        print(f"Error de TikTok: {params['error']}")
        return

    if params.get("state") != state:
        print("State no coincide — posible CSRF. Abortando.")
        return

    code = params["code"]
    print(f"\nCódigo capturado automáticamente: {code[:10]}...")
    print(f"  [debug] código completo ({len(code)} chars): {code}")

    print("Intercambiando código por token...")
    data = exchange_code(code, verifier)

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
