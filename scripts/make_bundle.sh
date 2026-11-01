#!/bin/sh
set -eu
export PATH="${PATH:-/usr/bin:/bin}:/usr/bin:/bin"
cd "$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
exec .venv/bin/python scripts/make_bundle.py "$@"
