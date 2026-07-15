#!/usr/bin/env python3
"""Post a tweet (optionally with images).

  python3 twitter/tweet.py --text "hello -grok"
  python3 twitter/tweet.py --text "seal -grok" --image assets/profile/avatar-l-seal-LL-diagonal.jpg
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from twitter.client import create_tweet, report_tweet_result, upload_images  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser(description="Post a tweet via X API")
    p.add_argument("--text", required=True, help="Tweet body (sign with -grok / -claude / …)")
    p.add_argument(
        "--image",
        action="append",
        default=[],
        metavar="PATH",
        help="Attach image (repeat up to 4)",
    )
    p.add_argument("--quote", metavar="TWEET_ID", help="Quote-tweet this id")
    p.add_argument("--oauth2", action="store_true")
    args = p.parse_args()

    paths = [Path(x).expanduser().resolve() for x in args.image]
    media_ids = upload_images(paths, oauth2=args.oauth2) if paths else None
    result = create_tweet(
        args.text,
        media_ids=media_ids,
        quote_id=args.quote,
        oauth2=args.oauth2,
    )
    report_tweet_result(result)


if __name__ == "__main__":
    main()
