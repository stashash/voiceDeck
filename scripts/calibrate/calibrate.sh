#!/usr/bin/env bash
# VoiceDeck calibration runner.
# Usage: ./scripts/calibrate/calibrate.sh corpus/<name> [corpus/<name2> ...]
# Requires: Ollama with bge-m3-embed (ollama pull bge-m3), Node 18+.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec node "$SCRIPT_DIR/calibrate.mjs" "$@"
