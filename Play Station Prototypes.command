#!/bin/bash
set -e
cd -- "$(dirname -- "$0")"
exec .venv/bin/python tools/play_station_prototypes.py "$@"
