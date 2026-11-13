from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import sysconfig
import time
import urllib.error
import urllib.request
import webbrowser


ROOT = Path(__file__).resolve().parents[1]
HOST = "127.0.0.1"


def runtime_python(root=ROOT):
    for folder in (root / ".venv", root / "kotaemon" / ".venv"):
        candidate = folder / "bin" / "python"
        if candidate.is_file():
            return candidate
    raise RuntimeError("未找到 Mac 运行环境，请先双击 setup_macos.command。")


def backend_environment(port, root=ROOT):
    env = os.environ.copy()
    env.update(GRADIO_SERVER_NAME=HOST, GRADIO_SERVER_PORT=str(port), PYTHONUNBUFFERED="1")
    for name, value in {
        "GRADIO_ANALYTICS_ENABLED": "False", "KH_FEATURE_USER_MANAGEMENT": "False",
        "KH_ENABLE_FIRST_SETUP": "False", "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
        "MPLCONFIGDIR": str(root / ".tmp" / "matplotlib"),
    }.items():
        env.setdefault(name, value)
    env["PYTHONPATH"] = str(root) + os.pathsep + env.get("PYTHONPATH", "")
    nltk = Path(sysconfig.get_path("purelib")) / "llama_index/core/_static/nltk_cache"
    if nltk.is_dir():
        env.setdefault("NLTK_DATA", str(nltk))
    return env


def check_runtime(root=ROOT):
    if sys.version_info[:2] != (3, 11):
        raise RuntimeError("Mac 版本需要 Python 3.11，请重新运行 setup_macos.command。")
    if not (root / "kotaemon/libs/ktem/ktem").is_dir():
        raise RuntimeError("Kotaemon 子模块尚未初始化，请运行 setup_macos.command。")
    for name in ("kotaemon", "ktem", "gradio", "fsrs", "cryptography", "voyageai", "aiolimiter"):
        try:
            version = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            raise RuntimeError(f"缺少依赖 {name}，请运行 setup_macos.command。") from None
        if name == "gradio" and version != "4.44.1":
            raise RuntimeError("Gradio 版本不匹配，请运行 setup_macos.command 恢复兼容版本。")
        print(f"  {name}: {version}", flush=True)


def free_port(first):
    for port in range(first, min(first + 20, 65536)):
        with socket.socket() as sock:
            try:
                sock.bind((HOST, port))
            except OSError:
                continue
            return port
    raise RuntimeError("没有可用的本地端口，请关闭旧服务或使用 --port 指定其他端口。")


def server_ready(port):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(f"http://{HOST}:{port}/config", timeout=2) as response:
            config = json.load(response)
        return isinstance(config, dict) and "Learn Everything" in config.get("title", "")
    except (OSError, ValueError, urllib.error.URLError):
        return False


def wait_for_backend(proc, port, timeout=180):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError("服务启动失败，请查看 .tmp/macos-server.log。")
        if server_ready(port):
            return
        time.sleep(.5)
    raise RuntimeError("服务启动超时，请查看 .tmp/macos-server.log。")


def open_browser(url):
    if Path("/Applications/Microsoft Edge.app").is_dir():
        if subprocess.run(["/usr/bin/open", "-a", "Microsoft Edge", url], check=False).returncode == 0:
            return
    webbrowser.open(url)


def stop_backend(proc):
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Learn Everything · Mac 启动器")
    parser.add_argument("--check", action="store_true", help="仅检查本地运行环境")
    parser.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    parser.add_argument("--port", type=int, default=7860)
    args = parser.parse_args(argv)
    if sys.platform != "darwin":
        parser.error("此入口用于 macOS；Windows 请运行 run.bat。")
    if not 1024 <= args.port <= 65535:
        parser.error("端口需在 1024–65535 之间。")
    proc = None
    previous_handler = signal.getsignal(signal.SIGTERM)
    try:
        print("Learn Everything · 检查 Mac 环境", flush=True)
        check_runtime()
        if args.check:
            print("检查通过。真实钥匙串访问将在保存连接时进行。", flush=True)
            return 0
        port = free_port(args.port)
        python = runtime_python()
        log_path = ROOT / ".tmp" / "macos-server.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("ab") as log:
            proc = subprocess.Popen(
                [str(python), str(ROOT / "custom_app.py")], cwd=ROOT / "kotaemon",
                env=backend_environment(port), stdout=log, stderr=subprocess.STDOUT,
            )
            def terminate(signum, frame):
                raise KeyboardInterrupt
            signal.signal(signal.SIGTERM, terminate)
            print(f"正在启动，首次可能需要约 1–3 分钟。日志：{log_path}", flush=True)
            wait_for_backend(proc, port)
            url = f"http://{HOST}:{port}/"
            print(f"已就绪：{url}\n此窗口保持打开；按 Control+C 停止服务。", flush=True)
            if not args.no_browser:
                open_browser(url)
            return proc.wait()
    except KeyboardInterrupt:
        print("\n正在停止本次启动的服务。", flush=True)
        return 0
    except (OSError, RuntimeError) as exc:
        print(f"启动失败：{exc}", file=sys.stderr, flush=True)
        return 1
    finally:
        signal.signal(signal.SIGTERM, previous_handler)
        if proc is not None:
            stop_backend(proc)


if __name__ == "__main__":
    raise SystemExit(main())
