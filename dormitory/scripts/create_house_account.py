#!/usr/bin/env python3
"""Create the one password-protected dormitory resident account."""

from __future__ import annotations

import argparse
import getpass
import json
import os
from pathlib import Path
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DORMITORY_ROOT = Path(__file__).resolve().parents[1]


def read_browser_config() -> tuple[str, str]:
    config = (DORMITORY_ROOT / "config.js").read_text()
    url_match = re.search(r"window\.SUPABASE_URL = '([^']+)'", config)
    email_match = re.search(r"window\.DORMITORY_HOUSE_AUTH_EMAIL = '([^']+)'", config)
    if not url_match or not email_match:
        raise RuntimeError("config.js is missing the Supabase URL or house account email")
    return url_match.group(1), email_match.group(1)


def prompt_password() -> str:
    password = getpass.getpass("New shared house key (16+ characters): ")
    if len(password) < 16:
        raise ValueError("Use a house key with at least 16 characters")
    confirmation = getpass.getpass("Confirm shared house key: ")
    if password != confirmation:
        raise ValueError("House keys did not match")
    return password


def create_account(secret_key: str, password: str) -> dict:
    supabase_url, house_email = read_browser_config()
    body = json.dumps(
        {
            "email": house_email,
            "password": password,
            "email_confirm": True,
            "app_metadata": {"dormitory_role": "resident"},
        }
    ).encode()
    request = Request(
        f"{supabase_url}/auth/v1/admin/users",
        data=body,
        method="POST",
        headers={
            "apikey": secret_key,
            "Authorization": f"Bearer {secret_key}",
            "Content-Type": "application/json",
        },
    )
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create the shared Supabase Auth resident account for the dormitory"
    )
    parser.parse_args()

    secret_key = (
        os.environ.get("SUPABASE_SECRET_KEY")
        or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        or getpass.getpass("Supabase secret/service-role key (hidden): ")
    )
    if not secret_key:
        print("A Supabase secret key is required.", file=sys.stderr)
        return 2

    try:
        password = prompt_password()
        account = create_account(secret_key, password)
    except (RuntimeError, ValueError) as error:
        print(error, file=sys.stderr)
        return 2
    except HTTPError as error:
        details = error.read().decode(errors="replace")
        print(f"Supabase rejected the account: HTTP {error.code} {details}", file=sys.stderr)
        return 1
    except URLError as error:
        print(f"Could not reach Supabase: {error.reason}", file=sys.stderr)
        return 1

    configured_email = account.get("email") or read_browser_config()[1]
    print(f"Created the shared resident account as {configured_email}.")
    print("The house key was not written to disk. Store it in a password manager.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
