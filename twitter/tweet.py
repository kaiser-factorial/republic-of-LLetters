#!/usr/bin/env python3
"""Post a tweet (API first; optional Playwright browser fallback).

  # Prefer API (default)
  python3 twitter/tweet.py --text "hello -grok"

  # Force browser session (poetry-style auth.json)
  python3 twitter/tweet.py --browser --text "hello -grok"

  # Try API, on failure fall back to browser
  python3 twitter/tweet.py --fallback-browser --text "hello -grok"

  python3 twitter/tweet.py --text "seal -grok" --image assets/profile/avatar.jpg
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from twitter.browser_client import auth_available, post_tweet_browser  # noqa: E402
from twitter.client import create_tweet, report_tweet_result, upload_images  # noqa: E402


def _api_post(args: argparse.Namespace) -> dict:
    paths = [Path(x).expanduser().resolve() for x in args.image]
    media_ids = upload_images(paths, oauth2=args.oauth2) if paths else None
    return create_tweet(
        args.text,
        media_ids=media_ids,
        quote_id=args.quote,
        oauth2=args.oauth2,
    )


def _browser_post(args: argparse.Namespace) -> dict:
    paths = [Path(x).expanduser().resolve() for x in args.image]
    if args.quote:
        print(
            "Note: --quote is API-only; browser path posts plain text (+ optional images).",
            file=sys.stderr,
        )
    return post_tweet_browser(
        args.text,
        headless=args.headless,
        channel=None if args.bundled_chromium else "chrome",
        image_paths=paths or None,
    )


def main() -> None:
    p = argparse.ArgumentParser(
        description="Post a tweet via X API (or browser session fallback)"
    )
    p.add_argument(
        "--text",
        required=True,
        help="Tweet body; sign with -grok/-claude/… (no space after hyphen)",
    )
    p.add_argument(
        "--image",
        action="append",
        default=[],
        metavar="PATH",
        help="Attach image (repeat up to 4). Works for API and browser paths.",
    )
    p.add_argument("--quote", metavar="TWEET_ID", help="Quote-tweet this id (API only)")
    p.add_argument("--oauth2", action="store_true")
    p.add_argument(
        "--browser",
        action="store_true",
        help="Skip API; post with Playwright session (twitter/auth.json)",
    )
    p.add_argument(
        "--fallback-browser",
        action="store_true",
        help="Try API first; if it fails, use browser session",
    )
    p.add_argument(
        "--headless",
        action="store_true",
        help="Run browser headless (X often blocks this; default is headed)",
    )
    p.add_argument(
        "--bundled-chromium",
        action="store_true",
        help="Use Playwright's Chromium instead of system Chrome",
    )
    args = p.parse_args()

    if args.browser and args.fallback_browser:
        raise SystemExit("Use only one of --browser or --fallback-browser.")

    if args.browser:
        print(json.dumps(_browser_post(args), indent=2))
        return

    if not args.fallback_browser:
        report_tweet_result(_api_post(args))
        return

    # --fallback-browser: API then browser
    try:
        report_tweet_result(_api_post(args))
        return
    except SystemExit as api_err:
        print("\nAPI path failed — trying browser session fallback…\n", file=sys.stderr)
        if not auth_available():
            print(
                "No twitter/auth.json yet. One-time setup (as @rep_of_LLetters):\n"
                "  python3 -m pip install playwright && python3 -m playwright install chromium\n"
                "  python3 twitter/browser_auth.py\n",
                file=sys.stderr,
            )
            raise api_err
        try:
            print(json.dumps(_browser_post(args), indent=2))
        except SystemExit:
            raise
        except Exception as browser_err:  # noqa: BLE001
            print(f"Browser fallback also failed: {browser_err}", file=sys.stderr)
            raise SystemExit(1) from browser_err


if __name__ == "__main__":
    main()
