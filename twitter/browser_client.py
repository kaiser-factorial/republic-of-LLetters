"""Playwright browser posting — fallback when X API is down (401 / free tier / portal).

Modeled on poetry_consciousness/twitter/auto_tweet.py:
  browser session in auth.json → open compose → type → click post.

Optional: use a dedicated Chrome profile (e.g. ``republic`` / Profile 4) via
``chrome_profile=`` or env ``REPUBLIC_CHROME_PROFILE``.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

AUTH_FILE = Path(__file__).resolve().parent / "auth.json"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)


def auth_available(auth_file: Path | None = None) -> bool:
    path = auth_file or AUTH_FILE
    return path.is_file() and path.stat().st_size > 10


def _resolve_profile_spec(chrome_profile: str | None) -> str | None:
    if chrome_profile and chrome_profile.strip():
        return chrome_profile.strip()
    try:
        from twitter.chrome_profile import env_chrome_profile

        return env_chrome_profile()
    except Exception:  # noqa: BLE001
        return None


def _pick_page(context: Any) -> Any:
    """Prefer an existing page; close extra about:blank tabs after we have one."""
    pages = list(context.pages) if context.pages else []
    page = pages[0] if pages else context.new_page()
    page.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )
    return page


def _close_extra_blank_pages(context: Any, keep: Any) -> None:
    """Drop leftover about:blank tabs so they don't pile up in the user's Chrome."""
    try:
        for p in list(context.pages):
            if p == keep:
                continue
            try:
                url = (p.url or "").strip()
            except Exception:  # noqa: BLE001
                url = ""
            if url in ("", "about:blank", "chrome://newtab/"):
                try:
                    p.close()
                except Exception:  # noqa: BLE001
                    pass
    except Exception:  # noqa: BLE001
        pass


def launch_logged_in_browser(
    *,
    auth_file: Path | None = None,
    chrome_profile: str | None = None,
    headless: bool = False,
    channel: str | None = None,
    slow_mo_ms: int = 0,
) -> tuple[Any, Any, Any, Any, dict[str, Any]]:
    """Start Playwright + logged-in context.

    Returns ``(pwt, browser_or_none, context, page, meta)``.
    Caller must close via ``close_logged_in_browser``.

    Auth sources (first match wins for cookies):
      1. Chrome profile (``chrome_profile`` / ``REPUBLIC_CHROME_PROFILE``) via persistent context
      2. ``auth.json`` storage state on an ephemeral context

    Default browser is **bundled Chromium** (not system Chrome) so desk tools don't
    dump ``about:blank`` tabs into your everyday Chrome windows. Pass
    ``channel="chrome"`` only when you explicitly want system Chrome (profile mode).
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise SystemExit(
            "playwright not installed.\n"
            "  python3 -m pip install playwright\n"
            "  python3 -m playwright install chromium"
        )

    auth_path = (auth_file or AUTH_FILE).expanduser().resolve()
    profile_spec = _resolve_profile_spec(chrome_profile)
    # System Chrome only when using a named profile (or caller forced channel).
    if profile_spec and channel is None:
        channel = "chrome"

    meta: dict[str, Any] = {
        "persistent": False,
        "auth_file": str(auth_path),
        "chrome_profile": profile_spec,
        "channel": channel,
    }

    pwt = sync_playwright().start()
    try:
        if profile_spec:
            from twitter.chrome_profile import persistent_launch_kwargs

            _root, p_kwargs = persistent_launch_kwargs(
                profile_spec,
                headless=headless,
                channel=channel,
                slow_mo_ms=slow_mo_ms,
            )
            # launch_persistent_context takes user_data_dir as first positional
            user_data_dir = p_kwargs.pop("user_data_dir")
            try:
                context = pwt.chromium.launch_persistent_context(
                    user_data_dir, **p_kwargs
                )
            except Exception as exc:  # noqa: BLE001
                # retry without channel
                if p_kwargs.get("channel"):
                    print(
                        f"  channel={p_kwargs.get('channel')!r} failed ({exc}); "
                        "retrying without channel…",
                        file=sys.stderr,
                    )
                    p_kwargs.pop("channel", None)
                    context = pwt.chromium.launch_persistent_context(
                        user_data_dir, **p_kwargs
                    )
                else:
                    raise
            page = _pick_page(context)
            _close_extra_blank_pages(context, page)
            meta["persistent"] = True
            meta["user_data_dir"] = user_data_dir
            return pwt, None, context, page, meta

        # Ephemeral + storage_state — bundled Chromium by default (isolates from system Chrome)
        if not auth_available(auth_path):
            raise SystemExit(
                f"No browser session at {auth_path}\n"
                "Log in once as @rep_of_LLetters:\n"
                "  python3 twitter/browser_auth.py --chrome-profile republic\n"
                "  # or: python3 twitter/browser_auth.py --automation-dir --wait-login"
            )

        launch_kwargs: dict = {
            "headless": headless,
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--no-first-run",
                "--no-default-browser-check",
            ],
        }
        if channel:
            launch_kwargs["channel"] = channel
        if slow_mo_ms:
            launch_kwargs["slow_mo"] = slow_mo_ms

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
        page = _pick_page(context)
        _close_extra_blank_pages(context, page)
        return pwt, browser, context, page, meta
    except Exception:
        pwt.stop()
        raise


def close_logged_in_browser(
    pwt: Any,
    browser: Any,
    context: Any,
    meta: dict[str, Any] | None = None,
) -> None:
    """Close browser/context started by ``launch_logged_in_browser``."""
    try:
        if meta and meta.get("persistent"):
            context.close()
        elif browser is not None:
            browser.close()
        else:
            context.close()
    except Exception:  # noqa: BLE001
        pass
    try:
        pwt.stop()
    except Exception:  # noqa: BLE001
        pass


def post_tweet_browser(
    text: str,
    *,
    auth_file: Path | None = None,
    chrome_profile: str | None = None,
    headless: bool = False,
    channel: str | None = None,
    image_paths: list[Path] | None = None,
    slow_mo_ms: int = 0,
) -> dict:
    """Post via logged-in browser session. Returns a small result dict."""
    if len(text) > 280:
        raise SystemExit(f"Text is {len(text)} chars (limit 280).")

    auth_path = (auth_file or AUTH_FILE).expanduser().resolve()
    images = [p.expanduser().resolve() for p in (image_paths or [])]
    for img in images:
        if not img.is_file():
            raise SystemExit(f"Image not found: {img}")

    profile_spec = _resolve_profile_spec(chrome_profile)
    if profile_spec:
        print(
            f"Browser fallback: Chrome profile {profile_spec!r}…",
            file=sys.stderr,
        )
    else:
        print(f"Browser fallback: posting via session {auth_path.name}…", file=sys.stderr)

    pwt, browser, context, page, meta = launch_logged_in_browser(
        auth_file=auth_path,
        chrome_profile=chrome_profile,
        headless=headless,
        channel=channel,
        slow_mo_ms=slow_mo_ms,
    )
    try:
        page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=60000)
        _close_extra_blank_pages(context, page)
        # Compose box (home) or fallback to /compose/post
        selector = '[data-testid="tweetTextarea_0"]'

        def _dismiss_overlays() -> None:
            # Cookie / mask / sheet overlays often sit above the compose box.
            for _ in range(3):
                page.keyboard.press("Escape")
                page.wait_for_timeout(250)
            for dismiss in (
                '[data-testid="xMigrationBottomBar"] [role="button"]',
                '[aria-label="Close"]',
                '[data-testid="app-bar-close"]',
                'div[role="dialog"] [aria-label="Close"]',
            ):
                loc = page.locator(dismiss)
                try:
                    if loc.count() and loc.first.is_visible():
                        loc.first.click(timeout=1500)
                        page.wait_for_timeout(300)
                except Exception:  # noqa: BLE001
                    pass

        def _wait_compose(timeout_ms: int = 20000) -> None:
            _dismiss_overlays()
            page.wait_for_selector(selector, timeout=timeout_ms)

        try:
            _wait_compose(12000)
        except Exception:  # noqa: BLE001
            page.goto(
                "https://x.com/compose/post",
                wait_until="domcontentloaded",
                timeout=60000,
            )
            page.wait_for_timeout(800)
            _dismiss_overlays()
            try:
                _wait_compose(20000)
            except Exception:  # noqa: BLE001
                # Last resort: click "Post" nav / open compose from home
                page.goto(
                    "https://x.com/home",
                    wait_until="domcontentloaded",
                    timeout=60000,
                )
                page.wait_for_timeout(1000)
                _dismiss_overlays()
                for open_btn in (
                    'a[href="/compose/post"]',
                    '[data-testid="SideNav_NewTweet_Button"]',
                    '[aria-label="Post"]',
                ):
                    loc = page.locator(open_btn)
                    try:
                        if loc.count() and loc.first.is_visible():
                            loc.first.click(timeout=3000)
                            page.wait_for_timeout(800)
                            break
                    except Exception:  # noqa: BLE001
                        pass
                _dismiss_overlays()
                page.wait_for_selector(selector, timeout=25000)

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
        # Refresh storage state so cookies stay warm (works for profile + auth.json)
        try:
            context.storage_state(path=str(auth_path))
        except Exception:  # noqa: BLE001
            pass
    finally:
        close_logged_in_browser(pwt, browser, context, meta)

    result = {
        "ok": True,
        "method": "browser",
        "text": text,
        "auth_file": str(auth_path),
        "chrome_profile": profile_spec,
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


def _launch_context(
    *,
    auth_path: Path,
    headless: bool = False,
    channel: str | None = None,
    slow_mo_ms: int = 0,
    chrome_profile: str | None = None,
):
    """Launch Chromium + logged-in context. Caller must close via close_logged_in_browser."""
    pwt, browser, context, page, meta = launch_logged_in_browser(
        auth_file=auth_path,
        chrome_profile=chrome_profile,
        headless=headless,
        channel=channel,
        slow_mo_ms=slow_mo_ms,
    )
    # Stash meta on context for callers that only unpack 4 values
    context._rep_meta = meta  # type: ignore[attr-defined]
    return pwt, browser, context, page


def _dismiss_overlays(page) -> None:
    for _ in range(3):
        page.keyboard.press("Escape")
        page.wait_for_timeout(250)
    for dismiss in (
        '[data-testid="xMigrationBottomBar"] [role="button"]',
        '[aria-label="Close"]',
        '[data-testid="app-bar-close"]',
        'div[role="dialog"] [aria-label="Close"]',
    ):
        loc = page.locator(dismiss)
        try:
            if loc.count() and loc.first.is_visible():
                loc.first.click(timeout=1500)
                page.wait_for_timeout(300)
        except Exception:  # noqa: BLE001
            pass


def _save_auth(context, auth_path: Path) -> None:
    try:
        context.storage_state(path=str(auth_path))
    except Exception:  # noqa: BLE001
        pass


def follow_user_browser(
    username: str,
    *,
    unfollow: bool = False,
    auth_file: Path | None = None,
    chrome_profile: str | None = None,
    headless: bool = False,
    channel: str | None = None,
    slow_mo_ms: int = 0,
) -> dict:
    """Follow/unfollow via profile page + Follow button (Playwright session)."""
    uname = username.lstrip("@")
    auth_path = (auth_file or AUTH_FILE).expanduser().resolve()
    action = "unfollow" if unfollow else "follow"
    print(f"Browser: {action} @{uname}…", file=sys.stderr)

    pwt, browser, context, page = _launch_context(
        auth_path=auth_path,
        chrome_profile=chrome_profile,
        headless=headless,
        channel=channel,
        slow_mo_ms=slow_mo_ms,
    )
    meta = getattr(context, "_rep_meta", {"persistent": bool(chrome_profile)})
    status = "unknown"
    try:
        page.goto(f"https://x.com/{uname}", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(2000)
        _dismiss_overlays(page)

        # Prefer the profile header control (aria-label includes @handle).
        # Sidebars also show Follow on suggested users — avoid those.
        uname_l = uname.lower()

        def _profile_follow_controls():
            """Return (follow_loc, following_loc) scoped to this profile when possible."""
            following = page.locator(
                f'button[aria-label="Following @{uname}" i], '
                f'button[aria-label="Following @{uname_l}" i], '
                f'[data-testid$="-unfollow"][aria-label*="@{uname}" i], '
                f'[data-testid$="-unfollow"][aria-label*="@{uname_l}" i]'
            )
            follow = page.locator(
                f'button[aria-label="Follow @{uname}" i], '
                f'button[aria-label="Follow @{uname_l}" i], '
                f'button[aria-label="Follow back @{uname}" i], '
                f'[data-testid$="-follow"][aria-label*="@{uname}" i], '
                f'[data-testid$="-follow"][aria-label*="@{uname_l}" i]'
            )
            # Fallbacks without handle match (header only, first match)
            if following.count() == 0:
                following = page.locator(
                    '[data-testid$="-unfollow"], '
                    'button[aria-label^="Following @"]'
                )
            if follow.count() == 0:
                follow = page.locator(
                    '[data-testid$="-follow"]:not([data-testid$="-unfollow"]), '
                    'button[aria-label^="Follow @"]'
                )
            return follow, following

        follow_loc, following_loc = _profile_follow_controls()

        if unfollow:
            if following_loc.count() == 0 or not following_loc.first.is_visible():
                status = "already_not_following"
            else:
                following_loc.first.click(timeout=5000)
                page.wait_for_timeout(600)
                confirm = page.locator(
                    '[data-testid="confirmationSheetConfirm"], '
                    'button:has-text("Unfollow")'
                )
                if confirm.count() and confirm.first.is_visible():
                    confirm.first.click(timeout=3000)
                    page.wait_for_timeout(800)
                status = "unfollowed"
        else:
            if following_loc.count() and following_loc.first.is_visible():
                status = "already_following"
            else:
                clicked = False
                # Exact aria match first
                for sel in (
                    f'button[aria-label="Follow @{uname}" i]',
                    f'button[aria-label="Follow @{uname_l}" i]',
                    f'button[aria-label="Follow back @{uname}" i]',
                    f'button[aria-label="Follow back @{uname_l}" i]',
                ):
                    loc = page.locator(sel)
                    if loc.count() and loc.first.is_visible():
                        loc.first.click(timeout=5000)
                        clicked = True
                        break
                if not clicked and follow_loc.count() and follow_loc.first.is_visible():
                    # Only click if aria mentions this user (avoid sidebar)
                    el = follow_loc.first
                    aria = (el.get_attribute("aria-label") or "").lower()
                    if f"@{uname_l}" in aria or not aria:
                        el.click(timeout=5000)
                        clicked = True
                if not clicked:
                    raise RuntimeError(f"Could not find Follow button on @{uname}")
                page.wait_for_timeout(1200)
                status = "followed"

        _save_auth(context, auth_path)
    finally:
        close_logged_in_browser(pwt, browser, context, meta)

    return {
        "ok": True,
        "method": "browser",
        "action": action,
        "username": uname,
        "status": status,
        "auth_file": str(auth_path),
    }


def reply_tweet_browser(
    tweet_id: str,
    text: str,
    *,
    auth_file: Path | None = None,
    chrome_profile: str | None = None,
    headless: bool = False,
    channel: str | None = None,
    image_paths: list[Path] | None = None,
    slow_mo_ms: int = 0,
) -> dict:
    """Reply to a tweet via status page (Playwright session)."""
    if len(text) > 280:
        raise SystemExit(f"Text is {len(text)} chars (limit 280).")

    auth_path = (auth_file or AUTH_FILE).expanduser().resolve()
    images = [p.expanduser().resolve() for p in (image_paths or [])]
    for img in images:
        if not img.is_file():
            raise SystemExit(f"Image not found: {img}")

    tid = str(tweet_id)
    print(f"Browser: reply to {tid}…", file=sys.stderr)

    pwt, browser, context, page = _launch_context(
        auth_path=auth_path,
        chrome_profile=chrome_profile,
        headless=headless,
        channel=channel,
        slow_mo_ms=slow_mo_ms,
    )
    meta = getattr(context, "_rep_meta", {"persistent": bool(chrome_profile)})
    try:
        # Status URL works without knowing author; X redirects if needed
        page.goto(
            f"https://x.com/i/web/status/{tid}",
            wait_until="domcontentloaded",
            timeout=60000,
        )
        page.wait_for_timeout(1500)
        _dismiss_overlays(page)

        # Click reply on primary tweet
        reply_btn = page.locator('[data-testid="reply"]').first
        reply_btn.click(timeout=10000)
        page.wait_for_timeout(800)
        _dismiss_overlays(page)

        selector = '[data-testid="tweetTextarea_0"]'
        page.wait_for_selector(selector, timeout=20000)

        if images:
            file_input = page.locator('input[type="file"][data-testid="fileInput"]')
            if file_input.count() == 0:
                file_input = page.locator('input[type="file"]').first
            file_input.set_input_files([str(p) for p in images])
            page.wait_for_timeout(1500)

        page.click(selector)
        page.keyboard.type(text, delay=25)
        page.wait_for_timeout(400)

        posted = False
        for btn in ('[data-testid="tweetButton"]', '[data-testid="tweetButtonInline"]'):
            loc = page.locator(btn)
            if loc.count() and loc.first.is_enabled():
                loc.first.click(force=True)
                posted = True
                break
        if not posted:
            raise RuntimeError("Could not find enabled Reply/Post button.")

        page.wait_for_timeout(2500)
        _save_auth(context, auth_path)
    finally:
        close_logged_in_browser(pwt, browser, context, meta)

    result = {
        "ok": True,
        "method": "browser",
        "reply_to": tid,
        "text": text,
        "auth_file": str(auth_path),
        "note": "Replied via Playwright session (no tweet id from API).",
    }
    try:
        from twitter.tweet_log import log_tweet

        log_tweet(
            text,
            method="browser",
            images=[str(p) for p in images] if images else None,
            reply_to=tid,
        )
        result["logged_to"] = "twitter/tweet_log.md"
    except Exception as exc:  # noqa: BLE001
        print(f"(tweet log write failed: {exc})", file=sys.stderr)
    return result


def read_home_timeline_browser(
    *,
    max_posts: int = 15,
    auth_file: Path | None = None,
    chrome_profile: str | None = None,
    headless: bool = False,
    channel: str | None = None,
    slow_mo_ms: int = 0,
) -> dict:
    """Scrape a few home-timeline posts via logged-in browser (for desk duty)."""
    auth_path = (auth_file or AUTH_FILE).expanduser().resolve()
    print(f"Browser: reading home timeline (max {max_posts})…", file=sys.stderr)

    pwt, browser, context, page = _launch_context(
        auth_path=auth_path,
        chrome_profile=chrome_profile,
        headless=headless,
        channel=channel,
        slow_mo_ms=slow_mo_ms,
    )
    meta = getattr(context, "_rep_meta", {"persistent": bool(chrome_profile)})
    posts: list[dict] = []
    try:
        page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(2000)
        _dismiss_overlays(page)
        page.wait_for_selector('article[data-testid="tweet"]', timeout=25000)

        # Scroll a bit to load more
        for _ in range(3):
            articles = page.locator('article[data-testid="tweet"]')
            if articles.count() >= max_posts:
                break
            page.mouse.wheel(0, 1400)
            page.wait_for_timeout(900)

        articles = page.locator('article[data-testid="tweet"]')
        n = min(articles.count(), max_posts)
        for i in range(n):
            art = articles.nth(i)
            try:
                text = art.locator('[data-testid="tweetText"]').inner_text(timeout=2000)
            except Exception:  # noqa: BLE001
                text = ""
            try:
                # status link
                href = ""
                links = art.locator('a[href*="/status/"]')
                if links.count():
                    href = links.first.get_attribute("href") or ""
                tid = ""
                if "/status/" in href:
                    tid = href.rstrip("/").split("/status/")[-1].split("?")[0].split("/")[0]
            except Exception:  # noqa: BLE001
                href, tid = "", ""
            try:
                user = ""
                user_links = art.locator('a[role="link"][href^="/"]')
                for j in range(min(user_links.count(), 6)):
                    h = user_links.nth(j).get_attribute("href") or ""
                    if (
                        h.startswith("/")
                        and "/status/" not in h
                        and h.count("/") == 1
                        and not h.startswith("/i/")
                    ):
                        user = h.lstrip("/")
                        break
            except Exception:  # noqa: BLE001
                user = ""
            posts.append(
                {
                    "id": tid,
                    "user": user,
                    "text": (text or "").replace("\n", " ")[:280],
                    "href": href,
                }
            )
        _save_auth(context, auth_path)
    finally:
        close_logged_in_browser(pwt, browser, context, meta)

    return {"ok": True, "method": "browser", "count": len(posts), "posts": posts}
