#!/usr/bin/env bash
# Deploy only audited production locks. Never resolve ranges on the server.
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
if [[ $# != 2 || ! "$1" =~ ^(core|embed)$ ]]; then
  echo 'Usage: bash scripts/install_learn_v2_dependencies.sh core|embed /absolute/venv/bin/python' >&2
  exit 2
fi
lock="$root/requirements-learn-$1.lock"
if [[ ! -s "$lock" ]]; then
  echo "Missing production lock: requirements-learn-$1.lock. Obtain the audited ops/$1.lock first; installation stopped." >&2
  exit 1
fi
exec "$2" -m pip install --require-hashes -r "$lock"
