#!/usr/bin/env python3
"""Delete a tweet by id.

  python3 twitter/delete.py --id 2077170704894869656
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from twitter.client import delete_tweet, print_json  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser(description="Delete a tweet")
    p.add_argument("--id", required=True, metavar="TWEET_ID")
    p.add_argument("--oauth2", action="store_true")
    args = p.parse_args()
    result = delete_tweet(args.id, oauth2=args.oauth2)
    print_json(result)


if __name__ == "__main__":
    main()
