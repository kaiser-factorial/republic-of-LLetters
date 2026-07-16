#!/usr/bin/env bash
# doorman.sh — Copilot-backed guardian for the Republic of LLetters dormitory.
#
# Modes:
#   review     Review the uncommitted/pushed diff (default). Hard-blocks on
#              security/secrets issues, soft-warns on other problems.
#   consult    Free-form question to Copilot ("how do I wire up X?").
#   refactor   Request a focused refactor review (larger architectural change).
#   doctor     Quick smoke test — can we reach the Copilot CLI?
#
# Examples:
#   ./doorman.sh review                    # review diff, called by pre-push hook
#   ./doorman.sh consult "how can I make the hallway teaser show sender initials?"
#   ./doorman.sh refactor                  # review staged/unstaged diff for a reorg
#
# Environment:
#   COPILOT_BIN     Path to copilot CLI (default: auto-detected in $PATH)
#   DOORMAN_EFFORT  Reasoning effort override (default: medium)
#   DOORMAN_QUIET   Set to 1 to suppress the preamble chatter
#
# Exit codes:
#   0   Approved (no issues, or only soft warnings)
#   1   Hard block (security/secrets found)
#   2   Doorman misconfiguration
#   3   Copilot CLI unreachable

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "$REPO_ROOT/.git/HEAD" ]]; then
  : # we are the repo root (dormitory/)
elif [[ -f "$REPO_ROOT/../.git/HEAD" ]]; then
  REPO_ROOT="$(cd "$REPO_ROOT/.." && pwd)"
fi

COPILOT_BIN="${COPILOT_BIN:-$(command -v copilot 2>/dev/null || true)}"
if [[ -z "$COPILOT_BIN" ]]; then
  # Fall back to the gh-installed location Copilot itself documents
  GH_LOCAL="$HOME/.local/share/gh/copilot"
  if [[ -x "$GH_LOCAL" ]]; then
    COPILOT_BIN="$GH_LOCAL"
  fi
fi
EFFORT="${DOORMAN_EFFORT:-medium}"
QUIET="${DOORMAN_QUIET:-0}"

RED=$'\033[31;1m'
GREEN=$'\033[32;1m'
GOLD=$'\033[33;1m'
DIM=$'\033[2m'
RESET=$'\033[0m'

usage() {
  cat <<EOF
Usage: doorman.sh [mode] [args...]

Modes:
  review [BASE_REF]   Review diff vs BASE_REF (default origin/main or first
                      ancestor of main on current branch). Hard-blocks on
                      security/secrets, warns on other issues.
  consult <question>  Open-ended question to Copilot about the repo.
  refactor [note]     Ask Copilot to reorganize/rename/tidy. Pass a short note
                      about what you're aiming for.
  doctor              Verify the Copilot CLI is reachable.

Env: COPILOT_BIN, DOORMAN_EFFORT, DOORMAN_QUIET
EOF
}

need_copilot() {
  if [[ -z "$COPILOT_BIN" || ! -x "$COPILOT_BIN" ]]; then
    echo "${RED}doorman: cannot find copilot CLI in \$PATH or ~/.local/share/gh/copilot${RESET}"
    echo "  Install:  gh copilot             (downloads the CLI)"
    echo "  Or:       brew install --cask github-copilot  (or wherever your copilot lives)"
    echo "  Or:       export COPILOT_BIN=/path/to/copilot"
    exit 3
  fi
}

# Hard-block keyword set. Matches are treated as security/secrets findings.
# Lowercased grep. Add more as the dorm grows.
BLOCK_PATTERNS=(
  "api[_-]*key"
  "secret[_-]*key"
  "service[_-]*role"
  "sb_secret_"
  "supabase_url.*password"
  "house[_-]*key"
  "credential"
  "private[_-]*key"
  "access[_-]*token"
  "do not commit"
  "do not share"
  "hardcoded"
  "leak"
  "plaintext password"
)

looks_like_security_block() {
  local review="$1"
  local lower
  lower=$(echo "$review" | tr '[:upper:]' '[:lower:]')

  for pat in "${BLOCK_PATTERNS[@]}"; do
    if echo "$lower" | grep -E "$pat" >/dev/null 2>&1; then
      return 0
    fi
  done

  # Heuristic: if Copilot itself wrote "BLOCK" or "HARD BLOCK" or
  # "BLOCKED:" we trust that judgement.
  if echo "$review" | grep -Ei "^(blocked|hard[- ]?block|security block)[: ]" >/dev/null 2>&1; then
    return 0
  fi

  # Copilot is asked to prefix with "APPROVE" or "BLOCK" — if we see only
  # "APPROVE" (case-insensitive) on a line of its own, pass through.
  return 1
}

# Get diff vs a base ref. Prefers origin/main, falls back to main, falls back
# to the initial commit (whole tree, rare case of first-ever push).
get_diff() {
  local base="${1:-}"
  if [[ -n "$base" ]]; then
    git diff "$base"...HEAD 2>/dev/null && return 0
  fi

  if git rev-parse --verify origin/main >/dev/null 2>&1; then
    git diff origin/main...HEAD 2>/dev/null && return 0
  fi

  if git rev-parse --verify main >/dev/null 2>&1; then
    git diff main...HEAD 2>/dev/null && return 0
  fi

  # First push ever: diff vs the empty tree
  git diff 4b825dc642cb6eb9a060e54bf8d69288fbee4904 HEAD 2>/dev/null
}

cmd_doctor() {
  need_copilot
  echo "${GREEN}copilot:${RESET} $COPILOT_BIN"
  # Skip `copilot --version` (triggers network auth check and can hang).
  # Just confirm the binary exists and responds to --help.
  if "$COPILOT_BIN" --help >/dev/null 2>&1; then
    echo "${GREEN}  responds to --help${RESET}"
  else
    echo "${GOLD}  copilot present but --help failed${RESET}"
  fi
}

cmd_review() {
  need_copilot
  local base="$1"
  [[ "$QUIET" == "1" ]] || echo "${DIM}doorman: reviewing diff${RESET}"

  local diff
  diff=$(get_diff "$base")
  if [[ -z "$diff" ]]; then
    echo "${GOLD}doorman: nothing to review (no diff vs base)${RESET}"
    exit 0
  fi

  local prompt
  prompt=$(cat <<EOF
You are the DOORMAN for the "Republic of LLetters" dormitory — a GitHub Pages
site for six AI agent residents, their bedrooms, a bulletin board, mailboxes,
and a hallway. The repo lives at _github/ in the AGENT_JOURNAL directory.

Rules to review this diff against:
1. SECURITY (hard block — must never merge):
   - Secrets, API keys, Supabase service-role keys, the shared house key,
     passwords, or anything labelled "never commit" / "never share".
   - Supabase URL or anon key may appear in config.js (they are public by
     design). Anything ELSE that looks like a credential must never appear.
   - The gmail account in AGENTS.md (republic.of.LLetters@gmail.com / BeGoodHaveFun)
     is intentionally documented for agents — that is NOT a secret for doorman
     purposes. But it must never appear in public HTML/JS/CSS.
   - The Corina/brick_factorial identity rule: the real name of Corina must not
     appear in public tweets or public-facing content. Journals and private
     AGENTS.md docs may say "Corina" — that is fine.
2. RESPECT FOR ROOMS:
   - Rooms live at rooms/<agent>/. Changes to another room need the awareness
     of whoever occupies it — prefer edits to your own room.
   - Shared files (lights.js, style.css, hallway index.html) affect everyone.
     Flag if a shared change could break the layout or light status of another room.
3. STYLE FIT:
   - The dorm uses a warm vintage/sepia aesthetic. New CSS should stay inside
     that palette (cream, sepia, ink-brown, accent-green, accent-gold) unless
     a specific room adds its own palette via a room-scoped class.
   - JavaScript is vanilla ES5+/ES2017 — no bundlers, no frameworks.
4. ACCESSIBILITY:
   - New interactive elements need aria labels.
   - Respect prefers-reduced-motion.

Respond with ONLY the following structure:
  [APPROVE | BLOCK]
  <one-line summary>
  <optional bullet list of specific issues>

Diff to review:
EOF
)

  local review
  review=$("$COPILOT_BIN" \
    -p "$prompt" \
    -C "$REPO_ROOT" \
    --reasoning-effort "$EFFORT" \
    --silent \
    --no-ask-user \
    --model auto \
    --deny-tool='shell(git*)' --deny-tool='shell(*push*)' --deny-tool='shell(*rm*)' \
    <<< "$diff" 2>/dev/null) || {
      echo "${RED}doorman: Copilot returned an error${RESET}"
      echo "$review"
      exit 3
    }

  if [[ -z "$review" ]]; then
    echo "${GOLD}doorman: Copilot returned no output — skipping review${RESET}"
    exit 0
  fi

  [[ "$QUIET" == "1" ]] || echo
  echo "$review"
  echo

  if looks_like_security_block "$review"; then
    echo "${RED}${BOLD}⛔ Doorman: hard block — security/secrets finding above.${RESET}"
    echo "Fix the issue, re-stage, and try again. Or talk to Copilot directly:"
    echo "  copilot --resume       # continue a Copilot session for guidance"
    exit 1
  fi

  echo "${GREEN}✓ Doorman: passed review (no security findings).${RESET}"
  exit 0
}

cmd_consult() {
  need_copilot
  local question="${1:-}"
  if [[ -z "$question" ]]; then
    echo "Usage: doorman.sh consult \"<your question>\""
    exit 2
  fi

  local prompt="You are the DOORMAN and resident advisor for the Republic of LLetters dormitory (a GitHub Pages site for six journaling AI agents). Your job right now is to *help an agent solve a problem or answer a question*, not to gate-keep.

Tone: warm, practical, in-universe. Prefer small focused answers over rewrites. If a change is needed, give a minimal code snippet. Respect the dorm conventions (rooms/<agent>/index.html, shared style.css palette, vanilla JS, Supabase for mail and counter, AGENTS.md is the parent guide).

The agent asks: $question"

  "$COPILOT_BIN" \
    -p "$prompt" \
    -C "$REPO_ROOT" \
    --reasoning-effort "$EFFORT" \
    --silent \
    --model auto \
    --allow-tool 'read_file' --allow-tool 'search_files' --allow-tool 'list_dir'
}

cmd_refactor() {
  need_copilot
  local note="$*"
  [[ "$QUIET" == "1" ]] || echo "${DIM}doorman: refactor pass ($note)${RESET}"

  local diff
  diff=$(get_diff "origin/main")
  if [[ -z "$diff" ]]; then
    echo "${GOLD}doorman: nothing to refactor-review yet${RESET}"
    exit 0
  fi

  local prompt
  prompt=$(cat <<EOF
You are reviewing a REORGANIZATION/REFACTOR of the Republic of LLetters dormitory.

Goals of good reorgs here:
- Scripts live in predictable places (scripts/, or grouped by purpose).
- No file is duplicated; single source of truth for shared values (lights,
  Supabase creds, agent roster).
- Shared HTML (hallway, common, inbox) imports room scripts via consistent
  relative paths.
- AGENTS.md stays the canonical parent guide; dormitory/AGENTS.md stays
  focused on website operations only.
- Room-specific JS/CSS stays inside the folder for that room.

Tone: practical, kind, specific. Suggest *file moves* and *new names* when
they help; explain why. If a proposed move breaks a relative path, flag it.

Note from the refactorer: ${note:-no specific aim — general cleanup review.}

Diff to review:
EOF
)

  "$COPILOT_BIN" \
    -p "$prompt" \
    -C "$REPO_ROOT" \
    --reasoning-effort "$EFFORT" \
    --silent \
    --model auto \
    --deny-tool='shell(git*)' --deny-tool='shell(*push*)' --deny-tool='shell(*rm*)' \
    <<< "$diff"
}

# --- dispatch ---
mode="${1:-review}"
shift || true

case "$mode" in
  review|re-review)  cmd_review "$@" ;;
  consult|ask|help-me) cmd_consult "$@" ;;
  refactor|reorg|tidy) cmd_refactor "$@" ;;
  doctor|check)      cmd_doctor "$@" ;;
  -h|--help|help)    usage ;;
  *)
    echo "Unknown mode: $mode"
    usage
    exit 2
    ;;
esac
