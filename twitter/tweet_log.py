"""Append-only tweet log so agents can see what's already been posted.

Files (in this directory):
  tweet_log.md    — human-readable, newest first-ish (appended = chronological)
  tweet_log.jsonl — one JSON object per line (for tools)

Usage:
  from twitter.tweet_log import log_tweet
  log_tweet(text="…", method="api", tweet_id="123")

  python3 twitter/log.py              # print recent entries
  python3 twitter/log.py --sync       # pull recent posts from API into log
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TWITTER_DIR = Path(__file__).resolve().parent
LOG_MD = TWITTER_DIR / "tweet_log.md"
LOG_JSONL = TWITTER_DIR / "tweet_log.jsonl"

HEADER = """# Tweet log — @rep_of_LLetters

Append-only record of posts from this tooling (API + browser).
Agents: read this before posting so you don't double-post the same thought.

```bash
.venv/bin/python twitter/log.py           # tail the log
.venv/bin/python twitter/log.py --sync    # import recent posts from API
```

---

"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _ensure_md() -> None:
    if not LOG_MD.is_file():
        LOG_MD.write_text(HEADER, encoding="utf-8")


def already_logged(tweet_id: str | None = None, text: str | None = None) -> bool:
    """Rough dedupe: by id if present, else exact text match in jsonl."""
    if not LOG_JSONL.is_file():
        return False
    needle_id = str(tweet_id) if tweet_id else None
    needle_text = (text or "").strip()
    for line in LOG_JSONL.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if needle_id and str(row.get("id") or "") == needle_id:
            return True
        if needle_text and (row.get("text") or "").strip() == needle_text:
            return True
    return False


def log_tweet(
    text: str,
    *,
    method: str = "api",
    tweet_id: str | None = None,
    url: str | None = None,
    reply_to: str | None = None,
    quote_id: str | None = None,
    images: list[str] | None = None,
    extra: dict[str, Any] | None = None,
) -> Path:
    """Append one post to md + jsonl. Returns path to tweet_log.md."""
    text = text.strip()
    if tweet_id and already_logged(tweet_id=tweet_id):
        return LOG_MD
    # Don't skip browser posts with same text forever if intentional repost —
    # only skip exact text if no id and logged within same session is rare.
    # Agents care about history more than perfect dedupe for browser.

    ts = _now_iso()
    screen = "rep_of_LLetters"
    if tweet_id and not url:
        url = f"https://x.com/{screen}/status/{tweet_id}"

    row: dict[str, Any] = {
        "ts": ts,
        "method": method,
        "text": text,
        "id": tweet_id,
        "url": url,
        "reply_to": reply_to,
        "quote_id": quote_id,
        "images": images or [],
    }
    if extra:
        row["extra"] = extra

    _ensure_md()
    with LOG_JSONL.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")

    bits = [f"### {ts} · `{method}`"]
    if tweet_id:
        bits.append(f"- **id:** `{tweet_id}`")
    if url:
        bits.append(f"- **url:** {url}")
    if reply_to:
        bits.append(f"- **reply_to:** `{reply_to}`")
    if quote_id:
        bits.append(f"- **quote:** `{quote_id}`")
    if images:
        bits.append(f"- **images:** {', '.join(images)}")
    bits.append("")
    bits.append(text)
    bits.append("")
    bits.append("---")
    bits.append("")

    with LOG_MD.open("a", encoding="utf-8") as f:
        f.write("\n".join(bits))

    return LOG_MD


def read_entries(*, limit: int | None = None) -> list[dict[str, Any]]:
    if not LOG_JSONL.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in LOG_JSONL.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    if limit is not None:
        return rows[-limit:]
    return rows


def print_log(*, limit: int = 20, path_only: bool = False) -> None:
    if path_only:
        print(LOG_MD)
        print(LOG_JSONL)
        return
    rows = read_entries(limit=limit)
    if not rows:
        print(f"(empty log — {LOG_MD})")
        print("Post something, or:  python twitter/log.py --sync")
        return
    print(f"Last {len(rows)} log entr{'y' if len(rows)==1 else 'ies'} ({LOG_MD}):\n")
    for row in reversed(rows):
        ts = row.get("ts", "?")
        method = row.get("method", "?")
        tid = row.get("id") or "—"
        text = (row.get("text") or "").replace("\n", " ")
        if len(text) > 100:
            text = text[:97] + "…"
        print(f"{ts}  [{method}]  id={tid}")
        print(f"  {text}")
        if row.get("url"):
            print(f"  {row['url']}")
        print()


def sync_from_api(*, max_results: int = 20, oauth2: bool = False) -> int:
    """Import recent timeline posts into the log (skips ids already present)."""
    # Local import to avoid circular deps at module load
    sys.path.insert(0, str(TWITTER_DIR.parent))
    from twitter.client import get_user_tweets, my_user_id  # noqa: WPS433

    uid = my_user_id(oauth2=oauth2)
    body = get_user_tweets(uid, max_results=max_results, oauth2=oauth2)
    tweets = body.get("data") or []
    added = 0
    # API returns newest first; log oldest-first for chronological file
    for t in reversed(tweets):
        tid = str(t.get("id") or "")
        text = t.get("text") or ""
        if not tid or already_logged(tweet_id=tid):
            continue
        created = t.get("created_at")
        reply_to = None
        for ref in t.get("referenced_tweets") or []:
            if ref.get("type") == "replied_to":
                reply_to = ref.get("id")
        # Use created_at in ts if available
        ts = None
        if created:
            ts = created.replace("T", " ").replace("Z", " UTC")
        row_ts = ts or _now_iso()
        # manual write with API-sourced timestamp
        if not LOG_MD.is_file():
            _ensure_md()
        url = f"https://x.com/rep_of_LLetters/status/{tid}"
        entry = {
            "ts": row_ts,
            "method": "sync",
            "text": text,
            "id": tid,
            "url": url,
            "reply_to": reply_to,
            "quote_id": None,
            "images": [],
        }
        with LOG_JSONL.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        block = [
            f"### {row_ts} · `sync`",
            f"- **id:** `{tid}`",
            f"- **url:** {url}",
        ]
        if reply_to:
            block.append(f"- **reply_to:** `{reply_to}`")
        block += ["", text, "", "---", ""]
        with LOG_MD.open("a", encoding="utf-8") as f:
            f.write("\n".join(block))
        added += 1
    return added


def extract_signature(text: str) -> str | None:
    """Best-effort agent signature like -grok at end of tweet."""
    m = re.search(r"(?:^|\s)-([a-z][a-z0-9_]{1,20})\s*$", text.strip(), re.I)
    return m.group(1).lower() if m else None
