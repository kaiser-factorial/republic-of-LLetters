"""Load and save secrets without committing them to git.

Search order for reads:
  1. Process environment
  2. Local .env (this folder — gitignored)
  3. Parent ../.secrets (AGENT_JOURNAL root — outside this git repo)
"""

from __future__ import annotations

import os
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
PARENT_SECRETS = HERE.parent / ".secrets"
LOCAL_ENV = HERE / ".env"

# Shared agent X account for the Republic of LLetters
EXPECTED_SCREEN_NAME = "rep_of_LLetters"

# Keys we care about for X API
KNOWN_KEYS = (
    "X_API_CONSUMER_KEY",
    "X_API_SECRET_KEY",
    "X_API_BEARER_TOKEN",
    "X_API_CLIENT_ID",
    "X_API_CLIENT_SECRET",
    "X_ACCESS_TOKEN",
    "X_ACCESS_TOKEN_SECRET",
    "X_SCREEN_NAME",
    "X_OAUTH2_ACCESS_TOKEN",
    "X_OAUTH2_REFRESH_TOKEN",
)


def warn_if_wrong_account(screen_name: str | None) -> None:
    """Print a clear warning if tokens are not for @rep_of_LLetters."""
    if not screen_name:
        return
    handle = screen_name.lstrip("@")
    if handle.lower() != EXPECTED_SCREEN_NAME.lower():
        print()
        print("!" * 60)
        print(f"WARNING: authorized as @{handle}")
        print(f"Expected:           @{EXPECTED_SCREEN_NAME}")
        print("Re-run authorize in a private window logged into the agents account.")
        print("!" * 60)

_LINE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$")


def _parse_file(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    out: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = _LINE.match(line)
        if not m:
            continue
        key, val = m.group(1), m.group(2)
        # strip optional surrounding quotes
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        out[key] = val
    return out


def load_secrets() -> dict[str, str]:
    """Merge parent .secrets, local .env, then process env (env wins)."""
    merged: dict[str, str] = {}
    merged.update(_parse_file(PARENT_SECRETS))
    merged.update(_parse_file(LOCAL_ENV))
    for key in KNOWN_KEYS:
        if key in os.environ and os.environ[key]:
            merged[key] = os.environ[key]
    return merged


def require(secrets: dict[str, str], *keys: str) -> None:
    missing = [k for k in keys if not secrets.get(k)]
    if missing:
        joined = ", ".join(missing)
        raise SystemExit(
            f"Missing required secret(s): {joined}\n"
            f"Add them to {PARENT_SECRETS} or {LOCAL_ENV} (see .env.example)."
        )


def upsert_secrets(updates: dict[str, str], *, target: Path | None = None) -> Path:
    """Create or update KEY=value lines in the secrets file. Returns path written."""
    path = target or PARENT_SECRETS
    existing_lines: list[str] = []
    if path.is_file():
        existing_lines = path.read_text(encoding="utf-8").splitlines()

    seen: set[str] = set()
    new_lines: list[str] = []
    for line in existing_lines:
        m = _LINE.match(line.strip()) if line.strip() and not line.strip().startswith("#") else None
        if m and m.group(1) in updates:
            key = m.group(1)
            new_lines.append(f"{key}={updates[key]}")
            seen.add(key)
        else:
            new_lines.append(line)

    for key, val in updates.items():
        if key not in seen:
            if new_lines and new_lines[-1].strip():
                new_lines.append("")
            new_lines.append(f"{key}={val}")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(new_lines).rstrip() + "\n", encoding="utf-8")
    # Keep parent secrets private-ish on multi-user machines
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return path
