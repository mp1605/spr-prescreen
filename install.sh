#!/bin/sh
set -eu
export PATH="${PATH:-/usr/bin:/bin}:/usr/bin:/bin"
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
if [ -e .venv ]; then
  echo "An environment already exists. Install into a fresh extracted folder; existing files were left unchanged." >&2
  exit 1
fi
runtime/python3.11/bin/python3.11 -I scripts/verify_bundle.py
runtime/python3.11/bin/python3.11 -I -m venv .venv
.venv/bin/python -I -m pip --isolated --disable-pip-version-check install --no-index --find-links vendor/ --require-hashes -r requirements.txt
.venv/bin/python scripts/check_setup.py
echo "Offline installation finished. Start with ./run.sh; create an admin with .venv/bin/python -m backend.admin init when needed."
