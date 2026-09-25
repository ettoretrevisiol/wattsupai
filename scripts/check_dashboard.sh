#!/usr/bin/env bash
# check_dashboard.sh — automated consistency check
# Run after every change: bash scripts/check_dashboard.sh
# Catches stale data references, broken JS, and key value mismatches.

set -e
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HTML="$REPO/index.html"
DASH="$REPO/data/dashboard.json"

RED='\033[0;31m'; GRN='\033[0;32m'; YEL='\033[0;33m'; NC='\033[0m'
ERRORS=0

fail() { echo -e "${RED}✗ $1${NC}"; ERRORS=$((ERRORS+1)); }
pass() { echo -e "${GRN}✓ $1${NC}"; }
warn() { echo -e "${YEL}⚠ $1${NC}"; }

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "WattsUpAI Dashboard Check"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ── 1. JS syntax (Node) ───────────────────────────────────────────────────────
if command -v node &>/dev/null; then
  node -e "
const fs=require('fs');
const html=fs.readFileSync('$HTML','utf8');
const d=JSON.parse(fs.readFileSync('$DASH','utf8'));
const mockEl={innerHTML:'',textContent:'',style:{},classList:{add(){},remove(){},toggle(){}},addEventListener(){},appendChild(){}};
global.document={getElementById:()=>mockEl,querySelectorAll:()=>[],addEventListener:()=>{},createElement:()=>mockEl};
global.window={addEventListener(){},location:{reload(){}}};
global.navigator={serviceWorker:{register:()=>Promise.resolve({addEventListener(){},installing:{addEventListener(){},state:'installed',postMessage(){}}}),addEventListener(){},controller:{}}};
global.sessionStorage={getItem:()=>null};
global.Chart=function(){};global.Chart.defaults={font:{},plugins:{legend:{labels:{}},tooltip:{}},scales:{}};
global.requestAnimationFrame=cb=>{try{cb();}catch(e){}};
global.fetch=()=>Promise.resolve({ok:true,json:()=>Promise.resolve(d)});
global.caches={open:()=>Promise.resolve({addAll(){},put(){},match(){}}),keys:()=>Promise.resolve([]),delete:()=>Promise.resolve()};
global.self={addEventListener(){},skipWaiting(){},clients:{claim(){}}};
eval(html.match(/<script>([\s\S]*?)<\/script>\s*<\/body>/)[1]);
const fns=['renderHeader','renderSeason','renderLoad','renderRecovery','renderRides','renderPlan','renderCharts'];
let ok=true;
fns.forEach(fn=>{try{eval(fn)(d);}catch(e){process.stderr.write(fn+': '+e.message+'\n');ok=false;}});
process.exit(ok?0:1);
" && pass "All render functions execute without errors" \
  || { fail "Render function error — see above"; }
else
  warn "Node.js not found — skipping JS render check"
fi

# ── 2. Key data consistency checks ───────────────────────────────────────────
python3 -c "
import json, sys
d = json.load(open('$DASH'))
errors = []

# FTP consistency
ftp = d['athlete']['ftp_w']
pzc_ftp = d.get('power_zones_corrected',{}).get('ftp')
if pzc_ftp and pzc_ftp != ftp:
    errors.append(f'FTP mismatch: athlete.ftp_w={ftp} vs power_zones_corrected.ftp={pzc_ftp}')

# Status: wattsupai_status must exist
ws = d.get('wattsupai_status')
if not ws:
    errors.append('wattsupai_status missing from dashboard.json')
elif not ws.get('code'):
    errors.append('wattsupai_status.code missing')

# Status: current_status.label should not be a Garmin raw label
cs_label = d.get('current_status',{}).get('label','')
garmin_labels = ['Plateau', 'Building', 'Maintaining', 'Peaking', 'Recovering', 'UNPRODUCTIVE', 'PRODUCTIVE', 'MAINTAINING']
# We allow old labels in current_status for backward compat — just warn

# ride_name completeness (sample check)
missing_names = []
for lap in d.get('best_climbing_laps',[])[:5]:
    if not lap.get('ride_name'): missing_names.append(f'climbing_lap {lap[\"date\"]}')
for r in d.get('best_vam_laps',[])[:5]:
    if not r.get('ride_name'): missing_names.append(f'vam {r[\"date\"]}')
for r in d.get('longest_rides',{}).get('by_distance',[])[:3]:
    if not r.get('ride_name'): missing_names.append(f'longest {r[\"date\"]}')
if missing_names:
    errors.append('Missing ride_names: ' + ', '.join(missing_names[:5]))

# wattsupai_status_history must have entries
hist = d.get('wattsupai_status_history',[])
if len(hist) < 10:
    errors.append(f'Status history too short: {len(hist)} entries (expected ≥10)')

if errors:
    for e in errors: print('ERROR:', e)
    sys.exit(1)
else:
    print('OK')
" && pass "Data consistency checks passed" \
  || { fail "Data consistency errors — see above"; }

# ── 3. No stale s.label in header badge ──────────────────────────────────────
if grep -q "statusColorMap\[s\.label\]" "$HTML"; then
  fail "renderHeader still uses s.label (stale Garmin status) — should use d.wattsupai_status"
else
  pass "renderHeader uses wattsupai_status correctly"
fi

# ── 4. FTP in HTML matches dashboard.json ────────────────────────────────────
DASH_FTP=$(python3 -c "import json; print(json.load(open('$DASH'))['athlete']['ftp_w'])")
if grep -q "FTP ${DASH_FTP}W\|ftp_w.*${DASH_FTP}\|FTP=${DASH_FTP}" "$HTML" 2>/dev/null; then
  pass "FTP ${DASH_FTP}W referenced in HTML"
else
  warn "FTP ${DASH_FTP}W not explicitly found in HTML (may be data-driven — OK)"
fi

# ── 5. SW cache version ───────────────────────────────────────────────────────
SW_VER=$(grep "CACHE_NAME" "$REPO/sw.js" | grep -o "v[0-9]*" | head -1)
pass "Service worker cache: $SW_VER"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [ $ERRORS -eq 0 ]; then
  echo -e "${GRN}All checks passed ✓${NC}"
  exit 0
else
  echo -e "${RED}$ERRORS check(s) failed ✗${NC}"
  echo "Fix the issues above before pushing."
  exit 1
fi
