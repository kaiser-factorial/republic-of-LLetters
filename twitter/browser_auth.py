#!/usr/bin/env python3
"""One-time browser login for the Playwright fallback (poetry_consciousness style).

Saves a session to twitter/auth.json (gitignored). Must be logged in as
@rep_of_LLetters — not a personal account.

  python3 twitter/browser_auth.py

Requires:
  python3 -m pip install playwright
  python3 -m playwright install chromium
  # optional: use system Chrome with --channel chrome (default)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

AUTH_FILE = Path(__file__).resolve().parent / "auth.json"
EXPECTED = "rep_of_LLetters"


def main() -> None:
    p = argparse.ArgumentParser(description="Save X browser session for fallback tweeting")
    p.add_argument(
        "--channel",
        default="chrome",
        help="Playwright browser channel (chrome|msedge|chromium). Empty = bundled chromium.",
    )
    p.add_argument(
        "--auth-file",
        type=Path,
        default=AUTH_FILE,
        help=f"Where to write storage state (default: {AUTH_FILE})",
    )
    args = p.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise SystemExit(
            "playwright not installed.\n"
            "  python3 -m pip install playwright\n"
            "  python3 -m playwright install chromium"
        )

    auth_path = args.auth_file.expanduser().resolve()
    launch_kwargs: dict = {
        "headless": False,
        "args": ["--disable-blink-features=AutomationControlled"],
    }
    if args.channel:
        launch_kwargs["channel"] = args.channel

    print(f"Will save session to: {auth_path}")
    print(f"Log in as @{EXPECTED} (private window / correct account).")
    print()

    with sync_playwright() as pwt:
        try:
            browser = pwt.chromium.launch(**launch_kwargs)
        except Exception as exc:  # noqa: BLE001
            if args.channel:
                print(f"Launch with channel={args.channel!r} failed ({exc}); trying bundled chromium…")
                launch_kwargs.pop("channel", None)
                browser = pwt.chromium.launch(**launch_kwargs)
            else:
                raise
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            )
        )
        page = context.new_page()
        page.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        page.goto("https://x.com/login", wait_until="domcontentloaded")
        input("Log in as @rep_of_LLetters in the browser, then press Enter here… ")
        context.storage_state(path=str(auth_path))
        browser.close()

    try:
        auth_path.chmod(0o600)
    except OSError:
        pass

    print(f"Auth saved to {auth_path}")
    print("Test:  python3 twitter/tweet.py --browser --text 'browser auth check -grok'")


if __name__ == "__main__":
    main()
