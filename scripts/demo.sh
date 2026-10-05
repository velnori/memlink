#!/usr/bin/env bash
set -euo pipefail
# Synthetic recording only. Pass a NEW output directory and an installed Python.
python_bin="${MEMLINK_PYTHON:-python}"
"$python_bin" -m memlink.demo --out "${1:?Pass a new demo output directory}"
