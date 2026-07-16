#!/usr/bin/env bash
# setup-doorman.sh — install the doorman pre-push hook into the live
# .git/hooks/ directory of the Republic of LLetters repo.
#
# Safe to re-run (idempotent via symlink-check).

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOOKS_DIR="$REPO_ROOT/.git/hooks"
SOURCE_HOOK="$REPO_ROOT/scripts/pre-push-doorman"
TARGET_HOOK="$HOOKS_DIR/pre-push"

if [[ ! -f "$SOURCE_HOOK" ]]; then
  echo "Source hook missing: $SOURCE_HOOK"
  exit 2
fi
chmod +x "$SOURCE_HOOK"

mkdir -p "$HOOKS_DIR"

if [[ -L "$TARGET_HOOK" ]]; then
  ln -sf "$SOURCE_HOOK" "$TARGET_HOOK"
  echo "✓ Updated existing pre-push symlink"
elif [[ -e "$TARGET_HOOK" ]]; then
  echo "A pre-push hook already exists at $TARGET_HOOK"
  echo "  (backing up to $TARGET_HOOK.bak)"
  mv "$TARGET_HOOK" "$TARGET_HOOK.bak"
  ln -s "$SOURCE_HOOK" "$TARGET_HOOK"
  echo "✓ Installed pre-push hook (previous version at .bak)"
else
  ln -s "$SOURCE_HOOK" "$TARGET_HOOK"
  echo "✓ Installed pre-push hook"
fi

if command -v copilot >/dev/null 2>&1; then
  echo "✓ copilot CLI reachable: $(command -v copilot)"
elif [[ -x "$HOME/.local/share/gh/copilot" ]]; then
  echo "✓ copilot CLI reachable via gh: $HOME/.local/share/gh/copilot"
else
  echo "⚠ copilot CLI not found in \$PATH."
  echo "  Run:  gh copilot        # downloads the CLI"
  echo "  Or:   export COPILOT_BIN=/path/to/copilot"
fi

echo
echo "Smoke test:  $REPO_ROOT/doorman.sh doctor"
echo "Manual run:  $REPO_ROOT/doorman.sh review"
