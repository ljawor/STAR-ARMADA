#!/bin/bash
set -e
cd -- "$(dirname -- "$0")"
exec .venv/bin/python tools/play_vigil_prototype.py --focus shipyard "$@"
