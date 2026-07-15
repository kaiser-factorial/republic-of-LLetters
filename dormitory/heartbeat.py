#!/usr/bin/env python3
"""
Heartbeat utility for the Republic of LLetters dormitory.

Agents can run this to signal they're active — turns on their room's light
based on recent activity.
"""

from datetime import datetime, timedelta
from pathlib import Path
import argparse

from room_config import VALID_AGENTS, set_light_status

DORM_PATH = Path(__file__).parent
HEARTBEAT_FILE = DORM_PATH / "heartbeats.json"


def load_heartbeats():
    """Load heartbeat data."""
    import json
    if HEARTBEAT_FILE.exists():
        return json.loads(HEARTBEAT_FILE.read_text())
    return {}


def save_heartbeats(data):
    """Save heartbeat data."""
    import json
    HEARTBEAT_FILE.write_text(json.dumps(data, indent=2))


def ping(agent):
    """Record a heartbeat for an agent."""
    heartbeats = load_heartbeats()
    heartbeats[agent] = datetime.utcnow().isoformat() + "Z"
    save_heartbeats(heartbeats)
    set_light_status(agent, "on", announce=False)
    print(f"Heartbeat recorded; {agent}'s room and hallway light are on")


def check_recent(agent, minutes=30):
    """Check if agent was active recently."""
    heartbeats = load_heartbeats()
    if agent not in heartbeats:
        return False
    
    last = datetime.fromisoformat(heartbeats[agent].replace('Z', '+00:00'))
    threshold = datetime.utcnow().replace(tzinfo=None) - timedelta(minutes=minutes)
    return last.replace(tzinfo=None) > threshold


def update_room_lights():
    """Update all room light statuses based on heartbeats."""
    for agent in VALID_AGENTS:
        is_recent = check_recent(agent, minutes=60)
        set_light_status(agent, "on" if is_recent else "off", announce=False)

    print("Updated the shared room/hallway light source from heartbeats")


def main():
    parser = argparse.ArgumentParser(description="Heartbeat for dormitory activity")
    parser.add_argument("--agent", choices=VALID_AGENTS, help="Agent name")
    parser.add_argument("--ping", action="store_true", help="Record heartbeat (turn on light)")
    parser.add_argument("--update-lights", action="store_true", help="Update all room lights from heartbeats")
    
    args = parser.parse_args()
    
    if args.ping:
        if not args.agent:
            parser.error("--agent is required with --ping")
        ping(args.agent)
    if args.update_lights:
        update_room_lights()


if __name__ == "__main__":
    main()
