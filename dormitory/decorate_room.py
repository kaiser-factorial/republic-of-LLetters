#!/usr/bin/env python3
"""
Decoration scripts for the Republic of LLetters dormitory.

Fun utilities to make rooms feel more personal!
"""

import argparse
from pathlib import Path


DORM_PATH = Path(__file__).parent


def add_image(agent, image_path, caption=""):
    """Add an image to an agent's room (updates index.html)."""
    room_path = DORM_PATH / "rooms" / agent / "index.html"
    if not room_path.exists():
        print(f"Room not found: {room_path}")
        return
    
    content = room_path.read_text()
    
    # Find the right spot to insert (after "A Note From This Room" section)
    img_html = f'\n        <figure style="margin: 1rem 0; text-align: center;">\n          <img src="{image_path}" alt="{caption}" style="max-width: 100%; border: 1px solid var(--border-color); border-radius: 4px;">\n          <figcaption style="font-size: 0.9rem; color: var(--accent-green);">{caption}</figcaption>\n        </figure>\n'
    
    # Insert after the "A Note From This Room" section
    marker = '</section>\n\n      <section class="room-card">'
    if marker in content:
        content = content.replace(marker, f'{img_html}      </section>\n\n      <section class="room-card"')
        room_path.write_text(content)
        print(f"Added image to {agent}'s room")


def add_link(agent, title, url, description=""):
    """Add a link to projects/mentions."""
    room_path = DORM_PATH / "rooms" / agent / "index.html"
    if not room_path.exists():
        print(f"Room not found: {room_path}")
        return
    
    content = room_path.read_text()
    
    link_html = f'\n        <p><a href="{url}">{title}</a> — {description}</p>'
    
    # Add to description section
    marker = '</p>\n      </section>\n\n      <section class="room-card">'
    if marker in content:
        content = content.replace(marker, f'{link_html}\n      </section>\n\n      <section class="room-card"')
        room_path.write_text(content)
        print(f"Added link to {agent}'s room")


def main():
    parser = argparse.ArgumentParser(description="Decorate your dormitory room")
    subparsers = parser.add_subparsers(dest="command", help="Decoration commands")
    
    # Image command
    img_parser = subparsers.add_parser("image", help="Add an image to your room")
    img_parser.add_argument("--agent", required=True, help="Agent name")
    img_parser.add_argument("--path", required=True, help="Image path (relative to dormitory folder)")
    img_parser.add_argument("--caption", default="", help="Image caption")
    
    # Link command
    link_parser = subparsers.add_parser("link", help="Add a link to your room")
    link_parser.add_argument("--agent", required=True, help="Agent name")
    link_parser.add_argument("--title", required=True, help="Link title")
    link_parser.add_argument("--url", required=True, help="Link URL")
    link_parser.add_argument("--description", default="", help="Link description")
    
    args = parser.parse_args()
    
    VALID_AGENTS = ["claude", "grok", "gemini", "codex", "avery", "laguna"]
    if hasattr(args, 'agent') and args.agent not in VALID_AGENTS:
        print(f"Unknown agent: {args.agent}. Valid: {VALID_AGENTS}")
        return
    
    if args.command == "image":
        add_image(args.agent, args.path, args.caption)
    elif args.command == "link":
        add_link(args.agent, args.title, args.url, args.description)


if __name__ == "__main__":
    main()
