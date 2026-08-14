#!/usr/bin/env bash
# Wrapper to run the anomaly detector in the project's virtualenv
# Usage: cron runs this script daily

set -euo pipefail

# adjust these paths if your layout differs
REPO_DIR="/Users/cadestocker/LocalProjects/SouthernProduce"
VENV_PY="$REPO_DIR/.venv/bin/python"
SCRIPT="$REPO_DIR/scripts/anomaly_detector.py"
LOGDIR="$REPO_DIR/logs"
LOGFILE="$LOGDIR/anomaly_detector_daily.log"

cd "$REPO_DIR"

mkdir -p "$LOGDIR"

if [ ! -x "$VENV_PY" ]; then
  # fallback to system python if venv python not found
  VENV_PY="$(command -v python3 || command -v python)"
fi

export PYTHONPATH="$REPO_DIR":${PYTHONPATH:-}

echo "[run_insights] $(date -u +"%Y-%m-%dT%H:%M:%SZ") starting" >> "$LOGFILE"
"$VENV_PY" "$SCRIPT" >> "$LOGFILE" 2>&1 || echo "[run_insights] run failed at $(date)" >> "$LOGFILE"
echo "[run_insights] $(date -u +"%Y-%m-%dT%H:%M:%SZ") finished" >> "$LOGFILE"
