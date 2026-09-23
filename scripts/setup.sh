#!/usr/bin/env bash
# WattsUpAI — Setup Script
# Run this once on a new machine after cloning the repo.
# Usage: bash scripts/setup.sh

set -e

REPO_PATH="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
KIRO_AGENTS_DIR="$HOME/.kiro/agents"
KIRO_PROMPTS_DIR="$HOME/.kiro/agents/prompts"

echo ""
echo "⚡ WattsUpAI Setup"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Repo path: $REPO_PATH"
echo ""

# ── 1. Check dependencies ─────────────────────────────────────────────────────
echo "▸ Checking dependencies..."

if ! command -v kiro-cli &>/dev/null; then
  echo "  ✗ kiro-cli not found. Install Kiro CLI first."
  echo "    https://kiro.ai/docs/getting-started"
  exit 1
fi
echo "  ✓ kiro-cli"

if ! command -v uvx &>/dev/null; then
  echo "  ✗ uvx not found. Install uv:"
  echo "    curl -LsSf https://astral.sh/uv/install.sh | sh"
  exit 1
fi
echo "  ✓ uvx"

if ! command -v git &>/dev/null; then
  echo "  ✗ git not found."
  exit 1
fi
echo "  ✓ git"

# ── 2. Install agent config ───────────────────────────────────────────────────
echo ""
echo "▸ Installing Kiro agent..."

mkdir -p "$KIRO_AGENTS_DIR"
mkdir -p "$KIRO_PROMPTS_DIR"

# Substitute $REPO_PATH in template
sed "s|\$REPO_PATH|$REPO_PATH|g" \
  "$REPO_PATH/agent/agent.json.template" \
  > "$KIRO_AGENTS_DIR/wattsupai.json"
echo "  ✓ Agent config → $KIRO_AGENTS_DIR/wattsupai.json"

# Copy prompt
cp "$REPO_PATH/agent/prompt.md" "$KIRO_PROMPTS_DIR/wattsupai.md"
echo "  ✓ Prompt → $KIRO_PROMPTS_DIR/wattsupai.md"

# ── 3. Garmin authentication ──────────────────────────────────────────────────
echo ""
echo "▸ Garmin authentication..."

if [ -d "$HOME/.garminconnect" ] && [ -n "$(ls -A $HOME/.garminconnect 2>/dev/null)" ]; then
  echo "  ✓ Tokens found in ~/.garminconnect (skip re-auth)"
else
  echo "  ○ No tokens found. Running Garmin auth..."
  uvx --python 3.12 --from git+https://github.com/Taxuspt/garmin_mcp garmin-mcp-auth
fi

# ── 4. Test Garmin connection ─────────────────────────────────────────────────
echo ""
echo "▸ Testing Garmin connection..."
uvx --python 3.12 --from git+https://github.com/Taxuspt/garmin_mcp python -c "
import sys
sys.path.insert(0, '$(uvx --python 3.12 --from git+https://github.com/Taxuspt/garmin_mcp python -c "import garmin_mcp, os; print(os.path.dirname(garmin_mcp.__file__))" 2>/dev/null)')
" 2>/dev/null && echo "  ✓ garmin_mcp available" || echo "  ○ Will be fetched on first use"

# ── 5. Summary ────────────────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Setup complete!"
echo ""
echo "Start the coach:"
echo "  kiro-cli chat --agent wattsupai"
echo ""
echo "Rebuild activity database:"
echo "  python3 $REPO_PATH/scripts/build_db.py"
echo ""
echo "Dashboard:"
echo "  open $REPO_PATH/index.html"
echo "  or: https://ettore.trevisiol.net/wattsupai"
echo ""
echo "Re-authenticate Garmin (every ~6 months):"
echo "  uvx --python 3.12 --from git+https://github.com/Taxuspt/garmin_mcp garmin-mcp-auth"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
