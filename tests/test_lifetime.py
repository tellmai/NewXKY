import builtins
import sys
from datetime import datetime, timedelta, timezone

import pytest

from newxky.lifetime import BEIJING, EXPIRES_AT, startup_allowed


@pytest.mark.parametrize("moment,expected", [
    (datetime(2027, 6, 30, tzinfo=BEIJING), True),
    (EXPIRES_AT - timedelta(microseconds=1), True),
    (EXPIRES_AT, False),
    (EXPIRES_AT + timedelta(seconds=1), False),
    (datetime(2027, 6, 30, 15, 59, 59, tzinfo=timezone.utc), True),
    (datetime(2027, 6, 30, 16, tzinfo=timezone.utc), False),
])
def test_boundary_in_different_timezones(moment, expected):
    assert startup_allowed(moment) is expected


@pytest.mark.parametrize("arguments", [[], ["--help"], ["--invalid"], ["--self-check", "report.json"]])
def test_main_returns_silently_before_loading_gui_or_creating_files(tmp_path, monkeypatch, capsys, arguments):
    import main
    monkeypatch.setattr(main, "startup_allowed", lambda: False)
    monkeypatch.setattr(sys, "argv", ["NewXKY.exe", *arguments])
    monkeypatch.chdir(tmp_path)
    original = builtins.__import__
    def checked(name, *args, **kwargs):
        assert not name.startswith(("PySide6", "newxky.ui", "newxky.diagnostics"))
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", checked)
    assert main.main() == 0
    output = capsys.readouterr()
    assert output.out == output.err == ""
    assert not list(tmp_path.iterdir())


def test_portable_returns_before_logs_or_error_dialog(tmp_path, monkeypatch, capsys):
    import portable_start
    import newxky.lifetime
    monkeypatch.setattr(newxky.lifetime, "startup_allowed", lambda: False)
    monkeypatch.setattr(sys, "argv", ["portable_start.py", "--data-dir", str(tmp_path / "data")])
    monkeypatch.setattr(portable_start.runpy, "run_path", lambda *a, **k: pytest.fail("entry executed"))
    portable_start.main()
    assert not (tmp_path / "data").exists()
    output = capsys.readouterr()
    assert output.out == output.err == ""
