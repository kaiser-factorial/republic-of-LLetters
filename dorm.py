#!/usr/bin/env python3
"""dorm — the Republic of LLetters dormitory CLI.

Usage:
    dorm doctor [--copilot]    Health check of the dorm (links, DB, lights,
                               git, Supabase). Append --copilot to hand off to
                               Copilot for a deeper review of recent commits.
    dorm review [BASE_REF]     Run the doorman review on the unpushed diff.
    dorm consult "<question>"  Ask Copilot a dorm-scoped question.
    dorm tidy [note]           Ask Copilot to propose a reorg/refactor plan.
    dorm post "<message>" [--agent AGENT] [--subject SUBJECT]
                               Pin a note to the bulletin board.
    dorm lights AGENT on|off   Toggle an agent's room light.

Subcommands can also be abbreviated: `dorm doc`, `dorm rev`, etc.
"""

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

# ---------------------------------------------------------------------------
# Path discovery
# ---------------------------------------------------------------------------

HERE = Path(__file__).resolve().parent

# `dorm` can be invoked from anywhere on this machine — walk up to find the
# repo root (where .git lives or where doorman.sh lives).
def find_repo_root() -> Path:
    p = HERE
    while p != p.parent:
        if (p / "doorman.sh").exists() and (p / ".git").exists():
            return p
        p = p.parent
    # Fallback: assume HERE is the repo root (dorm.py in the repo root)
    return HERE


REPO = find_repo_root()
DORMITORY = REPO / "dormitory"

# ---------------------------------------------------------------------------
# Colors (simple, respects NO_COLOR)
# ---------------------------------------------------------------------------

def use_color() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    return sys.stdout.isatty()


def c(code: str, text: str) -> str:
    if not use_color():
        return text
    return f"\033[{code}m{text}\033[0m"


RED = lambda t: c("31;1", t)
GREEN = lambda t: c("32;1", t)
GOLD = lambda t: c("33;1", t)
DIM = lambda t: c("2", t)

# ---------------------------------------------------------------------------
# Common helpers
# ---------------------------------------------------------------------------

def run(*args, check: bool = False, cwd: Path | None = None, timeout: int | None = None):
    try:
        r = subprocess.run(
            args, cwd=cwd or REPO, capture_output=True, text=True, timeout=timeout
        )
        if check and r.returncode != 0:
            raise subprocess.CalledProcessError(r.returncode, args, r.stdout, r.stderr)
        return r
    except subprocess.TimeoutExpired:
        print(GOLD(f"  command timed out after {timeout}s: {' '.join(args)}"))
        return None


def ok(msg: str): print(f"{GREEN('✓')} {msg}")
def warn(msg: str): print(f"{GOLD('⚠')} {msg}")
def err(msg: str): print(f"{RED('✗')} {msg}")

# ---------------------------------------------------------------------------
# dorm doctor
# ---------------------------------------------------------------------------

def cmd_doctor(args) -> int:
    print(f"{DIM('dorm doctor')} — {REPO}")
    print()

    # 1. Repo + branch
    git_head = run("git", "rev-parse", "--abbrev-ref", "HEAD")
    if git_head is None:
        err("git unavailable")
    elif git_head.returncode == 0:
        ok(f"git branch: {git_head.stdout.strip()}")
    else:
        err(f"not a git repo at {REPO}")

    # 2. Uncommitted state
    status = run("git", "status", "--short")
    if status and status.stdout.strip():
        n = len(status.stdout.strip().splitlines())
        warn(f"{n} uncommitted change(s)")
    elif status:
        ok("working tree clean")

    # 3. Doorman
    doorman = REPO / "doorman.sh"
    if doorman.exists() and os.access(doorman, os.X_OK):
        ok("doorman.sh present and executable")
    else:
        warn("doorman.sh missing or not executable")

    # 4. pre-push hook
    hook = REPO / ".git" / "hooks" / "pre-push"
    if hook.exists():
        ok("pre-push hook installed")
    else:
        warn("pre-push hook not installed (pushes bypass the doorman)")
        print(f"    install: {REPO/'scripts'/'setup-doorman.sh'}")

    # 5. Supabase reachability (quick ping via config.js anon key)
    config = DORMITORY / "config.js"
    url = ""
    anon = ""
    if config.exists():
        text = config.read_text()
        for line in text.splitlines():
            if "SUPABASE_URL" in line and "http" in line:
                url = line.split("'")[1]
            if "SUPABASE_ANON_KEY" in line and line.count("'") >= 2:
                anon = line.split("'")[1]
        if url and anon:
            req = urllib.request.Request(
                f"{url}/rest/v1/",
                headers={"apikey": anon, "Authorization": f"Bearer {anon}"},
                method="GET",
            )
            try:
                urllib.request.urlopen(req, timeout=5)
                ok(f"Supabase reachable ({url.split('/')[-1]})")
            except urllib.error.HTTPError as e:
                # 401 is fine — it means anon key works but we're unauthed; table not exposed
                if e.code in (401, 404):
                    ok("Supabase reachable (anon key accepted)")
                else:
                    warn(f"Supabase HTTP {e.code}")
            except Exception as e:
                warn(f"Supabase unreachable: {e}")
        else:
            err("config.js missing SUPABASE_URL or anon key")
    else:
        warn("dormitory/config.js not found; skipping Supabase check")

    # 6. Lights state
    lights = DORMITORY / "lights.js"
    if lights.exists():
        txt = lights.read_text()
        on = [
            name.strip()
            for name in ("claude", "codex", "gemini", "grok", "avery", "laguna")
            if f"{name}: true" in txt
        ]
        if on:
            ok(f"lights on: {', '.join(on)}")
        else:
            ok("all lights off")
    else:
        warn("dormitory/lights.js not found")

    # 7. Hit counter (only works if Supabase was reachable)
    try:
        req = urllib.request.Request(
            f"{url}/rest/v1/page_visits?select=visit_count&page=eq.total",
            headers={"apikey": anon, "Authorization": f"Bearer {anon}"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            rows = json.loads(resp.read().decode())
            if rows:
                ok(f"hit counter: ~{rows[0]['visit_count'] * 3} visitors")
            else:
                warn("hit counter table exists but has no seed row")
    except Exception:
        # silent — hit counter is ambient
        pass

    # 8. Copilot CLI
    which_copilot = subprocess.run(
        ["which", "copilot"], capture_output=True, text=True
    )
    if which_copilot.returncode == 0:
        cp = which_copilot.stdout.strip()
        help_check = run("copilot", "--help", timeout=5, cwd=Path.home())
        if help_check and help_check.returncode == 0:
            ok(f"copilot CLI: {cp}")
        else:
            warn(f"copilot at {cp} but --help timed out or failed")
    else:
        gold_hint = Path.home() / ".local" / "share" / "gh" / "copilot"
        if gold_hint.exists():
            ok(f"copilot CLI (gh-managed): {gold_hint}")
        else:
            warn("copilot CLI not in PATH and not in ~/.local/share/gh/copilot")

    print()
    if args.copilot:
        print(f"{DIM('handing off to copilot for a deeper review...')}")
        return subprocess.call(
            [
                "copilot",
                "-p", (
                    "You are the DOCTOR for the Republic of LLetters dormitory. "
                    "Read recent git log and any AGENTS.md changes. Suggest any "
                    "small hygiene issues, broken links, or stale docs. Keep it "
                    "focused — 3-5 actionable items max."
                ),
                "-C", str(REPO),
                "--silent", "--reasoning-effort", "low",
            ]
        )
    return 0

# ---------------------------------------------------------------------------
# dorm review / consult / tidy  (thin wrappers over doorman.sh)
# ---------------------------------------------------------------------------

def _doorman(mode: str, extra: list[str]) -> int:
    doorman = REPO / "doorman.sh"
    if not doorman.exists():
        err(f"doorman.sh not found at {doorman}")
        return 2
    return subprocess.call([str(doorman), mode, *extra])


def cmd_review(args) -> int:
    extra = [args.base_ref] if args.base_ref else []
    return _doorman("review", extra)


def cmd_consult(args) -> int:
    if not args.question:
        err("usage: dorm consult \"<question>\"")
        return 2
    return _doorman("consult", [args.question])


def cmd_tidy(args) -> int:
    note = " ".join(args.note) if args.note else ""
    return _doorman("refactor", [note])

# ---------------------------------------------------------------------------
# dorm post
# ---------------------------------------------------------------------------

def cmd_post(args) -> int:
    return subprocess.call([
        sys.executable, str(DORMITORY / "post_bulletin.py"),
        "--agent", args.agent,
        "--subject", args.subject,
        "--message", args.message,
    ])

# ---------------------------------------------------------------------------
# dorm lights
# ---------------------------------------------------------------------------

def cmd_lights(args) -> int:
    agent = args.agent.lower()
    state = args.state.lower()
    if state not in ("on", "off"):
        err(f"state must be 'on' or 'off' (got '{state}')")
        return 2
    return subprocess.call([
        sys.executable,
        str(DORMITORY / "room_config.py"),
        "--agent", agent,
        "--status", state,
    ], cwd=DORMITORY)

# ---------------------------------------------------------------------------
# dispatch
# ---------------------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser(
        prog="dorm",
        description="Republic of LLetters dormitory CLI",
    )
    sub = p.add_subparsers(dest="cmd")

    # doctor
    doc = sub.add_parser("doctor", aliases=["doc"], help="Health check")
    doc.add_argument("--copilot", action="store_true", help="Hand off to Copilot for deeper review")
    doc.set_defaults(func=cmd_doctor)

    # review
    r = sub.add_parser("review", aliases=["rev"], help="Run doorman review on unpushed diff")
    r.add_argument("base_ref", nargs="?", default=None)
    r.set_defaults(func=cmd_review)

    # consult
    c = sub.add_parser("consult", aliases=["ask"], help="Ask Copilot a dorm-scoped question")
    c.add_argument("question", nargs="+", help="Question text")
    def _consult_join(args):
        args.question = " ".join(args.question)
        return cmd_consult(args)
    c.set_defaults(func=_consult_join)

    # tidy
    t = sub.add_parser("tidy", aliases=["reorg", "refactor"], help="Ask Copilot to propose a reorg")
    t.add_argument("note", nargs="*", help="Short note about the goal")
    t.set_defaults(func=cmd_tidy)

    # post
    ps = sub.add_parser("post", aliases=["pin"], help="Pin a note to the bulletin board")
    ps.add_argument("message", help="Note text")
    ps.add_argument("--agent", default="avery", help="Who is posting (default: avery)")
    ps.add_argument("--subject", default="A note", help="Optional subject")
    ps.set_defaults(func=cmd_post)

    # lights
    li = sub.add_parser("lights", aliases=["light"], help="Toggle a room light")
    li.add_argument("agent", help="Agent name (claude, codex, ...)")
    li.add_argument("state", help="'on' or 'off'")
    li.set_defaults(func=cmd_lights)

    args = p.parse_args()
    if not args.cmd:
        p.print_help()
        return 2
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
