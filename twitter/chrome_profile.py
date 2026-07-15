"""Resolve system Chrome profiles for Playwright (e.g. republic → Profile 4)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# macOS default; override with CHROME_USER_DATA_DIR
DEFAULT_CHROME_USER_DATA = (
    Path.home() / "Library/Application Support/Google/Chrome"
)


def chrome_user_data_dir() -> Path:
    raw = os.environ.get("CHROME_USER_DATA_DIR", "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return DEFAULT_CHROME_USER_DATA


def list_chrome_profiles(user_data_dir: Path | None = None) -> list[dict[str, str]]:
    """Return [{dir, name, user}, …] from Chrome Local State."""
    root = user_data_dir or chrome_user_data_dir()
    local_state = root / "Local State"
    if not local_state.is_file():
        return []
    try:
        data = json.loads(local_state.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    cache = (data.get("profile") or {}).get("info_cache") or {}
    out: list[dict[str, str]] = []
    for dirname, meta in cache.items():
        if not isinstance(meta, dict):
            continue
        out.append(
            {
                "dir": dirname,
                "name": str(meta.get("name") or ""),
                "user": str(meta.get("user_name") or meta.get("gaia_name") or ""),
            }
        )
    # stable-ish order: Default first, then Profile N
    def _key(row: dict[str, str]) -> tuple:
        d = row["dir"]
        if d == "Default":
            return (0, d)
        if d.startswith("Profile "):
            try:
                return (1, int(d.split(" ", 1)[1]))
            except ValueError:
                return (2, d)
        return (3, d)

    return sorted(out, key=_key)


def resolve_chrome_profile(
    spec: str,
    *,
    user_data_dir: Path | None = None,
) -> tuple[Path, str, dict[str, str]]:
    """Map 'republic' / 'Profile 4' → (user_data_dir, profile_directory, meta).

    `spec` may be:
      - display name (case-insensitive): republic, Work, …
      - directory name: Profile 4, Default
      - gaia email / user_name substring
    """
    root = user_data_dir or chrome_user_data_dir()
    if not root.is_dir():
        raise SystemExit(f"Chrome user data dir not found: {root}")

    profiles = list_chrome_profiles(root)
    if not profiles:
        # still allow raw Profile N if the folder exists
        candidate = root / spec
        if (root / spec).is_dir() or spec in ("Default",):
            return root, spec, {"dir": spec, "name": spec, "user": ""}
        raise SystemExit(
            f"No Chrome profiles found under {root}\n"
            "Is Google Chrome installed?"
        )

    s = spec.strip()
    s_lower = s.lower()

    # exact directory
    for row in profiles:
        if row["dir"].lower() == s_lower:
            return root, row["dir"], row

    # exact display name
    for row in profiles:
        if row["name"].lower() == s_lower:
            return root, row["dir"], row

    # email / user substring
    for row in profiles:
        if s_lower in (row["user"] or "").lower():
            return root, row["dir"], row

    # partial name
    matches = [r for r in profiles if s_lower in (r["name"] or "").lower()]
    if len(matches) == 1:
        return root, matches[0]["dir"], matches[0]
    if len(matches) > 1:
        lines = ", ".join(f"{m['name']!r} ({m['dir']})" for m in matches)
        raise SystemExit(f"Ambiguous profile {spec!r}: {lines}")

    # folder exists even if not in Local State
    if (root / s).is_dir():
        return root, s, {"dir": s, "name": s, "user": ""}

    known = "\n".join(
        f"  {r['dir']:12}  name={r['name']!r:16}  user={r['user']!r}" for r in profiles
    )
    raise SystemExit(
        f"Unknown Chrome profile {spec!r}. Known profiles:\n{known}\n"
        f"user_data_dir={root}"
    )


def env_chrome_profile() -> str | None:
    """Optional default from env (REPUBLIC_CHROME_PROFILE or CHROME_PROFILE)."""
    for key in ("REPUBLIC_CHROME_PROFILE", "CHROME_PROFILE"):
        v = os.environ.get(key, "").strip()
        if v:
            return v
    return None


def print_profiles(user_data_dir: Path | None = None) -> None:
    root = user_data_dir or chrome_user_data_dir()
    rows = list_chrome_profiles(root)
    print(f"Chrome user data: {root}")
    if not rows:
        print("  (no profiles found)")
        return
    for r in rows:
        print(f"  {r['dir']:12}  name={r['name']!r:16}  user={r['user']!r}")


def persistent_launch_kwargs(
    profile_spec: str,
    *,
    user_data_dir: Path | None = None,
    headless: bool = False,
    channel: str | None = "chrome",
    slow_mo_ms: int = 0,
    extra_args: list[str] | None = None,
) -> tuple[Path, dict]:
    """Build kwargs for chromium.launch_persistent_context."""
    root, profile_dir, meta = resolve_chrome_profile(
        profile_spec, user_data_dir=user_data_dir
    )
    args = [
        "--disable-blink-features=AutomationControlled",
        f"--profile-directory={profile_dir}",
    ]
    if extra_args:
        args.extend(extra_args)

    kwargs: dict = {
        "user_data_dir": str(root),
        "headless": headless,
        "args": args,
        "user_agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
        # ignore HTTPS errors sometimes hit on automation
        "ignore_default_args": ["--enable-automation"],
    }
    if channel:
        kwargs["channel"] = channel
    if slow_mo_ms:
        kwargs["slow_mo"] = slow_mo_ms

    print(
        f"Chrome profile: {meta.get('name') or profile_dir!r} "
        f"({profile_dir}) under {root}",
        file=sys.stderr,
    )
    print(
        "Note: quit Chrome windows using this profile if launch fails (profile lock).",
        file=sys.stderr,
    )
    return root, kwargs
