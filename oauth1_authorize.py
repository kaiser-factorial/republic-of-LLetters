#!/usr/bin/env python3
"""OAuth 1.0a — get user access tokens for the agents' X account (RECOMMENDED).

Why OAuth 1.0a for this project?
  - Access tokens do not expire (until revoked) → perfect for a shared bot account
  - Four secrets, no refresh-token dance
  - Battle-tested path for "post as this user" bots

Before you run:
  1. Developer Portal → your app → User authentication settings
     - App permissions: Read and write
     - Type: Web App, Automated App or Bot (or Native)
     - Callback URL (for --mode callback): http://127.0.0.1:8765/callback
     - Website URL: any valid URL
  2. App permissions must be Read and write (not Read only)
  3. Put X_API_CONSUMER_KEY + X_API_SECRET_KEY in ../.secrets

Then:
  # PIN mode (easiest first time — no callback URL required if app allows PIN):
  python3 oauth1_authorize.py --mode pin

  # Local callback mode:
  python3 oauth1_authorize.py --mode callback

IMPORTANT: Log into X as @rep_of_LLetters in the browser (not your personal
account) before authorizing, or use a private window.
"""

from __future__ import annotations

import argparse
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from requests_oauthlib import OAuth1Session

# Allow `python oauth1_authorize.py` from this directory
sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib.secrets import (  # noqa: E402
    EXPECTED_SCREEN_NAME,
    load_secrets,
    require,
    upsert_secrets,
    warn_if_wrong_account,
)

REQUEST_TOKEN_URL = "https://api.x.com/oauth/request_token"
AUTHORIZE_URL = "https://api.x.com/oauth/authorize"
ACCESS_TOKEN_URL = "https://api.x.com/oauth/access_token"
VERIFY_URL = "https://api.x.com/1.1/account/verify_credentials.json"

DEFAULT_CALLBACK = "http://127.0.0.1:8765/callback"
DEFAULT_PORT = 8765


def _oauth_session(consumer_key: str, consumer_secret: str, **kwargs) -> OAuth1Session:
    return OAuth1Session(consumer_key, client_secret=consumer_secret, **kwargs)


def _fetch_request_token(
    consumer_key: str, consumer_secret: str, callback: str
) -> tuple[OAuth1Session, dict]:
    oauth = _oauth_session(consumer_key, consumer_secret, callback_uri=callback)
    try:
        tokens = oauth.fetch_request_token(REQUEST_TOKEN_URL)
    except Exception as exc:  # noqa: BLE001 — surface API errors clearly
        raise SystemExit(
            f"Failed to get request token: {exc}\n\n"
            "Checks:\n"
            "  • X_API_CONSUMER_KEY / X_API_SECRET_KEY are correct\n"
            "  • App has User authentication set up\n"
            "  • For callback mode, callback URL is registered exactly\n"
            f"    as: {callback}\n"
            "  • Try --mode pin if callback is not configured yet\n"
        ) from exc
    return oauth, tokens


def _authorize_url(oauth: OAuth1Session) -> str:
    return oauth.authorization_url(AUTHORIZE_URL)


def _exchange_access_token(
    consumer_key: str,
    consumer_secret: str,
    resource_owner_key: str,
    resource_owner_secret: str,
    verifier: str,
) -> dict:
    oauth = _oauth_session(
        consumer_key,
        consumer_secret,
        resource_owner_key=resource_owner_key,
        resource_owner_secret=resource_owner_secret,
        verifier=verifier,
    )
    return oauth.fetch_access_token(ACCESS_TOKEN_URL)


def _verify_user(consumer_key: str, consumer_secret: str, token: str, token_secret: str) -> dict:
    oauth = _oauth_session(
        consumer_key,
        consumer_secret,
        resource_owner_key=token,
        resource_owner_secret=token_secret,
    )
    r = oauth.get(VERIFY_URL, params={"skip_status": "true", "include_entities": "false"})
    r.raise_for_status()
    return r.json()


def _save_and_report(
    consumer_key: str,
    consumer_secret: str,
    access: dict,
) -> None:
    token = access["oauth_token"]
    secret = access["oauth_token_secret"]
    screen = access.get("screen_name") or ""

    try:
        me = _verify_user(consumer_key, consumer_secret, token, secret)
        screen = me.get("screen_name") or screen
        user_id = me.get("id_str") or me.get("id")
        name = me.get("name")
    except Exception as exc:  # noqa: BLE001
        print(f"(Could not verify credentials: {exc})")
        user_id, name = "?", "?"

    path = upsert_secrets(
        {
            "X_ACCESS_TOKEN": token,
            "X_ACCESS_TOKEN_SECRET": secret,
            "X_SCREEN_NAME": screen,
        }
    )

    print()
    print("=" * 60)
    print("SUCCESS — user access tokens saved")
    print("=" * 60)
    print(f"  Account:  @{screen}  ({name})")
    print(f"  User id:  {user_id}")
    print(f"  Expected: @{EXPECTED_SCREEN_NAME}")
    print(f"  Wrote:    {path}")
    warn_if_wrong_account(screen)
    print()
    print("Next:  python3 tweet.py --text 'hello from the Republic of LLetters'")
    print("=" * 60)


def run_pin(consumer_key: str, consumer_secret: str) -> None:
    """PIN-based OAuth (oob). Easiest when you haven't set a callback yet."""
    oauth, req = _fetch_request_token(consumer_key, consumer_secret, callback="oob")
    url = _authorize_url(oauth)
    print()
    print(f"Open this URL in a browser (logged in as @{EXPECTED_SCREEN_NAME}):")
    print()
    print(f"  {url}")
    print()
    try:
        webbrowser.open(url)
    except Exception:  # noqa: BLE001
        pass
    pin = input("Enter the PIN shown by X: ").strip()
    if not pin:
        raise SystemExit("No PIN entered.")
    access = _exchange_access_token(
        consumer_key,
        consumer_secret,
        req["oauth_token"],
        req["oauth_token_secret"],
        pin,
    )
    _save_and_report(consumer_key, consumer_secret, access)


def run_callback(consumer_key: str, consumer_secret: str, port: int) -> None:
    callback = f"http://127.0.0.1:{port}/callback"
    oauth, req = _fetch_request_token(consumer_key, consumer_secret, callback=callback)
    url = _authorize_url(oauth)

    result: dict[str, str] = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path not in ("/callback", "/"):
                self.send_response(404)
                self.end_headers()
                return
            qs = parse_qs(parsed.query)
            if "oauth_verifier" not in qs:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"Missing oauth_verifier. Try again.")
                return
            result["oauth_token"] = qs.get("oauth_token", [""])[0]
            result["oauth_verifier"] = qs["oauth_verifier"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                b"<html><body style='font-family:system-ui;padding:2rem'>"
                b"<h1>Authorized</h1>"
                b"<p>You can close this tab and return to the terminal.</p>"
                b"</body></html>"
            )

        def log_message(self, fmt, *args):  # quiet
            return

    print()
    print(f"Starting local callback server on {callback}")
    print("Make sure this exact URL is listed under your app's Callback URLs.")
    print()
    print(f"Open this URL (logged in as @{EXPECTED_SCREEN_NAME}):")
    print()
    print(f"  {url}")
    print()
    try:
        webbrowser.open(url)
    except Exception:  # noqa: BLE001
        pass

    httpd = HTTPServer(("127.0.0.1", port), Handler)
    while "oauth_verifier" not in result:
        httpd.handle_request()
    httpd.server_close()

    access = _exchange_access_token(
        consumer_key,
        consumer_secret,
        req["oauth_token"],
        req["oauth_token_secret"],
        result["oauth_verifier"],
    )
    _save_and_report(consumer_key, consumer_secret, access)


def main() -> None:
    parser = argparse.ArgumentParser(description="Authorize an X user via OAuth 1.0a")
    parser.add_argument(
        "--mode",
        choices=("pin", "callback"),
        default="pin",
        help="pin = enter a code (default, easiest); callback = local redirect",
    )
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="callback server port")
    args = parser.parse_args()

    secrets = load_secrets()
    require(secrets, "X_API_CONSUMER_KEY", "X_API_SECRET_KEY")
    ck, cs = secrets["X_API_CONSUMER_KEY"], secrets["X_API_SECRET_KEY"]

    print("OAuth 1.0a user authorization")
    print(f"Remember: authorize while logged into @{EXPECTED_SCREEN_NAME}.")

    if args.mode == "pin":
        run_pin(ck, cs)
    else:
        run_callback(ck, cs, args.port)


if __name__ == "__main__":
    main()
