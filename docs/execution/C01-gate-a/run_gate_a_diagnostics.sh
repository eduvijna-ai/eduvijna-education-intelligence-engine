#!/usr/bin/env bash
# C01 Gate A — run guarded Python harness (disposable PG/SQLite only).
set -uo pipefail
exec python3 "$(cd "$(dirname "$0")" && pwd)/c01_gate_a_harness.py" "$@"