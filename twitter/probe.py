#!/usr/bin/env python3
"""Probe X API health for desk duty — status codes + rate-limit headers.

Distinguishes auth failure (401) from rate limits (429) at a glance.
Does **not** create a real post: create is a dry POST (empty body → 400 if auth ok).

  python3 twitter/probe.py
  python3 twitter/probe.py --oauth2
  python3 twitter/probe.py --extra   # also user-lookup (spends free-tier reads)
  python3 twitter/probe.py --json    # machine-readable full dump

Exit codes:
  0  — no AUTH/RATE failures and core path (me + dry write) ok
  1  — auth, rate limit, or core path failed
  2  — could not load secrets / run at all
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from twitter.client import (  # noqa: E402
    CREATE_TWEET_URL,
    EXPECTED_SCREEN_NAME,
    USERS_ME_V2,
    VERIFY_V1,
    oauth1,
    oauth2_headers,
    secrets,
)

# Headers that tell Free vs paid / remaining quota windows
RATE_HEADERS = (
    "x-rate-limit-limit",
    "x-rate-limit-remaining",
    "x-rate-limit-reset",
    "x-app-limit-24hour-limit",
    "x-app-limit-24hour-remaining",
    "x-app-limit-24hour-reset",
    "x-user-limit-24hour-limit",
    "x-user-limit-24hour-remaining",
    "x-user-limit-24hour-reset",
    "retry-after",
)


def _classify(status: int, *, dry_create: bool = False) -> str:
    if dry_create and status == 400:
        return "OK-auth"
    if 200 <= status < 300:
        return "OK"
    if status == 401:
        return "AUTH"
    if status == 403:
        return "FORBIDDEN"
    if status == 429:
        return "RATE"
    if 500 <= status < 600:
        return "SERVER"
    return f"HTTP{status}"


def _fmt_reset(ts: str | None) -> str:
    if not ts:
        return "—"
    try:
        t = int(float(ts))
        # large → unix timestamp; small → seconds-from-now
        if t > 1_000_000_000:
            delta = t - int(time.time())
            when = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(t))
            return f"{when} (in {max(0, delta)}s)"
        return f"in {t}s"
    except ValueError:
        return ts


def _extract_headers(r: requests.Response) -> dict[str, str]:
    out: dict[str, str] = {}
    for key in RATE_HEADERS:
        val = r.headers.get(key)
        if val is not None:
            out[key] = val
    return out


def _brief_body(data: Any, *, max_len: int = 200) -> str:
    if data is None:
        return "(empty body)"
    if isinstance(data, dict):
        if "title" in data or "detail" in data:
            return f"{data.get('title', '')}: {data.get('detail', '')}".strip(": ")
        if "errors" in data:
            errs = data["errors"]
            if isinstance(errs, list) and errs:
                e0 = errs[0]
                if isinstance(e0, dict):
                    return str(e0.get("message") or e0.get("detail") or e0)[:max_len]
                return str(e0)[:max_len]
        if "data" in data and isinstance(data["data"], dict):
            d = data["data"]
            if "username" in d:
                return f"@{d.get('username')} id={d.get('id')}"
            if "id" in d:
                return f"id={d.get('id')}"
        if "data" in data and isinstance(data["data"], list):
            return f"{len(data['data'])} item(s)"
        return json.dumps(data, separators=(",", ":"))[:max_len]
    if isinstance(data, str):
        return data.replace("\n", " ")[:max_len]
    return str(data)[:max_len]


def _request(
    method: str,
    url: str,
    *,
    oauth2: bool = False,
    params: dict | None = None,
    json_body: Any = None,
    timeout: int = 30,
) -> requests.Response:
    sec = secrets()
    if oauth2:
        headers = {**oauth2_headers(sec)}
        if json_body is not None:
            headers["Content-Type"] = "application/json"
        return requests.request(
            method,
            url,
            headers=headers,
            params=params,
            json=json_body,
            timeout=timeout,
        )
    headers: dict[str, str] = {}
    if json_body is not None:
        headers["Content-Type"] = "application/json"
    return requests.request(
        method,
        url,
        auth=oauth1(sec),
        headers=headers or None,
        params=params,
        json=json_body,
        timeout=timeout,
    )


def probe_one(
    name: str,
    method: str,
    url: str,
    *,
    oauth2: bool = False,
    params: dict | None = None,
    json_body: Any = None,
    ok_statuses: set[int] | None = None,
    dry_create: bool = False,
) -> dict[str, Any]:
    ok_statuses = ok_statuses or {200, 201}
    try:
        r = _request(method, url, oauth2=oauth2, params=params, json_body=json_body)
    except Exception as exc:  # noqa: BLE001
        return {
            "name": name,
            "method": method,
            "url": url,
            "status": None,
            "class": "ERROR",
            "ok": False,
            "error": str(exc),
            "headers": {},
            "body": None,
            "data": None,
        }

    try:
        data: Any = r.json()
    except Exception:  # noqa: BLE001
        data = r.text or None

    klass = _classify(r.status_code, dry_create=dry_create)
    if dry_create:
        is_ok = r.status_code == 400  # missing/invalid payload, but auth accepted
    else:
        is_ok = r.status_code in ok_statuses

    return {
        "name": name,
        "method": method,
        "url": url,
        "status": r.status_code,
        "class": klass,
        "ok": is_ok,
        "headers": _extract_headers(r),
        "body": _brief_body(data),
        "data": data if isinstance(data, dict) else None,
    }


def _print_probe(p: dict[str, Any]) -> None:
    status = p.get("status")
    klass = p.get("class")
    mark = "✓" if p.get("ok") else "✗"
    print(f"{mark} {p['name']}")
    print(f"  {p['method']} {p['url']}")
    if status is None:
        print(f"  class={klass}  error={p.get('error')}")
        print()
        return
    print(f"  status={status}  class={klass}")
    print(f"  body: {p.get('body')}")
    hdrs = p.get("headers") or {}
    if not hdrs:
        print("  rate headers: (none returned)")
    else:
        print("  rate headers:")
        for k, v in hdrs.items():
            if k.endswith("-reset") or k == "retry-after":
                print(f"    {k}: {v}  → {_fmt_reset(v)}")
            else:
                print(f"    {k}: {v}")
    if klass == "AUTH":
        print("  → 401 AUTH: not a rate limit. Check tokens, app permissions, plan/credits.")
    elif klass == "RATE":
        print("  → 429 RATE: wait for reset (see headers). Free tier often 1/24h on reads.")
    elif klass == "FORBIDDEN":
        print("  → 403 FORBIDDEN: authenticated but tier/permissions block this endpoint.")
    elif klass == "SERVER":
        print("  → 5xx SERVER: X blip — retry or use browser fallback.")
    elif klass == "OK-auth":
        print("  → dry create rejected payload (expected) — write auth path is open.")
    print()


def _skip(name: str, url: str, reason: str) -> dict[str, Any]:
    return {
        "name": name,
        "method": "GET",
        "url": url,
        "status": None,
        "class": "SKIP",
        "ok": False,
        "error": reason,
        "headers": {},
        "body": None,
        "data": None,
    }


def main() -> None:
    p = argparse.ArgumentParser(
        description="Probe X API status + rate-limit headers (no real tweet created)"
    )
    p.add_argument("--oauth2", action="store_true", help="Use OAuth 2 user token instead of OAuth 1")
    p.add_argument(
        "--extra",
        action="store_true",
        help="Also hit user-by-username (spends free-tier read budget)",
    )
    p.add_argument("--json", action="store_true", help="Print full JSON report")
    args = p.parse_args()

    try:
        secrets()
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        print(f"Could not load secrets: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc

    if not args.json:
        print(
            f"X API probe  ·  expected @{EXPECTED_SCREEN_NAME}  ·  "
            f"auth={'oauth2' if args.oauth2 else 'oauth1'}"
        )
        print(
            "Legend: OK=success  OK-auth=dry write path open  "
            "AUTH=401  RATE=429  FORBIDDEN=403  SERVER=5xx"
        )
        print("—")

    results: list[dict[str, Any]] = []

    # 1) users/me (v2)
    me = probe_one(
        "users/me",
        "GET",
        USERS_ME_V2,
        oauth2=args.oauth2,
        params={"user.fields": "id,name,username,public_metrics"},
    )
    results.append(me)
    if not args.json:
        _print_probe(me)

    # 1b) v1.1 verify — sometimes works when v2 me 401s; gives screen_name + id
    v1: dict[str, Any]
    if args.oauth2:
        v1 = _skip(
            "verify_credentials (v1.1)",
            VERIFY_V1,
            "skipped — v1.1 verify is OAuth 1 only",
        )
    else:
        v1 = probe_one(
            "verify_credentials (v1.1)",
            "GET",
            VERIFY_V1,
            oauth2=False,
            params={"skip_status": "true", "include_entities": "false"},
        )
    results.append(v1)
    if not args.json:
        _print_probe(v1)

    uid: str | None = None
    uname: str | None = None
    if me.get("ok") and isinstance(me.get("data"), dict):
        body = me["data"]
        d = body.get("data") if isinstance(body.get("data"), dict) else {}
        uid = str(d.get("id") or "") or None
        uname = d.get("username")
    if (not uid or not uname) and v1.get("ok") and isinstance(v1.get("data"), dict):
        # v1.1 body is flat: id_str, screen_name
        uid = uid or str(v1["data"].get("id_str") or v1["data"].get("id") or "") or None
        uname = uname or v1["data"].get("screen_name")
    if uname and not args.json:
        print(f"  (acting as @{uname}, id={uid})\n")

    # 2) mentions (owned read)
    if uid:
        mentions = probe_one(
            "mentions",
            "GET",
            f"https://api.x.com/2/users/{uid}/mentions",
            oauth2=args.oauth2,
            params={"max_results": "5"},
        )
    else:
        mentions = _skip(
            "mentions",
            "https://api.x.com/2/users/{id}/mentions",
            "skipped — no user id (users/me failed)",
        )
    results.append(mentions)
    if not args.json:
        _print_probe(mentions)

    # 3) own tweets (owned read)
    if uid:
        own = probe_one(
            "own_tweets",
            "GET",
            f"https://api.x.com/2/users/{uid}/tweets",
            oauth2=args.oauth2,
            params={"max_results": "5"},
        )
    else:
        own = _skip(
            "own_tweets",
            "https://api.x.com/2/users/{id}/tweets",
            "skipped — no user id",
        )
    results.append(own)
    if not args.json:
        _print_probe(own)

    # 4) dry create — empty object should 400 if write auth works (does not post)
    dry = probe_one(
        "create_tweet (dry)",
        "POST",
        CREATE_TWEET_URL,
        oauth2=args.oauth2,
        json_body={},
        dry_create=True,
    )
    results.append(dry)
    if not args.json:
        _print_probe(dry)

    if args.extra:
        lookup = probe_one(
            "user_by_username (lumpenspace)",
            "GET",
            "https://api.x.com/2/users/by/username/lumpenspace",
            oauth2=args.oauth2,
            params={"user.fields": "id,username,public_metrics"},
        )
        results.append(lookup)
        if not args.json:
            _print_probe(lookup)

    auth_fail = any(r.get("class") == "AUTH" for r in results)
    rate_fail = any(r.get("class") == "RATE" for r in results)
    identity_ok = bool(me.get("ok") or v1.get("ok"))
    write_ok = bool(dry.get("ok"))
    core_ok = identity_ok and write_ok

    if auth_fail and not write_ok:
        hint = "401 AUTH — fix tokens/permissions/plan/credits (not a wait-for-window issue)"
    elif auth_fail and write_ok:
        hint = (
            "split brain: some reads 401 but dry write open — "
            "tier/endpoint access quirk; browser for reads, API may still post"
        )
    elif rate_fail:
        hint = "429 RATE — wait for x-rate-limit-reset / 24h headers; free tier is harsh"
    elif core_ok:
        hint = "core path healthy (identity + dry write)"
    else:
        hint = "mixed failures — see probes above"

    # strip heavy data for json export of nested probes (keep headers/status)
    export_probes = []
    for r in results:
        export_probes.append(
            {
                "name": r["name"],
                "method": r["method"],
                "url": r["url"],
                "status": r.get("status"),
                "class": r.get("class"),
                "ok": r.get("ok"),
                "error": r.get("error"),
                "headers": r.get("headers"),
                "body": r.get("body"),
            }
        )

    summary = {
        "expected": EXPECTED_SCREEN_NAME,
        "acting_as": uname,
        "user_id": uid,
        "auth_mode": "oauth2" if args.oauth2 else "oauth1",
        "core_ok": core_ok,
        "any_401": auth_fail,
        "any_429": rate_fail,
        "hint": hint,
        "probes": export_probes,
    }

    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print("—")
        print("SUMMARY")
        print(f"  core_ok (me + dry write): {core_ok}")
        print(f"  any 401 AUTH:             {auth_fail}")
        print(f"  any 429 RATE:             {rate_fail}")
        print(f"  → {hint}")
        print()
        print("Desk tip: browser fallback when AUTH, or when RATE on mentions/reads.")
        print("Official: rate limits → 429; auth/plan → 401/403. Zero credits can block requests.")

    if auth_fail or rate_fail or not core_ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
