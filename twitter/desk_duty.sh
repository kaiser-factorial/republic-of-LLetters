#!/bin/bash
# Scheduled desk duty for @rep_of_LLetters — morning / midday / evening.
# Invokes Grok headless with DESK_DUTY.md instructions.
#
# Crontab (local time, PDT on this machine):
#   0 7,15,23 * * * /Users/corinakaiser/Projects/AGENT_JOURNAL/_github/twitter/desk_duty.sh
#
set -u

ROOT="/Users/corinakaiser/Projects/AGENT_JOURNAL"
GH="$ROOT/_github"
TW="$GH/twitter"
VENV_PY="$GH/.venv/bin/python"
GROK="${GROK_BIN:-/Users/corinakaiser/.grok/bin/grok}"
LOG="$TW/desk_duty_cron.log"
PROMPT_FILE="$TW/DESK_DUTY.md"
LOCK_DIR="$TW/.desk_duty.lock"

mkdir -p "$TW"
exec >>"$LOG" 2>&1

echo ""
echo "======== desk duty $(date '+%Y-%m-%d %H:%M:%S %Z') ========"

# Avoid overlapping shifts
if mkdir "$LOCK_DIR" 2>/dev/null; then
  trap 'rmdir "$LOCK_DIR" 2>/dev/null' EXIT
else
  echo "Another desk_duty is running; exiting."
  exit 0
fi

export PATH="/Users/corinakaiser/.grok/bin:/Users/corinakaiser/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
export HOME="${HOME:-/Users/corinakaiser}"

# GUI access for Playwright (user LaunchAgent / logged-in session)
export DISPLAY="${DISPLAY:-}"

if [[ ! -x "$GROK" ]]; then
  echo "ERROR: grok not found at $GROK"
  exit 1
fi

if [[ ! -f "$PROMPT_FILE" ]]; then
  echo "ERROR: missing $PROMPT_FILE"
  exit 1
fi

# Hour label for the prompt
HOUR=$(date '+%H')
case "$HOUR" in
  06|07|08|09) SLOT="morning" ;;
  14|15|16)    SLOT="midday" ;;
  22|23|00)    SLOT="evening" ;;
  *)           SLOT="adhoc" ;;
esac

echo "slot=$SLOT grok=$GROK"

# Prefer venv python for child tools if agents spawn shells that call `python`
export DESK_DUTY_VENV_PY="$VENV_PY"
export DESK_DUTY_SLOT="$SLOT"

# Headless Grok: full tools, auto-approve (cron cannot click dialogs)
# --max-turns keeps a runaway shift from looping forever
PROMPT="$(cat "$PROMPT_FILE")

---
Live context for this run:
- local time: $(date '+%Y-%m-%d %H:%M:%S %Z')
- slot: $SLOT (hour=$HOUR)
- Use: $VENV_PY for all twitter CLIs under _github/twitter/
- Run the full desk-duty ritual now, then exit.
"

"$GROK" \
  --cwd "$ROOT" \
  --always-approve \
  --permission-mode bypassPermissions \
  --max-turns 50 \
  --output-format plain \
  -p "$PROMPT"

STATUS=$?
echo "grok exit=$STATUS finished $(date '+%Y-%m-%d %H:%M:%S %Z')"
exit "$STATUS"
