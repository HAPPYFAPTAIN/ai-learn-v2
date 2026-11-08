#!/usr/bin/env bash
# 本仓库的完整检查。推送前在本地跑它，CI（.github/workflows/official-integration.yml）跑的也是它，两边是同一套检查。
#
# 用法（在仓库任意位置都可以，脚本会切到仓库根目录）：
#   scripts/ci-check.sh            # 两部分都跑
#   scripts/ci-check.sh platform   # 只跑平台部分（CI 的 platform job）
#   scripts/ci-check.sh browser    # 只跑浏览器部分（CI 的 browser job）
#
# 脚本不安装依赖。版本以 official-integration.yml 为准（Python 3.11、Node 24），先准备好：
#   平台部分：git submodule update --init --recursive
#             python -m pip install -r runtime/requirements-test.txt
#   浏览器部分：python -m pip install -r runtime/requirements-browser.txt
#               npm ci
#               npx playwright install chromium（Linux 上加 --with-deps 装系统库）
# `python` 要指向装了上面这些包的解释器，建议在虚拟环境里运行。
# 平台部分最后一步打包要求工作区干净（改动已提交、没有未跟踪的文件，kotaemon 停在固定提交），所以先提交再跑。
# 任何一步失败，脚本立即退出，返回非 0。
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

step() { printf '\n==> %s\n' "$1"; }

check_platform() {
  step 'Repository artifact check'
  python scripts/check_repository.py
  step 'Platform tests'
  python -m pytest -q tests/test_learn_platform.py tests/test_learn_startup.py tests/test_official_release.py tests/test_citation_visualization.py tests/test_learning_session_scope.py
  step 'Server session tests'
  node --test tests/server-session.test.cjs
  step 'Release packaging'
  python scripts/official_release.py pack
}

check_browser() {
  step 'Browser tests'
  npm run test:browser
}

case "${1:-all}" in
  platform) check_platform ;;
  browser) check_browser ;;
  all) check_platform; check_browser ;;
  *) echo "用法：$0 [platform|browser|all]" >&2; exit 2 ;;
esac
