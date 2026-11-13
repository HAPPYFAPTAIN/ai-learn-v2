#!/bin/zsh
set -eu
cd -- "${0:A:h}"
if [[ "$(uname -s)" != Darwin ]]; then
  print "此启动器用于 macOS。"
  exit 1
fi
runtime_python=""
for candidate in "$PWD/.venv/bin/python" "$PWD/kotaemon/.venv/bin/python"; do
  if [[ -x "$candidate" ]]; then
    runtime_python="$candidate"
    break
  fi
done
if [[ -z "$runtime_python" ]]; then
  print "请先双击 setup_macos.command 安装环境。"
  read -r "reply?按回车关闭…"
  exit 1
fi
if "$runtime_python" -m learning_ext.macos_launcher "$@"; then
  exit 0
else
  result=$?
  read -r "reply?按回车关闭…"
  exit "$result"
fi
