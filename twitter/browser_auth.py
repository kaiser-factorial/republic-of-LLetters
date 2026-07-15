#!/usr/bin/env python3
"""One-time browser login for the Playwright fallback.

Saves a session to twitter/auth.json (gitignored). Must be logged in as
@rep_of_LLetters — not a personal account.

Preferred: use the dedicated Chrome profile ``republic`` (Profile 4):

  python3 twitter/browser_auth.py --chrome-profile republic
  python3 twitter/browser_auth.py --list-profiles

Also works with a clean ephemeral window + manual login (old path):

  python3 twitter/browser_auth.py

Requires:
  python3 -m pip install playwright
  python3 -m playwright install chromium
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

AUTH_FILE = Path(__file__).resolve().parent / "auth.json"
EXPECTED = "rep_of_LLetters"


def main() -> None:
    p = argparse.ArgumentParser(
        description="Save X browser session for fallback tweeting (@rep_of_LLetters)"
    )
    p.add_argument(
        "--channel",
        default="chrome",
        help="Playwright browser channel (chrome|msedge|chromium). Empty = bundled chromium.",
    )
    p.add_argument(
        "--auth-file",
        type=Path,
        default=AUTH_FILE,
        help=f"Where to write storage state (default: {AUTH_FILE})",
    )
    p.add_argument(
        "--chrome-profile",
        metavar="NAME",
        help=(
            "Use a system Chrome profile by display name or dir "
            "(e.g. republic, 'Profile 4'). Recommended for the shared desk."
        ),
    )
    p.add_argument(
        "--list-profiles",
        action="store_true",
        help="List Chrome profiles on this machine and exit",
    )
    p.add_argument(
        "--user-data-dir",
        type=Path,
        default=None,
        help="Override Chrome user-data-dir (default: ~/Library/Application Support/Google/Chrome)",
    )
    p.add_argument(
        "--wait-login",
        action="store_true",
        help=(
            "Don't require pressing Enter — poll until X shows a logged-in nav "
            "(up to --timeout-sec). Handy for agent-driven setup."
        ),
    )
    p.add_argument(
        "--timeout-sec",
        type=int,
        default=600,
        help="With --wait-login, max seconds to wait (default 600)",
    )
    p.add_argument(
        "--automation-dir",
        action="store_true",
        help=(
            "Use a dedicated Playwright user-data dir at twitter/.chrome-republic/ "
            "(no profile lock vs everyday Chrome). First run: log into X there once."
        ),
    )
    args = p.parse_args()

    if args.list_profiles:
        from twitter.chrome_profile import print_profiles

        print_profiles(args.user_data_dir)
        return

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise SystemExit(
            "playwright not installed.\n"
            "  python3 -m pip install playwright\n"
            "  python3 -m playwright install chromium"
        )

    auth_path = args.auth_file.expanduser().resolve()
    channel = args.channel or None
    if channel == "":
        channel = None

    def _wait_until_logged_in(page) -> None:
        """Poll for logged-in X chrome, or fall back to Enter."""
        if not args.wait_login:
            input(f"When @{EXPECTED} is logged into X in that window, press Enter… ")
            return
        print(
            f"Waiting up to {args.timeout_sec}s for a logged-in X session "
            f"(@{EXPECTED})…",
            flush=True,
        )
        selectors = (
            '[data-testid="SideNav_AccountSwitcher_Button"]',
            '[data-testid="AppTabBar_Profile_Link"]',
            'a[href="/compose/post"]',
            '[data-testid="SideNav_NewTweet_Button"]',
        )
        deadline = __import__("time").time() + max(30, args.timeout_sec)
        while __import__("time").time() < deadline:
            for sel in selectors:
                try:
                    loc = page.locator(sel)
                    if loc.count() and loc.first.is_visible():
                        print(f"Detected logged-in UI ({sel}).", flush=True)
                        return
                except Exception:  # noqa: BLE001
                    pass
            # still on login?
            try:
                page.wait_for_timeout(2000)
            except Exception:  # noqa: BLE001
                break
        raise SystemExit(
            f"Timed out after {args.timeout_sec}s waiting for X login. "
            f"Log in as @{EXPECTED} and re-run."
        )

    print(f"Will save session to: {auth_path}")
    print(f"Log in as @{EXPECTED} (shared desk account — not a personal login).")
    print()

    with sync_playwright() as pwt:
        use_profile = bool(args.chrome_profile) or args.automation_dir
        if use_profile:
            from twitter.chrome_profile import persistent_launch_kwargs

            if args.automation_dir:
                # Dedicated dir — never fights everyday Chrome
                auto_root = Path(__file__).resolve().parent / ".chrome-republic"
                auto_root.mkdir(parents=True, exist_ok=True)
                user_data_dir = str(auto_root)
                p_kwargs = {
                    "headless": False,
                    "channel": channel or "chrome",
                    "args": ["--disable-blink-features=AutomationControlled"],
                    "user_agent": (
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/122.0.0.0 Safari/537.36"
                    ),
                    "ignore_default_args": ["--enable-automation"],
                }
                print(f"Automation Chrome user-data: {auto_root}", file=sys.stderr)
                print(
                    "(Independent of system Profile 4 — log into X here once.)",
                    file=sys.stderr,
                )
            else:
                _root, p_kwargs = persistent_launch_kwargs(
                    args.chrome_profile or "republic",
                    user_data_dir=args.user_data_dir,
                    headless=False,
                    channel=channel or "chrome",
                )
                user_data_dir = p_kwargs.pop("user_data_dir")
                if args.user_data_dir:
                    user_data_dir = str(args.user_data_dir.expanduser().resolve())

            print()
            print("Opening Chrome…")
            print("  1. Confirm this is the republic / desk window")
            print(f"  2. Log into X as @{EXPECTED} if not already")
            if args.wait_login:
                print("  3. This script will auto-save when it sees a logged-in nav")
            else:
                print("  3. Come back here and press Enter")
            print()
            try:
                context = pwt.chromium.launch_persistent_context(
                    user_data_dir, **p_kwargs
                )
            except Exception as exc:  # noqa: BLE001
                print(
                    f"\nLaunch failed: {exc}\n"
                    "Tip: fully quit Chrome (Cmd+Q) so the system profile lock is free,\n"
                    "     or use:  python3 twitter/browser_auth.py --automation-dir --wait-login\n",
                    file=sys.stderr,
                )
                raise SystemExit(1) from exc
            page = context.pages[0] if context.pages else context.new_page()
            page.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )
            page.goto("https://x.com/home", wait_until="domcontentloaded")
            _wait_until_logged_in(page)
            context.storage_state(path=str(auth_path))
            context.close()
        else:
            launch_kwargs: dict = {
                "headless": False,
                "args": ["--disable-blink-features=AutomationControlled"],
            }
            if channel:
                launch_kwargs["channel"] = channel

            try:
                browser = pwt.chromium.launch(**launch_kwargs)
            except Exception as exc:  # noqa: BLE001
                if channel:
                    print(
                        f"Launch with channel={channel!r} failed ({exc}); "
                        "trying bundled chromium…"
                    )
                    launch_kwargs.pop("channel", None)
                    browser = pwt.chromium.launch(**launch_kwargs)
                else:
                    raise
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/122.0.0.0 Safari/537.36"
                )
            )
            page = context.new_page()
            page.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )
            page.goto("https://x.com/login", wait_until="domcontentloaded")
            _wait_until_logged_in(page)
            context.storage_state(path=str(auth_path))
            browser.close()

    try:
        auth_path.chmod(0o600)
    except OSError:
        pass

    print(f"Auth saved to {auth_path}")
    print("Test:  python3 twitter/tweet.py --browser --text 'browser auth check -grok'")
    print(
        "Optional: export REPUBLIC_CHROME_PROFILE=republic  "
        "# always use that Chrome profile for browser tools"
    )


if __name__ == "__main__":
    main()
