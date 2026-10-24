#!/usr/bin/env bash
# refresh.sh - one command to rebuild the war-room dashboard from live RBI DBIE data.
#
#   ./refresh.sh                 fetch -> analyse -> render -> verify
#   ./refresh.sh --build-only    skip the network fetch (re-use raw/*.json)
#
# The dashboard is a static file: dashboard/index.html. Nothing keeps running in the background;
# "monitoring" is a refresh you schedule (cron/systemd timer) or run by hand.
set -euo pipefail

cd "$(dirname "$0")"
LOG_DIR="logs"; mkdir -p "$LOG_DIR"
STAMP="$(date +%Y%m%d_%H%M%S)"
LOG="$LOG_DIR/refresh_$STAMP.log"

log() { printf '[%s] [refresh] %s\n' "$(date +%H:%M:%S)" "$*" | tee -a "$LOG"; }

BUILD_ONLY=0
[[ "${1:-}" == "--build-only" ]] && BUILD_ONLY=1

if [[ "$BUILD_ONLY" -eq 0 ]]; then
  log "[INFO] fetching report tables from data.rbi.org.in"
  python3 fetch_series.py >"$LOG_DIR/fetch_$STAMP.log" 2>&1 || { log "[ERROR] fetch failed - see $LOG_DIR/fetch_$STAMP.log"; exit 1; }
else
  log "[INFO] --build-only: reusing raw/*.json"
fi

log "[INFO] analysing + rendering"
python3 build_dashboard.py >"$LOG_DIR/build_$STAMP.log" 2>&1 || { log "[ERROR] build failed - see $LOG_DIR/build_$STAMP.log"; exit 1; }
tail -n 8 "$LOG_DIR/build_$STAMP.log" | sed 's/^/        /' | tee -a "$LOG"

# Publish the API and regenerate the docs from the data just built. Without these the dashboard is
# new while api/v1/ still describes the previous data - the exact "site and API disagree" failure
# daily.yml was fixed for - and committing that state fails ci.yml's reproducibility gate.
log "[INFO] publishing the static API"
python3 publish_api.py >"$LOG_DIR/publish_$STAMP.log" 2>&1 || { log "[ERROR] API publish failed - see $LOG_DIR/publish_$STAMP.log"; exit 1; }

log "[INFO] regenerating the reference docs"
python3 tools/gen_docs.py >"$LOG_DIR/docs_$STAMP.log" 2>&1 || { log "[ERROR] doc generation failed - see $LOG_DIR/docs_$STAMP.log"; exit 1; }

log "[INFO] validating the published API"
python3 tools/validate_api.py >"$LOG_DIR/api_$STAMP.log" 2>&1 || { log "[ERROR] API validation failed - see $LOG_DIR/api_$STAMP.log"; exit 1; }

log "[INFO] verifying the rendered page in headless Chromium"
python3 verify_dashboard.py >"$LOG_DIR/verify_$STAMP.log" 2>&1 || { log "[ERROR] render verification failed - see $LOG_DIR/verify_$STAMP.log"; exit 1; }
# verify_dashboard.py prints "PASS - ..." / "FAIL - N problem(s)", not "render OK". Matching the wrong
# string made grep exit 1 under `set -o pipefail`, so a SUCCESSFUL run ended the script with exit 1.
matched=$(grep -E '^(PASS|FAIL) ' "$LOG_DIR/verify_$STAMP.log" | sed 's/^/        /' | tee -a "$LOG") || true
if [ -z "$matched" ]; then
  log "[WARN] no PASS/FAIL line found in $LOG_DIR/verify_$STAMP.log"
fi

log "[INFO] done -> dashboard/index.html (screenshot: dashboard/warroom_screenshot.png)"
