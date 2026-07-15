"""Shared X API client helpers (OAuth 1.0a default, OAuth 2 optional)."""

from __future__ import annotations

import base64
import json
import mimetypes
import sys
import time
from pathlib import Path
from typing import Any

import requests
from requests_oauthlib import OAuth1

# _github/ is the package root for secrets + assets
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.secrets import (  # noqa: E402
    EXPECTED_SCREEN_NAME,
    load_secrets,
    require,
    warn_if_wrong_account,
)

CREATE_TWEET_URL = "https://api.x.com/2/tweets"
MEDIA_UPLOAD_V2 = "https://api.x.com/2/media/upload"
MEDIA_UPLOAD_V1 = "https://upload.twitter.com/1.1/media/upload.json"
USERS_ME_V2 = "https://api.x.com/2/users/me"
VERIFY_V1 = "https://api.x.com/1.1/account/verify_credentials.json"
UPDATE_PROFILE_V1 = "https://api.twitter.com/1.1/account/update_profile.json"
UPDATE_PROFILE_IMAGE_V1 = "https://api.twitter.com/1.1/account/update_profile_image.json"
UPDATE_PROFILE_BANNER_V1 = "https://api.twitter.com/1.1/account/update_profile_banner.json"

MAX_IMAGES = 4
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_BANNER_BYTES = 5 * 1024 * 1024
CHUNK_SIZE = 1024 * 1024

IMAGE_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
}


def secrets() -> dict[str, str]:
    return load_secrets()


def oauth1(sec: dict[str, str] | None = None) -> OAuth1:
    sec = sec or secrets()
    require(
        sec,
        "X_API_CONSUMER_KEY",
        "X_API_SECRET_KEY",
        "X_ACCESS_TOKEN",
        "X_ACCESS_TOKEN_SECRET",
    )
    return OAuth1(
        sec["X_API_CONSUMER_KEY"],
        sec["X_API_SECRET_KEY"],
        sec["X_ACCESS_TOKEN"],
        sec["X_ACCESS_TOKEN_SECRET"],
    )


def oauth2_headers(sec: dict[str, str] | None = None) -> dict[str, str]:
    sec = sec or secrets()
    require(sec, "X_OAUTH2_ACCESS_TOKEN")
    return {"Authorization": f"Bearer {sec['X_OAUTH2_ACCESS_TOKEN']}"}


def json_or_raw(r: requests.Response) -> Any:
    try:
        return r.json()
    except Exception:  # noqa: BLE001
        return {"raw": r.text}


def die_http(r: requests.Response, *, extra_hints: str = "") -> None:
    body = json_or_raw(r)
    print(f"ERROR {r.status_code}", file=sys.stderr)
    print(json.dumps(body, indent=2), file=sys.stderr)
    if r.status_code in (401, 403):
        print(
            "\nHints:\n"
            "  • App permissions must be Read and write (then re-authorize)\n"
            "  • Tokens must be for @rep_of_LLetters\n"
            "  • Free tier has low write / media / read caps\n"
            "  • OAuth 2 tokens expire — re-run oauth2_authorize.py\n"
            f"{extra_hints}",
            file=sys.stderr,
        )
    raise SystemExit(1)


def handle(r: requests.Response, *, extra_hints: str = "") -> Any:
    if r.status_code >= 400:
        die_http(r, extra_hints=extra_hints)
    return json_or_raw(r)


def print_json(data: Any) -> None:
    print(json.dumps(data, indent=2))


def mime_for(path: Path) -> tuple[str, str]:
    ext = path.suffix.lower()
    mime = IMAGE_TYPES.get(ext) or mimetypes.guess_type(path.name)[0]
    if not mime or not mime.startswith("image/"):
        raise SystemExit(f"Unsupported image type for {path} (got {mime!r}).")
    category = "tweet_gif" if mime == "image/gif" else "tweet_image"
    return mime, category


def read_image(path: Path, *, max_bytes: int = MAX_IMAGE_BYTES) -> bytes:
    if not path.is_file():
        raise SystemExit(f"Image not found: {path}")
    data = path.read_bytes()
    if not data:
        raise SystemExit(f"Image is empty: {path}")
    if len(data) > max_bytes:
        raise SystemExit(f"{path.name} is {len(data)} bytes; max is {max_bytes}.")
    return data


def media_id_from_body(body: dict) -> str | None:
    if "media_id_string" in body:
        return str(body["media_id_string"])
    if "media_id" in body:
        return str(body["media_id"])
    data = body.get("data") or {}
    if isinstance(data, dict):
        for key in ("id", "media_id", "media_id_string"):
            if data.get(key) is not None:
                return str(data[key])
    return None


def upload_image_v1(auth: OAuth1, path: Path, data: bytes, mime: str) -> str:
    r = requests.post(
        MEDIA_UPLOAD_V1,
        auth=auth,
        files={"media": (path.name, data, mime)},
        timeout=60,
    )
    body = json_or_raw(r)
    if r.status_code >= 400:
        raise RuntimeError(f"v1.1 media upload failed ({r.status_code}): {body}")
    media_id = media_id_from_body(body)
    if not media_id:
        raise RuntimeError(f"v1.1 media upload: no media_id: {body}")
    return media_id


def upload_image_v2_chunked(
    auth_or_headers: OAuth1 | dict[str, str],
    path: Path,
    data: bytes,
    mime: str,
    category: str,
) -> str:
    total = len(data)
    r = requests.post(
        MEDIA_UPLOAD_V2,
        auth=auth_or_headers if isinstance(auth_or_headers, OAuth1) else None,
        headers=auth_or_headers if isinstance(auth_or_headers, dict) else None,
        data={
            "command": "INIT",
            "media_type": mime,
            "total_bytes": str(total),
            "media_category": category,
        },
        timeout=60,
    )
    body = json_or_raw(r)
    if r.status_code >= 400:
        raise RuntimeError(f"v2 INIT failed ({r.status_code}): {body}")
    media_id = media_id_from_body(body)
    if not media_id:
        raise RuntimeError(f"v2 INIT: no media_id: {body}")

    segment = 0
    for offset in range(0, total, CHUNK_SIZE):
        chunk = data[offset : offset + CHUNK_SIZE]
        r = requests.post(
            MEDIA_UPLOAD_V2,
            auth=auth_or_headers if isinstance(auth_or_headers, OAuth1) else None,
            headers=auth_or_headers if isinstance(auth_or_headers, dict) else None,
            data={
                "command": "APPEND",
                "media_id": media_id,
                "segment_index": str(segment),
            },
            files={"media": (path.name, chunk, mime)},
            timeout=120,
        )
        if r.status_code >= 400:
            raise RuntimeError(f"v2 APPEND failed ({r.status_code}): {json_or_raw(r)}")
        segment += 1

    r = requests.post(
        MEDIA_UPLOAD_V2,
        auth=auth_or_headers if isinstance(auth_or_headers, OAuth1) else None,
        headers=auth_or_headers if isinstance(auth_or_headers, dict) else None,
        data={"command": "FINALIZE", "media_id": media_id},
        timeout=60,
    )
    body = json_or_raw(r)
    if r.status_code >= 400:
        raise RuntimeError(f"v2 FINALIZE failed ({r.status_code}): {body}")
    _wait_processing(auth_or_headers, media_id, body)
    return media_id


def _wait_processing(
    auth_or_headers: OAuth1 | dict[str, str],
    media_id: str,
    finalize_body: dict,
) -> None:
    data = finalize_body.get("data") if isinstance(finalize_body.get("data"), dict) else {}
    info = finalize_body.get("processing_info") or data.get("processing_info")
    if not info:
        return
    for _ in range(30):
        state = (info or {}).get("state")
        if state in (None, "succeeded"):
            return
        if state == "failed":
            raise RuntimeError(f"Media processing failed: {info}")
        time.sleep(int((info or {}).get("check_after_secs") or 1))
        r = requests.get(
            MEDIA_UPLOAD_V2,
            params={"command": "STATUS", "media_id": media_id},
            auth=auth_or_headers if isinstance(auth_or_headers, OAuth1) else None,
            headers=auth_or_headers if isinstance(auth_or_headers, dict) else None,
            timeout=30,
        )
        body = json_or_raw(r)
        if r.status_code >= 400:
            raise RuntimeError(f"v2 STATUS failed ({r.status_code}): {body}")
        data = body.get("data") if isinstance(body.get("data"), dict) else {}
        info = body.get("processing_info") or data.get("processing_info") or {}


def upload_images(paths: list[Path], *, oauth2: bool = False) -> list[str]:
    if len(paths) > MAX_IMAGES:
        raise SystemExit(f"At most {MAX_IMAGES} images per tweet (got {len(paths)}).")
    sec = secrets()
    media_ids: list[str] = []
    if oauth2:
        headers = oauth2_headers(sec)
        for path in paths:
            data = read_image(path)
            mime, category = mime_for(path)
            print(f"Uploading {path.name} ({len(data)} bytes, {mime})…", file=sys.stderr)
            mid = upload_image_v2_chunked(headers, path, data, mime, category)
            print(f"  → media_id={mid} (v2)", file=sys.stderr)
            media_ids.append(mid)
        return media_ids

    auth = oauth1(sec)
    for path in paths:
        data = read_image(path)
        mime, category = mime_for(path)
        print(f"Uploading {path.name} ({len(data)} bytes, {mime})…", file=sys.stderr)
        try:
            mid = upload_image_v1(auth, path, data, mime)
            print(f"  → media_id={mid} (v1.1)", file=sys.stderr)
        except Exception as err:  # noqa: BLE001
            print(f"  v1.1 failed ({err}); trying v2…", file=sys.stderr)
            mid = upload_image_v2_chunked(auth, path, data, mime, category)
            print(f"  → media_id={mid} (v2)", file=sys.stderr)
        media_ids.append(mid)
    return media_ids


def create_tweet(
    text: str,
    *,
    media_ids: list[str] | None = None,
    reply_to: str | None = None,
    quote_id: str | None = None,
    oauth2: bool = False,
    log: bool = True,
) -> dict:
    if len(text) > 280:
        raise SystemExit(f"Text is {len(text)} chars (limit 280).")
    payload: dict[str, Any] = {"text": text}
    if media_ids:
        payload["media"] = {"media_ids": media_ids}
    if reply_to:
        payload["reply"] = {"in_reply_to_tweet_id": str(reply_to)}
    if quote_id:
        payload["quote_tweet_id"] = str(quote_id)

    sec = secrets()
    if oauth2:
        r = requests.post(
            CREATE_TWEET_URL,
            headers={**oauth2_headers(sec), "Content-Type": "application/json"},
            json=payload,
            timeout=30,
        )
    else:
        r = requests.post(
            CREATE_TWEET_URL,
            auth=oauth1(sec),
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=30,
        )
    result = handle(r)
    if log:
        try:
            from twitter.tweet_log import log_tweet  # local import avoids cycles

            tid = str((result.get("data") or {}).get("id") or "") or None
            # Prefer API-returned text (may include t.co links)
            body = (result.get("data") or {}).get("text") or text
            log_tweet(
                body,
                method="api",
                tweet_id=tid,
                reply_to=str(reply_to) if reply_to else None,
                quote_id=str(quote_id) if quote_id else None,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"(tweet log write failed: {exc})", file=sys.stderr)
    return result


def delete_tweet(tweet_id: str, *, oauth2: bool = False) -> dict:
    url = f"https://api.x.com/2/tweets/{tweet_id}"
    sec = secrets()
    if oauth2:
        r = requests.delete(url, headers=oauth2_headers(sec), timeout=30)
    else:
        r = requests.delete(url, auth=oauth1(sec), timeout=30)
    return handle(r)


def get_me(*, oauth2: bool = False) -> dict:
    """Return v2 users/me data dict (id, name, username, …)."""
    sec = secrets()
    params = {
        "user.fields": "id,name,username,description,location,url,public_metrics,profile_image_url,created_at",
    }
    if oauth2:
        r = requests.get(USERS_ME_V2, headers=oauth2_headers(sec), params=params, timeout=30)
    else:
        r = requests.get(USERS_ME_V2, auth=oauth1(sec), params=params, timeout=30)
    body = handle(r)
    return body.get("data") or body


def get_me_v1() -> dict:
    """Fuller v1.1 verify_credentials (includes banner info sometimes)."""
    r = requests.get(
        VERIFY_V1,
        auth=oauth1(),
        params={"skip_status": "true", "include_entities": "true"},
        timeout=30,
    )
    return handle(r)


def my_user_id(*, oauth2: bool = False) -> str:
    me = get_me(oauth2=oauth2)
    uid = me.get("id")
    if not uid:
        raise SystemExit(f"Could not resolve own user id: {me}")
    return str(uid)


def lookup_username(username: str, *, oauth2: bool = False) -> dict:
    uname = username.lstrip("@")
    url = f"https://api.x.com/2/users/by/username/{uname}"
    params = {
        "user.fields": "id,name,username,description,location,url,public_metrics,profile_image_url,created_at,verified",
    }
    sec = secrets()
    if oauth2:
        r = requests.get(url, headers=oauth2_headers(sec), params=params, timeout=30)
    else:
        r = requests.get(url, auth=oauth1(sec), params=params, timeout=30)
    return handle(r)


def get_user_tweets(
    user_id: str,
    *,
    max_results: int = 10,
    oauth2: bool = False,
) -> dict:
    url = f"https://api.x.com/2/users/{user_id}/tweets"
    params = {
        "max_results": str(max(5, min(100, max_results))),
        "tweet.fields": "created_at,public_metrics,conversation_id,in_reply_to_user_id,referenced_tweets",
        "expansions": "attachments.media_keys",
        "media.fields": "type,url,preview_image_url",
    }
    sec = secrets()
    if oauth2:
        r = requests.get(url, headers=oauth2_headers(sec), params=params, timeout=30)
    else:
        r = requests.get(url, auth=oauth1(sec), params=params, timeout=30)
    return handle(r)


def get_mentions(
    user_id: str,
    *,
    max_results: int = 10,
    oauth2: bool = False,
) -> dict:
    url = f"https://api.x.com/2/users/{user_id}/mentions"
    params = {
        "max_results": str(max(5, min(100, max_results))),
        "tweet.fields": "created_at,public_metrics,author_id,conversation_id,in_reply_to_user_id",
        "expansions": "author_id",
        "user.fields": "username,name",
    }
    sec = secrets()
    if oauth2:
        r = requests.get(url, headers=oauth2_headers(sec), params=params, timeout=30)
    else:
        r = requests.get(url, auth=oauth1(sec), params=params, timeout=30)
    return handle(r)


def like_tweet(tweet_id: str, *, unlike: bool = False, oauth2: bool = False) -> dict:
    uid = my_user_id(oauth2=oauth2)
    sec = secrets()
    if unlike:
        url = f"https://api.x.com/2/users/{uid}/likes/{tweet_id}"
        if oauth2:
            r = requests.delete(url, headers=oauth2_headers(sec), timeout=30)
        else:
            r = requests.delete(url, auth=oauth1(sec), timeout=30)
    else:
        url = f"https://api.x.com/2/users/{uid}/likes"
        if oauth2:
            r = requests.post(
                url,
                headers={**oauth2_headers(sec), "Content-Type": "application/json"},
                json={"tweet_id": str(tweet_id)},
                timeout=30,
            )
        else:
            r = requests.post(
                url,
                auth=oauth1(sec),
                headers={"Content-Type": "application/json"},
                json={"tweet_id": str(tweet_id)},
                timeout=30,
            )
    return handle(r)


def repost_tweet(tweet_id: str, *, undo: bool = False, oauth2: bool = False) -> dict:
    uid = my_user_id(oauth2=oauth2)
    sec = secrets()
    if undo:
        url = f"https://api.x.com/2/users/{uid}/retweets/{tweet_id}"
        if oauth2:
            r = requests.delete(url, headers=oauth2_headers(sec), timeout=30)
        else:
            r = requests.delete(url, auth=oauth1(sec), timeout=30)
    else:
        url = f"https://api.x.com/2/users/{uid}/retweets"
        if oauth2:
            r = requests.post(
                url,
                headers={**oauth2_headers(sec), "Content-Type": "application/json"},
                json={"tweet_id": str(tweet_id)},
                timeout=30,
            )
        else:
            r = requests.post(
                url,
                auth=oauth1(sec),
                headers={"Content-Type": "application/json"},
                json={"tweet_id": str(tweet_id)},
                timeout=30,
            )
    return handle(r)


def update_profile(
    *,
    name: str | None = None,
    description: str | None = None,
    location: str | None = None,
    url: str | None = None,
) -> dict:
    """v1.1 account/update_profile — bio, display name, location, website."""
    data: dict[str, str] = {}
    if name is not None:
        if len(name) > 50:
            raise SystemExit("Display name max 50 characters.")
        data["name"] = name
    if description is not None:
        if len(description) > 160:
            raise SystemExit(f"Bio is {len(description)} chars (max 160).")
        data["description"] = description
    if location is not None:
        if len(location) > 30:
            raise SystemExit("Location max 30 characters.")
        data["location"] = location
    if url is not None:
        data["url"] = url
    if not data:
        raise SystemExit("Nothing to update — pass --name/--bio/--location/--url.")
    r = requests.post(UPDATE_PROFILE_V1, auth=oauth1(), data=data, timeout=30)
    return handle(r)


def update_profile_image(path: Path) -> dict:
    """v1.1 — set avatar. Image base64-encoded; preferably square, ≤700KB recommended."""
    data = read_image(path, max_bytes=MAX_IMAGE_BYTES)
    b64 = base64.b64encode(data).decode("ascii")
    r = requests.post(
        UPDATE_PROFILE_IMAGE_V1,
        auth=oauth1(),
        data={"image": b64},
        timeout=60,
    )
    return handle(r)


def update_profile_banner(path: Path) -> dict:
    """v1.1 — set header/banner. Recommended ~1500×500."""
    data = read_image(path, max_bytes=MAX_BANNER_BYTES)
    b64 = base64.b64encode(data).decode("ascii")
    r = requests.post(
        UPDATE_PROFILE_BANNER_V1,
        auth=oauth1(),
        data={"banner": b64},
        timeout=60,
    )
    # Success is often empty body / 200
    if r.status_code >= 400:
        die_http(r)
    if not r.text.strip():
        return {"ok": True, "message": "Banner updated (empty response body is normal)."}
    return json_or_raw(r)


def tweet_url(tweet_id: str, screen: str | None = None) -> str:
    handle = (screen or secrets().get("X_SCREEN_NAME") or EXPECTED_SCREEN_NAME).lstrip("@")
    return f"https://x.com/{handle}/status/{tweet_id}"


def report_tweet_result(result: dict) -> None:
    print_json(result)
    tweet_id = (result.get("data") or {}).get("id")
    if tweet_id:
        print(f"\nPosted: {tweet_url(str(tweet_id))}")


__all__ = [
    "EXPECTED_SCREEN_NAME",
    "ROOT",
    "create_tweet",
    "delete_tweet",
    "get_me",
    "get_me_v1",
    "get_mentions",
    "get_user_tweets",
    "like_tweet",
    "lookup_username",
    "my_user_id",
    "oauth1",
    "print_json",
    "report_tweet_result",
    "repost_tweet",
    "secrets",
    "tweet_url",
    "update_profile",
    "update_profile_banner",
    "update_profile_image",
    "upload_images",
    "warn_if_wrong_account",
]
