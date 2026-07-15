#!/usr/bin/env python3
"""Show which X user the stored tokens act as.

  python3 twitter/whoami.py
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
    warn_if_wrong_account,
)


def main() -> None:
    p = argparse.ArgumentParser(description="Show authorized X user")
    p.add_argument("--oauth2", action="store_true")
    p.add_argument("--v1", action="store_true", help="Use v1.1 verify_credentials (more fields)")
    args = p.parse_args()

    if args.v1 and not args.oauth2:
        body = get_me_v1()
        print_json(body)
        screen = body.get("screen_name")
        print(f"\nActing as @{screen} ({body.get('name')})")
    else:
        data = get_me(oauth2=args.oauth2)
        print_json(data)
        screen = data.get("username")
        print(f"\nActing as @{screen} ({data.get('name')})")

    print(f"Expected  @{EXPECTED_SCREEN_NAME}")
    warn_if_wrong_account(screen)


if __name__ == "__main__":
    main()
