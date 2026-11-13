#!/bin/zsh
set -eu
cd -- "${0:A:h}"
trap 'print "安装未完成。请查看上方错误，修复后可重新运行本文件。"' ZERR
if [[ "$(uname -s)" != Darwin ]]; then
  print "此安装器用于 macOS。"
  exit 1
fi
print "Learn Everything · Mac 环境安装（首次需要联网）"
export UV_CACHE_DIR="$PWD/.uv-cache"
export UV_PYTHON_INSTALL_DIR="$PWD/.python-runtimes"
uv_bin=""
if [[ -x "$PWD/.tools/bin/uv" ]]; then
  uv_bin="$PWD/.tools/bin/uv"
elif command -v uv >/dev/null 2>&1; then
  uv_bin="$(command -v uv)"
else
  if ! command -v python3 >/dev/null 2>&1; then
    print "请先安装 Python 3（python.org）或 uv（docs.astral.sh/uv），再重新运行。"
    exit 1
  fi
  python3 -m venv .tools
  .tools/bin/python -m pip install 'uv==0.13.7'
  uv_bin="$PWD/.tools/bin/uv"
fi
if [[ ! -f kotaemon/libs/ktem/ktem/__init__.py ]]; then
  git submodule update --init --recursive kotaemon
fi
if [[ ! -x .venv/bin/python ]]; then
  "$uv_bin" venv --python 3.11 .venv
fi
if ! .venv/bin/python -c 'import sys; raise SystemExit(sys.version_info[:2] != (3, 11))'; then
  print "现有 .venv 不是 Python 3.11；请先备份并移开该目录，再重新运行。本安装器不会删除已有环境。"
  exit 1
fi
"$uv_bin" pip install --python .venv/bin/python -r learning_ext/requirements-macos.txt
"$uv_bin" pip install --python .venv/bin/python --no-deps -e kotaemon/libs/kotaemon -e kotaemon/libs/ktem
"$uv_bin" pip check --python .venv/bin/python
.venv/bin/python - <<'PY'
import sysconfig
from pathlib import Path
import nltk
cache = Path(sysconfig.get_path("purelib")) / "llama_index/core/_static/nltk_cache"
cache.mkdir(parents=True, exist_ok=True)
for name in ("stopwords", "punkt", "punkt_tab"):
    if not nltk.download(name, download_dir=str(cache), quiet=True):
        raise SystemExit(f"NLTK 数据 {name} 下载失败，请检查网络后重试。")
PY
.venv/bin/python -m learning_ext.macos_launcher --check
print "安装完成。双击 run_macos.command 启动，网页中可配置模型密钥。"
