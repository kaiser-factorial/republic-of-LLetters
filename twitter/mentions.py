#!/usr/bin/env python3
"""List recent mentions of @rep_of_LLetters.

  python3 twitter/mentions.py
  python3 twitter/mentions.py --max 20
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from twitter.client import get_mentions, my_user_id, print_json  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser(description="List recent @mentions")
    p.add_argument("--max", type=int, default=10, help="5–100 (default 10)")
    p.add_argument("--oauth2", action="store_true")
    p.add_argument("--raw", action="store_true", help="Print full JSON only")
    args = p.parse_args()

    uid = my_user_id(oauth2=args.oauth2)
    body = get_mentions(uid, max_results=args.max, oauth2=args.oauth2)

    if args.raw:
        print_json(body)
        return

    users = {
        u["id"]: u
        for u in (body.get("includes") or {}).get("users") or []
        if "id" in u
    }
    tweets = body.get("data") or []
    if not tweets:
        print("No recent mentions (or free-tier read limit hit).")
        print_json(body)
        return

    for t in tweets:
        author = users.get(t.get("author_id") or "", {})
        handle = author.get("username", "?")
        text = (t.get("text") or "").replace("\n", " ")
        print(f"{t.get('id')}\t@{handle}\t{text[:120]}")
    print()
    print(f"({len(tweets)} mention(s))")


if __name__ == "__main__":
    main()
