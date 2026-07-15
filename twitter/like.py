#!/usr/bin/env python3
"""Like (or unlike) a tweet.

  python3 twitter/like.py --id 2077170704894869656
  python3 twitter/like.py --id 2077… --unlike
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from twitter.client import like_tweet, print_json  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser(description="Like or unlike a tweet")
    p.add_argument("--id", required=True, metavar="TWEET_ID")
    p.add_argument("--unlike", action="store_true")
    p.add_argument("--oauth2", action="store_true")
    args = p.parse_args()
    result = like_tweet(args.id, unlike=args.unlike, oauth2=args.oauth2)
    print_json(result)


if __name__ == "__main__":
    main()
