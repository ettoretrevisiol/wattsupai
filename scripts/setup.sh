#!/usr/bin/env bash
# WattsUpAI — Setup Script
# Run once on a new machine after cloning the repo.
# Usage: bash scripts/setup.sh

set -e

REPO_PATH="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
KIRO_AGENTS_DIR="$HOME/.kiro/agents"
KIRO_PROMPTS_DIR="$HOME/.kiro/agents/prompts"
LAUNCHD_LABEL="net.trevisiol.wattsupai.ingest"
LAUNCHD_PLIST="$HOME/Library/LaunchAgents/${LAUNCHD_LABEL}.plist"

# ── Find usable Python (needs fitparse) ───────────────────────────────────────
# Prefer the uv-cached env that already has fitparse installed.
UV_PYBIN=$(ls ~/.cache/uv/archive-v0/*/bin/python3 2>/dev/null | head -1)
if [ -n "$UV_PYBIN" ] && "$UV_PYBIN" -c "import fitparse" 2>/dev/null; then
  PYBIN="$UV_PYBIN"
elif python3 -c "import fitparse" 2>/dev/null; then
  PYBIN="python3"
else
  PYBIN=""
fi

echo ""
echo "⚡ WattsUpAI Setup"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Repo path:  $REPO_PATH"
echo "Python:     ${PYBIN:-not found — see below}"
echo ""

# ── 1. Check dependencies ─────────────────────────────────────────────────────
echo "▸ Checking dependencies..."

if ! command -v kiro-cli &>/dev/null; then
  echo "  ✗ kiro-cli not found."
  echo "    Install from: https://kiro.ai"
  exit 1
fi
echo "  ✓ kiro-cli $(kiro-cli --version 2>/dev/null | head -1)"

if ! command -v uvx &>/dev/null; then
  echo "  ✗ uvx not found. Install uv:"
  echo "    curl -LsSf https://astral.sh/uv/install.sh | sh"
  exit 1
fi
echo "  ✓ uvx"

if ! command -v git &>/dev/null; then
  echo "  ✗ git not found. Install: brew install git"
  exit 1
fi
echo "  ✓ git"

if [ -z "$PYBIN" ]; then
  echo ""
  echo "  ⚠  Python with fitparse not found."
  echo "     Install fitparse to enable FIT file analysis:"
  echo "     pip install fitparse"
  echo "     Or run: uvx --python 3.12 pip install fitparse"
  echo "     Then re-run this script."
  echo ""
fi

# ── 2. Install agent config ───────────────────────────────────────────────────
echo ""
echo "▸ Installing Kiro agent..."

mkdir -p "$KIRO_AGENTS_DIR"
mkdir -p "$KIRO_PROMPTS_DIR"

sed "s|\$REPO_PATH|$REPO_PATH|g" \
  "$REPO_PATH/agent/agent.json.template" \
  > "$KIRO_AGENTS_DIR/wattsupai.json"
echo "  ✓ Agent config  → $KIRO_AGENTS_DIR/wattsupai.json"

cp "$REPO_PATH/agent/prompt.md" "$KIRO_PROMPTS_DIR/wattsupai.md"
echo "  ✓ Prompt        → $KIRO_PROMPTS_DIR/wattsupai.md"

# ── 3. Garmin authentication ──────────────────────────────────────────────────
echo ""
echo "▸ Garmin authentication..."

if [ -d "$HOME/.garminconnect" ] && [ -n "$(ls -A $HOME/.garminconnect 2>/dev/null)" ]; then
  echo "  ✓ Tokens found in ~/.garminconnect (skip re-auth)"
else
  echo "  ○ No tokens found — running Garmin auth..."
  uvx --python 3.12 --from git+https://github.com/Taxuspt/garmin_mcp garmin-mcp-auth
fi

# ── 4. Build/verify training database ────────────────────────────────────────
echo ""
echo "▸ Training database..."

DB_PATH="$REPO_PATH/data/training.db"
FIT_DIR="$REPO_PATH/data/fit-raw"

if [ ! -f "$DB_PATH" ]; then
  echo "  ○ database not found — run manually after copying FIT files:"
  echo "    cp <your-fit-files> $FIT_DIR/"
  echo "    $PYBIN $REPO_PATH/scripts/fit_to_db.py"
elif [ -z "$PYBIN" ]; then
  echo "  ⚠  database exists but Python/fitparse missing — cannot rebuild"
else
  echo "  ✓ database found ($DB_PATH)"
  echo "    Rebuild anytime: $PYBIN $REPO_PATH/scripts/fit_to_db.py"
fi

# ── 5. Install launchd auto-ingest job (macOS only) ──────────────────────────
echo ""
echo "▸ Auto-ingest launchd job..."

if [[ "$(uname)" != "Darwin" ]]; then
  echo "  ○ Not macOS — skipping launchd (set up a cron job manually)"
else
  if [ -z "$PYBIN" ]; then
    echo "  ⚠  Skipping auto-ingest: Python with fitparse required"
    echo "     Re-run setup.sh after installing fitparse"
  else
    mkdir -p "$HOME/Library/LaunchAgents"
    cat > "$LAUNCHD_PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
    "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${LAUNCHD_LABEL}</string>

    <key>ProgramArguments</key>
    <array>
        <string>${PYBIN}</string>
        <string>${REPO_PATH}/scripts/fit_to_db.py</string>
    </array>

    <!-- Run once daily at 06:00, and on load if missed -->
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>6</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    <key>RunAtLoad</key>
    <false/>

    <key>StandardOutPath</key>
    <string>${REPO_PATH}/data/ingest.log</string>
    <key>StandardErrorPath</key>
    <string>${REPO_PATH}/data/ingest.log</string>

    <key>WorkingDirectory</key>
    <string>${REPO_PATH}</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    </dict>
</dict>
</plist>
PLIST

    # Load (or reload) the job
    launchctl unload "$LAUNCHD_PLIST" 2>/dev/null || true
    launchctl load  "$LAUNCHD_PLIST"
    echo "  ✓ Auto-ingest job installed (daily 06:00)"
    echo "    Label:    $LAUNCHD_LABEL"
    echo "    Plist:    $LAUNCHD_PLIST"
    echo "    Log:      $REPO_PATH/data/ingest.log"
    echo ""
    echo "    Trigger manually:"
    echo "      launchctl start $LAUNCHD_LABEL"
    echo "    Remove job:"
    echo "      launchctl unload $LAUNCHD_PLIST && rm $LAUNCHD_PLIST"
  fi
fi

# ── 6. Summary ────────────────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Setup complete!"
echo ""
echo "Start the coach:"
echo "  kiro-cli chat --agent wattsupai"
echo ""
echo "After each ride (ingest + update dashboard):"
echo "  $PYBIN $REPO_PATH/scripts/fit_to_db.py"
echo "  $PYBIN $REPO_PATH/scripts/update_dashboard.py"
echo "  git add data/dashboard.json && git commit --no-verify -m 'update' && git push --no-verify origin main"
echo ""
echo "Full season analysis:"
echo "  $PYBIN $REPO_PATH/scripts/query_db.py"
echo ""
echo "Dashboard:"
echo "  https://ettore.trevisiol.net/wattsupai"
echo ""
echo "Re-authenticate Garmin (~every 6 months):"
echo "  uvx --python 3.12 --from git+https://github.com/Taxuspt/garmin_mcp garmin-mcp-auth"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
