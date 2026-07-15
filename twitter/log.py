#!/usr/bin/env python3
"""Show or sync the local tweet log.

  .venv/bin/python twitter/log.py
  .venv/bin/python twitter/log.py --limit 50
  .venv/bin/python twitter/log.py --sync
  .venv/bin/python twitter/log.py --paths
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from twitter.tweet_log import LOG_JSONL, LOG_MD, print_log, sync_from_api  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser(description="Tweet log for @rep_of_LLetters")
    p.add_argument("--limit", type=int, default=20, help="How many entries to show (default 20)")
    p.add_argument(
        "--sync",
        action="store_true",
        help="Pull recent posts from API into the log (needs working OAuth)",
    )
    p.add_argument("--paths", action="store_true", help="Print log file paths only")
    p.add_argument("--oauth2", action="store_true")
    args = p.parse_args()

    if args.paths:
        print(LOG_MD)
        print(LOG_JSONL)
        return

    if args.sync:
        try:
            n = sync_from_api(max_results=max(5, min(100, args.limit)), oauth2=args.oauth2)
        except SystemExit as exc:
            print(
                "API sync failed (tokens/portal?). Log file still works for local posts.\n"
                f"  {LOG_MD}",
                file=sys.stderr,
            )
            raise exc
        print(f"Synced {n} new post(s) into {LOG_MD}")

    print_log(limit=args.limit)


if __name__ == "__main__":
    main()
