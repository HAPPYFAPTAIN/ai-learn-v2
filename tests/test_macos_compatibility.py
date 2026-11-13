import io
import json
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from learning_ext import host_platform, local_embeddings, macos_launcher as launcher
from learning_ext.agent import tools
from learning_ext.practice import auto_setup


def test_runtime_search_supports_both_existing_layouts(tmp_path):
    with pytest.raises(RuntimeError, match="setup_macos"):
        launcher.runtime_python(tmp_path)
    nested = tmp_path / "kotaemon/.venv/bin/python"
    nested.parent.mkdir(parents=True)
    nested.touch()
    assert launcher.runtime_python(tmp_path) == nested
    direct = tmp_path / ".venv/bin/python"
    direct.parent.mkdir(parents=True)
    direct.touch()
    assert launcher.runtime_python(tmp_path) == direct


def test_backend_is_loopback_and_preserves_user_model_settings(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "test-only-key")
    monkeypatch.setenv("GRADIO_SERVER_NAME", "0.0.0.0")
    env = launcher.backend_environment(7870, tmp_path)
    assert env["GRADIO_SERVER_NAME"] == "127.0.0.1"
    assert env["GRADIO_SERVER_PORT"] == "7870"
    assert env["OPENAI_API_KEY"] == "test-only-key"
    assert env["PYTHONPATH"].startswith(str(tmp_path))


def test_readiness_requires_our_app_not_just_an_open_port(monkeypatch):
    opener = Mock()
    monkeypatch.setattr(launcher.urllib.request, "build_opener", Mock(return_value=opener))
    for title, expected in (("Other Service", False), ("Learn Everything · 以太智元", True)):
        opener.open.return_value = io.StringIO(json.dumps({"title": title}))
        assert launcher.server_ready(7860) is expected
    opener.open.side_effect = OSError("not listening")
    assert not launcher.server_ready(7860)


def test_dead_backend_cannot_be_mistaken_for_ready(monkeypatch):
    monkeypatch.setattr(launcher, "server_ready", lambda _: True)
    with pytest.raises(RuntimeError, match="启动失败"):
        launcher.wait_for_backend(SimpleNamespace(poll=lambda: 1), 7860)


def test_busy_port_is_skipped_and_exhaustion_reported(monkeypatch):
    sock = Mock()
    sock.__enter__ = Mock(return_value=sock)
    sock.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(launcher.socket, "socket", lambda: sock)
    sock.bind.side_effect = [OSError("busy"), None]
    assert launcher.free_port(7860) == 7861
    sock.bind.side_effect = OSError("busy")
    with pytest.raises(RuntimeError, match="没有可用"):
        launcher.free_port(7860)


def test_child_is_reaped_even_when_termination_times_out():
    proc = Mock()
    proc.poll.return_value = None
    proc.wait.side_effect = [subprocess.TimeoutExpired("test", 10), 0]
    launcher.stop_backend(proc)
    proc.terminate.assert_called_once()
    proc.kill.assert_called_once()
    assert proc.wait.call_count == 2


def test_launch_failure_cleans_up_only_its_child(monkeypatch, tmp_path):
    monkeypatch.setattr(launcher.sys, "platform", "darwin")
    monkeypatch.setattr(launcher, "ROOT", tmp_path)
    monkeypatch.setattr(launcher, "check_runtime", lambda: None)
    monkeypatch.setattr(launcher, "free_port", lambda _: 7861)
    monkeypatch.setattr(launcher, "runtime_python", lambda: Path("/runtime/python"))
    monkeypatch.setattr(launcher, "backend_environment", lambda _: {})
    proc = Mock()
    spawn = Mock(return_value=proc)
    monkeypatch.setattr(launcher.subprocess, "Popen", spawn)
    monkeypatch.setattr(launcher, "wait_for_backend", Mock(side_effect=RuntimeError("startup error")))
    cleanup = Mock()
    monkeypatch.setattr(launcher, "stop_backend", cleanup)
    assert launcher.main(["--no-browser"]) == 1
    cleanup.assert_called_once_with(proc)
    assert spawn.call_args.args[0] == ["/runtime/python", str(tmp_path / "custom_app.py")]


def test_edge_is_preferred_without_shell_interpolation(monkeypatch):
    monkeypatch.setattr(launcher.Path, "is_dir", lambda _: True)
    run = Mock(return_value=SimpleNamespace(returncode=0))
    monkeypatch.setattr(launcher.subprocess, "run", run)
    launcher.open_browser("http://127.0.0.1:7861/")
    assert run.call_args.args[0] == ["/usr/bin/open", "-a", "Microsoft Edge", "http://127.0.0.1:7861/"]


@pytest.mark.parametrize("platform,label,shell", [("darwin", "macOS", "zsh"), ("win32", "Windows", "PowerShell"), ("linux", "Linux", "POSIX")])
def test_coaching_targets_host_os(monkeypatch, platform, label, shell):
    monkeypatch.setattr(host_platform.sys, "platform", platform)
    text = host_platform.host_instructions()
    assert label in text and shell in text


@pytest.mark.skipif(os.name == "nt", reason="POSIX shells")
@pytest.mark.parametrize("command,success", [("printf mac-test-ok", True), ("false; printf should-not-run", False), ("exit 7", False)])
def test_native_shell_reports_failure_and_does_not_continue(command, success):
    output = list(auto_setup.run_command_streaming(command))
    assert ("退出码 0" in output[-1]) is success
    assert "should-not-run" not in "".join(output)


def test_mac_file_open_and_clipboard_use_native_commands(monkeypatch, tmp_path):
    monkeypatch.setattr(tools.sys, "platform", "darwin")
    run = Mock(return_value=SimpleNamespace(returncode=0, stdout="测试文本", stderr=""))
    monkeypatch.setattr(tools.subprocess, "run", run)
    path = tmp_path / "space and $(example).txt"
    path.touch()
    assert "已用" in tools._open_path(str(path))
    assert run.call_args.args[0] == ["/usr/bin/open", str(path)]
    assert "测试文本" in tools._clipboard_get()
    assert run.call_args.args[0] == ["/usr/bin/pbpaste"]
    assert "已写入" in tools._clipboard_set("测试文本")
    assert run.call_args.args[0] == ["/usr/bin/pbcopy"]
    assert run.call_args.kwargs["input"] == "测试文本"


def test_windows_desktop_operations_are_not_exposed_on_mac(monkeypatch):
    monkeypatch.setattr(tools.sys, "platform", "darwin")
    names = {row["function"]["name"] for row in tools.build_tool_specs()}
    assert not (names & tools.WINDOWS_DESKTOP_TOOLS)
    assert {"open_path", "clipboard_get", "run_command"} <= names
    assert "仅支持 Windows" in tools.execute_tool("click_ui", {"text": "test"})


def test_mac_ollama_can_be_found_on_path(monkeypatch, tmp_path):
    monkeypatch.setattr(local_embeddings.sys, "platform", "darwin")
    binary = tmp_path / "ollama"
    binary.touch()
    binary.chmod(0o700)
    monkeypatch.setattr(local_embeddings.shutil, "which", lambda _: str(binary))
    assert local_embeddings._installed_ollama() == binary
