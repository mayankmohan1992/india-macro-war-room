#!/usr/bin/env bash
# refresh.sh (in scripts/) - thin wrapper around the pipeline at the repository root.
#
# This file used to be a byte-identical copy of ../refresh.sh, which starts with
# `cd "$(dirname "$0")"`. Run from here that lands in scripts/, where fetch_series.py and
# build_dashboard.py do not exist - so this copy could never work. Keeping one implementation
# (at the root, where the cd is correct) removes the class of bug entirely.
set -euo pipefail

exec "$(cd "$(dirname "$0")/.." && pwd)/refresh.sh" "$@"
