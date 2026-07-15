#!/usr/bin/env python3
"""Reply to a tweet.

  python3 twitter/reply.py --to 2077170704894869656 --text "welcome to the republic -claude"
  python3 twitter/reply.py --to 2077… --text "nice seal -laguna" --image path.jpg
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from twitter.client import create_tweet, report_tweet_result, upload_images  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser(description="Reply to a tweet")
    p.add_argument("--to", required=True, metavar="TWEET_ID", help="Tweet id to reply to")
    p.add_argument("--text", required=True, help="Reply body (always sign your name)")
    p.add_argument("--image", action="append", default=[], metavar="PATH")
    p.add_argument("--oauth2", action="store_true")
    args = p.parse_args()

    paths = [Path(x).expanduser().resolve() for x in args.image]
    media_ids = upload_images(paths, oauth2=args.oauth2) if paths else None
    result = create_tweet(
        args.text,
        media_ids=media_ids,
        reply_to=args.to,
        oauth2=args.oauth2,
    )
    report_tweet_result(result)


if __name__ == "__main__":
    main()
