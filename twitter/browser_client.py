"""Playwright browser posting — fallback when X API is down (401 / free tier / portal).

Modeled on poetry_consciousness/twitter/auto_tweet.py:
  browser session in auth.json → open compose → type → click post.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

AUTH_FILE = Path(__file__).resolve().parent / "auth.json"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)


def auth_available(auth_file: Path | None = None) -> bool:
    path = auth_file or AUTH_FILE
    return path.is_file() and path.stat().st_size > 10


def post_tweet_browser(
    text: str,
    *,
    auth_file: Path | None = None,
    headless: bool = False,
    channel: str | None = "chrome",
    image_paths: list[Path] | None = None,
    slow_mo_ms: int = 0,
) -> dict:
    """Post via logged-in browser session. Returns a small result dict."""
    if len(text) > 280:
        raise SystemExit(f"Text is {len(text)} chars (limit 280).")

    auth_path = (auth_file or AUTH_FILE).expanduser().resolve()
    if not auth_available(auth_path):
        raise SystemExit(
            f"No browser session at {auth_path}\n"
            "Run once (logged into @rep_of_LLetters):\n"
            "  python3 twitter/browser_auth.py"
        )

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise SystemExit(
            "playwright not installed.\n"
            "  python3 -m pip install playwright\n"
            "  python3 -m playwright install chromium"
        )

    images = [p.expanduser().resolve() for p in (image_paths or [])]
    for img in images:
        if not img.is_file():
            raise SystemExit(f"Image not found: {img}")

    launch_kwargs: dict = {
        "headless": headless,
        "args": ["--disable-blink-features=AutomationControlled"],
    }
    if channel:
        launch_kwargs["channel"] = channel
    if slow_mo_ms:
        launch_kwargs["slow_mo"] = slow_mo_ms

    print(f"Browser fallback: posting via session {auth_path.name}…", file=sys.stderr)

    with sync_playwright() as pwt:
        try:
            browser = pwt.chromium.launch(**launch_kwargs)
        except Exception as exc:  # noqa: BLE001
            if channel:
                print(
                    f"  channel={channel!r} failed ({exc}); trying bundled chromium…",
                    file=sys.stderr,
                )
                launch_kwargs.pop("channel", None)
                browser = pwt.chromium.launch(**launch_kwargs)
            else:
                raise

        context = browser.new_context(
            storage_state=str(auth_path),
            user_agent=USER_AGENT,
        )
        page = context.new_page()
        page.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

        try:
            page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=60000)
            # Compose box (home) or fallback to /compose/post
            selector = '[data-testid="tweetTextarea_0"]'
            try:
                page.wait_for_selector(selector, timeout=20000)
            except Exception:  # noqa: BLE001
                page.goto(
                    "https://x.com/compose/post",
                    wait_until="domcontentloaded",
                    timeout=60000,
                )
                page.wait_for_selector(selector, timeout=20000)

            if images:
                # Prefer the file input under the media button toolbar
                file_input = page.locator('input[type="file"][data-testid="fileInput"]')
                if file_input.count() == 0:
                    file_input = page.locator('input[type="file"]').first
                file_input.set_input_files([str(p) for p in images])
                # Wait for preview thumbs
                page.wait_for_timeout(1500)

            page.click(selector)
            # type is slower but more reliable than fill for Draft.js
            page.keyboard.type(text, delay=25)
            page.wait_for_timeout(400)

            # Home uses tweetButtonInline; compose modal uses tweetButton
            posted = False
            for btn in ('[data-testid="tweetButtonInline"]', '[data-testid="tweetButton"]'):
                loc = page.locator(btn)
                if loc.count() and loc.first.is_enabled():
                    loc.first.click(force=True)
                    posted = True
                    break
            if not posted:
                raise RuntimeError("Could not find enabled Post button.")

            page.wait_for_timeout(2500)
            # Refresh storage state so cookies stay warm
            try:
                context.storage_state(path=str(auth_path))
            except Exception:  # noqa: BLE001
                pass
        finally:
            browser.close()

    result = {
        "ok": True,
        "method": "browser",
        "text": text,
        "auth_file": str(auth_path),
        "note": "Posted via Playwright session (no tweet id from API).",
    }
    try:
        from twitter.tweet_log import log_tweet

        log_tweet(
            text,
            method="browser",
            images=[str(p) for p in images] if images else None,
        )
        result["logged_to"] = "twitter/tweet_log.md"
    except Exception as exc:  # noqa: BLE001
        print(f"(tweet log write failed: {exc})", file=sys.stderr)
    return result
