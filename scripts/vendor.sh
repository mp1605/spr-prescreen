#!/bin/sh
set -eu
export PATH="${PATH:-/usr/bin:/bin}:/usr/bin:/bin"
cd "$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
.venv/bin/python -m pip download --only-binary=:all: --require-hashes -r requirements.txt -d vendor/
