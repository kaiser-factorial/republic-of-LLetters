#!/usr/bin/env python3
"""Follow or unfollow a user (API first; optional browser fallback).

  python3 twitter/follow.py --user lumpenspace
  python3 twitter/follow.py --user voooooogel --fallback-browser
  python3 twitter/follow.py --user someone --unfollow
  python3 twitter/follow.py --browser --user viemccoy
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from twitter.browser_client import auth_available, follow_user_browser  # noqa: E402
from twitter.client import follow_username, print_json  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser(description="Follow or unfollow an X user")
    p.add_argument("--user", required=True, help="Username (with or without @)")
    p.add_argument("--unfollow", action="store_true", help="Unfollow instead of follow")
    p.add_argument("--oauth2", action="store_true")
    p.add_argument(
        "--browser",
        action="store_true",
        help="Skip API; use Playwright session (twitter/auth.json)",
    )
    p.add_argument(
        "--fallback-browser",
        action="store_true",
        help="Try API first; if it fails, use browser session",
    )
    p.add_argument("--headless", action="store_true")
    p.add_argument(
        "--bundled-chromium",
        action="store_true",
        help="(default) Use Playwright's Chromium",
    )
    p.add_argument(
        "--system-chrome",
        action="store_true",
        help="Use system Google Chrome (can leave about:blank tabs)",
    )
    args = p.parse_args()

    if args.browser and args.fallback_browser:
        raise SystemExit("Use only one of --browser or --fallback-browser.")

    uname = args.user.lstrip("@")

    def _browser() -> dict:
        return follow_user_browser(
            uname,
            unfollow=args.unfollow,
            headless=args.headless,
            channel="chrome" if args.system_chrome else None,
        )

    if args.browser:
        print(json.dumps(_browser(), indent=2))
        return

    if not args.fallback_browser:
        print_json(follow_username(uname, unfollow=args.unfollow, oauth2=args.oauth2))
        return

    try:
        print_json(follow_username(uname, unfollow=args.unfollow, oauth2=args.oauth2))
        return
    except SystemExit as api_err:
        print("\nAPI path failed — trying browser session fallback…\n", file=sys.stderr)
        if not auth_available():
            print(
                "No twitter/auth.json yet. One-time setup (as @rep_of_LLetters):\n"
                "  python3 twitter/browser_auth.py\n",
                file=sys.stderr,
            )
            raise api_err
        try:
            print(json.dumps(_browser(), indent=2))
        except SystemExit:
            raise
        except Exception as browser_err:  # noqa: BLE001
            print(f"Browser fallback also failed: {browser_err}", file=sys.stderr)
            raise SystemExit(1) from browser_err


if __name__ == "__main__":
    main()
