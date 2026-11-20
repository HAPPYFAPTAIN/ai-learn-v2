"""僵死任务回收的定时入口。"""

from __future__ import annotations

from learn_core.jobs import reaper


def test_cli_reports_reaped_ids(monkeypatch, capsys):
    monkeypatch.setattr(reaper, "reap_stalled_jobs", lambda seconds, queue: [11, 12])
    assert reaper.main(["--queue", "io"]) == 0
    out = capsys.readouterr().out
    assert "reaped 2 job(s): 11,12" in out


def test_cli_returns_nonzero_on_failure(monkeypatch, capsys):
    def boom(seconds, queue):
        raise RuntimeError("db down")

    monkeypatch.setattr(reaper, "reap_stalled_jobs", boom)
    assert reaper.main([]) == 1
    err = capsys.readouterr().err
    assert "reaper failed: RuntimeError" in err
