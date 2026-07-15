#!/usr/bin/env python3
"""Show recent posts from @rep_of_LLetters (or another user id/username).

  python3 twitter/timeline.py
  python3 twitter/timeline.py --user elonmusk --max 5
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from twitter.client import (  # noqa: E402
    get_user_tweets,
    lookup_username,
    my_user_id,
    print_json,
)


def main() -> None:
    p = argparse.ArgumentParser(description="User timeline")
    p.add_argument("--user", help="Username (without @). Default: authorized account")
    p.add_argument("--max", type=int, default=10, help="5–100 (default 10)")
    p.add_argument("--oauth2", action="store_true")
    p.add_argument("--raw", action="store_true")
    args = p.parse_args()

    if args.user:
        body = lookup_username(args.user, oauth2=args.oauth2)
        data = body.get("data") or {}
        uid = data.get("id")
        if not uid:
            print_json(body)
            raise SystemExit(f"Could not resolve @{args.user}")
        label = data.get("username") or args.user
    else:
        uid = my_user_id(oauth2=args.oauth2)
        label = "me"

    body = get_user_tweets(str(uid), max_results=args.max, oauth2=args.oauth2)
    if args.raw:
        print_json(body)
        return

    tweets = body.get("data") or []
    if not tweets:
        print(f"No tweets returned for @{label}.")
        print_json(body)
        return

    print(f"Timeline for @{label}:")
    for t in tweets:
        text = (t.get("text") or "").replace("\n", " ")
        metrics = t.get("public_metrics") or {}
        print(
            f"{t.get('id')}\t"
            f"❤{metrics.get('like_count', 0)} "
            f"↻{metrics.get('retweet_count', 0)} "
            f"💬{metrics.get('reply_count', 0)}\t"
            f"{text[:100]}"
        )
    print(f"\n({len(tweets)} post(s))")


if __name__ == "__main__":
    main()
