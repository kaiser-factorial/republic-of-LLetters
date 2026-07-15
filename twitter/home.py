#!/usr/bin/env python3
"""Read the home (following) timeline via browser session.

Free-tier API often cannot read home feed; this uses Playwright + auth.json.

  python3 twitter/home.py
  python3 twitter/home.py --max 20
  python3 twitter/home.py --raw
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from twitter.browser_client import read_home_timeline_browser  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser(description="Home timeline (browser session)")
    p.add_argument("--max", type=int, default=15, help="Max posts to scrape (default 15)")
    p.add_argument("--raw", action="store_true", help="Print full JSON")
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

    body = read_home_timeline_browser(
        max_posts=max(1, min(40, args.max)),
        headless=args.headless,
        channel="chrome" if args.system_chrome else None,
    )
    if args.raw:
        print(json.dumps(body, indent=2))
        return

    posts = body.get("posts") or []
    if not posts:
        print("No posts scraped from home timeline.")
        print(json.dumps(body, indent=2))
        return

    print(f"Home timeline ({len(posts)} post(s)):")
    for t in posts:
        tid = t.get("id") or "—"
        user = t.get("user") or "?"
        text = (t.get("text") or "")[:120]
        print(f"{tid}\t@{user}\t{text}")
    print()


if __name__ == "__main__":
    main()
