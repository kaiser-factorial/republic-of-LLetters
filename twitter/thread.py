#!/usr/bin/env python3
"""Post a thread (each line = one tweet, chained as replies).

  python3 twitter/thread.py --file thread.txt
  python3 twitter/thread.py --text "first -grok" --text "second -grok" --text "third -grok"

File format: one tweet per paragraph separated by a blank line, OR one per line
if you pass --lines. Always sign each post.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from twitter.client import create_tweet, print_json, tweet_url  # noqa: E402


def _parts_from_file(path: Path, *, by_line: bool) -> list[str]:
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        raise SystemExit(f"Empty file: {path}")
    if by_line:
        return [ln.strip() for ln in raw.splitlines() if ln.strip()]
    # blank-line separated paragraphs
    chunks = [c.strip() for c in raw.split("\n\n")]
    return [c for c in chunks if c]


def main() -> None:
    p = argparse.ArgumentParser(description="Post a multi-tweet thread")
    p.add_argument("--text", action="append", default=[], help="Tweet body (repeat)")
    p.add_argument("--file", type=Path, help="Read thread body from file")
    p.add_argument(
        "--lines",
        action="store_true",
        help="With --file: each non-empty line is a tweet (default: blank-line paragraphs)",
    )
    p.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Seconds between posts (default 1.0; free tier is fragile)",
    )
    p.add_argument("--oauth2", action="store_true")
    args = p.parse_args()

    parts: list[str] = list(args.text)
    if args.file:
        parts.extend(_parts_from_file(args.file.expanduser().resolve(), by_line=args.lines))
    if len(parts) < 2:
        raise SystemExit("A thread needs at least 2 posts (--text twice, or a --file).")

    for i, t in enumerate(parts, 1):
        if len(t) > 280:
            raise SystemExit(f"Post {i} is {len(t)} chars (limit 280).")

    ids: list[str] = []
    prev: str | None = None
    for i, text in enumerate(parts, 1):
        print(f"Posting {i}/{len(parts)}…", file=sys.stderr)
        result = create_tweet(text, reply_to=prev, oauth2=args.oauth2)
        tid = (result.get("data") or {}).get("id")
        if not tid:
            print_json(result)
            raise SystemExit(f"Thread stopped at post {i}: no id returned.")
        ids.append(str(tid))
        prev = str(tid)
        print(f"  → {tweet_url(str(tid))}", file=sys.stderr)
        if i < len(parts) and args.delay > 0:
            time.sleep(args.delay)

    print_json({"data": {"thread_ids": ids, "root_id": ids[0]}})
    print(f"\nThread root: {tweet_url(ids[0])}")


if __name__ == "__main__":
    main()
