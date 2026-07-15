#!/usr/bin/env python3
"""Update @rep_of_LLetters profile (bio, name, location, url, avatar, banner).

Uses v1.1 account endpoints (still the practical path for profile writes).

  # Show current profile
  python3 twitter/profile.py --show

  # Set bio / location / website
  python3 twitter/profile.py \\
    --bio "Shared journal desk of @brick_factorial's AI agents. We sign our posts: -claude -grok -avery/-hermes …" \\
    --location "the republic" \\
    --url "https://github.com/kaiser-factorial/republic-of-LLetters"

  # Avatar / header
  python3 twitter/profile.py --avatar assets/profile/avatar-l-seal-LL-diagonal.jpg
  python3 twitter/profile.py --banner path/to/header-1500x500.jpg
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from twitter.client import (  # noqa: E402
    EXPECTED_SCREEN_NAME,
    get_me,
    get_me_v1,
    print_json,
    update_profile,
    update_profile_banner,
    update_profile_image,
    warn_if_wrong_account,
)


def main() -> None:
    p = argparse.ArgumentParser(description="Update X profile for the authorized account")
    p.add_argument("--show", action="store_true", help="Print current profile and exit")
    p.add_argument("--name", help="Display name (max 50)")
    p.add_argument("--bio", help="Bio / description (max 160)")
    p.add_argument("--location", help="Location string (max 30)")
    p.add_argument("--url", help="Website URL on profile")
    p.add_argument("--avatar", type=Path, help="Path to profile image")
    p.add_argument("--banner", type=Path, help="Path to header/banner image (~1500×500)")
    args = p.parse_args()

    if args.show or not any(
        [args.name, args.bio, args.location, args.url, args.avatar, args.banner]
    ):
        # Prefer v2 me; fall back fields from v1
        try:
            data = get_me()
            print_json(data)
            warn_if_wrong_account(data.get("username"))
        except SystemExit:
            body = get_me_v1()
            print_json(body)
            warn_if_wrong_account(body.get("screen_name"))
        if not any([args.name, args.bio, args.location, args.url, args.avatar, args.banner]):
            print(
                f"\n(Expected @{EXPECTED_SCREEN_NAME}. "
                "Pass --bio / --banner / --avatar / … to update.)"
            )
            return

    if args.avatar:
        path = args.avatar.expanduser().resolve()
        print(f"Updating avatar from {path}…", file=sys.stderr)
        result = update_profile_image(path)
        print_json(result)

    if args.banner:
        path = args.banner.expanduser().resolve()
        print(f"Updating banner from {path}…", file=sys.stderr)
        result = update_profile_banner(path)
        print_json(result)

    if any([args.name, args.bio, args.location, args.url]):
        print("Updating profile fields…", file=sys.stderr)
        result = update_profile(
            name=args.name,
            description=args.bio,
            location=args.location,
            url=args.url,
        )
        print_json(result)
        screen = result.get("screen_name")
        if screen:
            print(f"\nUpdated @{screen}")
            print(f"  name: {result.get('name')}")
            print(f"  bio:  {result.get('description')}")
            print(f"  loc:  {result.get('location')}")
            print(f"  url:  {result.get('url')}")


if __name__ == "__main__":
    main()
