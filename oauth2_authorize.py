#!/usr/bin/env python3
"""OAuth 2.0 PKCE — alternate path for user tokens (optional).

Recommendation for this project: prefer oauth1_authorize.py instead.

OAuth 2.0 is great for multi-user apps, but access tokens expire (~2 hours)
unless you refresh them with offline.access. Extra moving parts for a
single shared bot account.

Requires in ../.secrets:
  X_API_CLIENT_ID
  X_API_CLIENT_SECRET   (confidential clients; omit if public/native only)

App setup:
  User authentication settings → OAuth 2.0 enabled
  Callback URI: http://127.0.0.1:8765/callback
  Scopes used: tweet.read tweet.write users.read offline.access
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import secrets as pysecrets
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib.secrets import (  # noqa: E402
    EXPECTED_SCREEN_NAME,
    load_secrets,
    require,
    upsert_secrets,
    warn_if_wrong_account,
)

AUTHORIZE_URL = "https://x.com/i/oauth2/authorize"
TOKEN_URL = "https://api.x.com/2/oauth2/token"
ME_URL = "https://api.x.com/2/users/me"

DEFAULT_PORT = 8765
SCOPES = "tweet.read tweet.write users.read offline.access"


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _pkce_pair() -> tuple[str, str]:
    verifier = _b64url(pysecrets.token_bytes(32))
    challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
    return verifier, challenge


def main() -> None:
    parser = argparse.ArgumentParser(description="Authorize an X user via OAuth 2.0 PKCE")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()

    conf = load_secrets()
    require(conf, "X_API_CLIENT_ID")
    client_id = conf["X_API_CLIENT_ID"]
    client_secret = conf.get("X_API_CLIENT_SECRET") or ""

    redirect_uri = f"http://127.0.0.1:{args.port}/callback"
    state = _b64url(pysecrets.token_bytes(16))
    verifier, challenge = _pkce_pair()

    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": SCOPES,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    auth_url = f"{AUTHORIZE_URL}?{urlencode(params)}"

    result: dict[str, str] = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            parsed = urlparse(self.path)
            qs = parse_qs(parsed.query)
            if "error" in qs:
                result["error"] = qs["error"][0]
                result["error_description"] = qs.get("error_description", [""])[0]
            else:
                result["code"] = qs.get("code", [""])[0]
                result["state"] = qs.get("state", [""])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                b"<html><body style='font-family:system-ui;padding:2rem'>"
                b"<h1>Authorized</h1><p>Return to the terminal.</p></body></html>"
            )

        def log_message(self, fmt, *args):  # quiet
            return

    print("OAuth 2.0 PKCE user authorization")
    print(f"Remember: authorize while logged into @{EXPECTED_SCREEN_NAME}.")
    print()
    print(f"Callback must be registered exactly as: {redirect_uri}")
    print()
    print("Open this URL:")
    print()
    print(f"  {auth_url}")
    print()
    try:
        webbrowser.open(auth_url)
    except Exception:  # noqa: BLE001
        pass

    httpd = HTTPServer(("127.0.0.1", args.port), Handler)
    while not result:
        httpd.handle_request()
    httpd.server_close()

    if result.get("error"):
        raise SystemExit(f"Authorization error: {result['error']} {result.get('error_description')}")
    if result.get("state") != state:
        raise SystemExit("State mismatch — aborting (possible CSRF).")
    code = result.get("code")
    if not code:
        raise SystemExit("No authorization code returned.")

    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "code_verifier": verifier,
        "client_id": client_id,
    }
    auth = (client_id, client_secret) if client_secret else None
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    r = requests.post(TOKEN_URL, data=data, headers=headers, auth=auth, timeout=30)
    if r.status_code >= 400:
        raise SystemExit(f"Token exchange failed ({r.status_code}): {r.text}")

    tokens = r.json()
    access = tokens["access_token"]
    refresh = tokens.get("refresh_token", "")

    me = requests.get(
        ME_URL,
        headers={"Authorization": f"Bearer {access}"},
        params={"user.fields": "username,name"},
        timeout=30,
    )
    username = "?"
    if me.ok:
        u = me.json().get("data") or {}
        username = u.get("username") or "?"
        print(f"Authorized as @{username} ({u.get('name')})")
        print(f"Expected:     @{EXPECTED_SCREEN_NAME}")
        warn_if_wrong_account(username if username != "?" else None)
    else:
        print(f"(Could not fetch /2/users/me: {me.status_code} {me.text})")

    path = upsert_secrets(
        {
            "X_OAUTH2_ACCESS_TOKEN": access,
            "X_OAUTH2_REFRESH_TOKEN": refresh,
            "X_SCREEN_NAME": username if username != "?" else conf.get("X_SCREEN_NAME", ""),
        }
    )
    print()
    print(f"Saved OAuth 2 tokens to {path}")
    print("Note: access tokens expire; use the refresh token or switch to OAuth 1.0a.")
    print("Posting with OAuth 2: python3 tweet.py --oauth2 --text 'hello'")


if __name__ == "__main__":
    main()
