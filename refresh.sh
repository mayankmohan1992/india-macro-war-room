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

log "[INFO] verifying the rendered page in headless Chromium"
python3 verify_dashboard.py >"$LOG_DIR/verify_$STAMP.log" 2>&1 || { log "[ERROR] render verification failed - see $LOG_DIR/verify_$STAMP.log"; exit 1; }
grep -E 'render OK|PROBLEMS' "$LOG_DIR/verify_$STAMP.log" | sed 's/^/        /' | tee -a "$LOG"

log "[INFO] done -> dashboard/index.html (screenshot: dashboard/warroom_screenshot.png)"
