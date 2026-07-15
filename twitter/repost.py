#!/usr/bin/env python3
"""Repost (retweet) or undo.

  python3 twitter/repost.py --id 2077170704894869656
  python3 twitter/repost.py --id 2077… --undo
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from twitter.client import print_json, repost_tweet  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser(description="Repost or undo a repost")
    p.add_argument("--id", required=True, metavar="TWEET_ID")
    p.add_argument("--undo", action="store_true")
    p.add_argument("--oauth2", action="store_true")
    args = p.parse_args()
    result = repost_tweet(args.id, undo=args.undo, oauth2=args.oauth2)
    print_json(result)


if __name__ == "__main__":
    main()
