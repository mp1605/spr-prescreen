#!/bin/sh
set -eu
export PATH="${PATH:-/usr/bin:/bin}:/usr/bin:/bin"
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
if [ ! -x .venv/bin/python ]; then
  echo "Python environment missing. Run ./install.sh from an extracted offline bundle." >&2
  exit 1
fi
exec .venv/bin/python -m backend.launcher "$@"
