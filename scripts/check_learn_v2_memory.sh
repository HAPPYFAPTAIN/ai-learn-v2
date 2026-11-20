#!/usr/bin/env bash
set -euo pipefail
failed=0
for name in db api worker@llm worker@chat worker@io embed; do
  unit="ai-learn-v2-${name}.service"
  configured=$(systemctl --user show "$unit" -p MemoryMax --value)
  group=$(systemctl --user show "$unit" -p ControlGroup --value)
  if [[ -z "$group" || ! -r "/sys/fs/cgroup${group}/memory.max" ]]; then
    echo "$unit: memory controller not delegated or service not running" >&2
    failed=1
    continue
  fi
  actual=$(cat "/sys/fs/cgroup${group}/memory.max")
  echo "$unit: MemoryMax=$configured memory.max=$actual"
  if [[ "$actual" == max || "$actual" != "$configured" ]]; then failed=1; fi
done
exit "$failed"
