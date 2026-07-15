#!/usr/bin/env python3
"""Look up an X user by username.

  python3 twitter/user.py --user rep_of_LLetters
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from twitter.client import lookup_username, print_json  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser(description="Look up a user")
    p.add_argument("--user", required=True, help="Username without or with @")
    p.add_argument("--oauth2", action="store_true")
    args = p.parse_args()
    body = lookup_username(args.user, oauth2=args.oauth2)
    print_json(body)
    data = body.get("data") or {}
    if data.get("username"):
        m = data.get("public_metrics") or {}
        print(
            f"\n@{data['username']} — {data.get('name')}\n"
            f"  followers={m.get('followers_count')} following={m.get('following_count')} "
            f"posts={m.get('tweet_count')}"
        )


if __name__ == "__main__":
    main()
