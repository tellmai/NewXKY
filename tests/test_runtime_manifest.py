"""The packaged build must carry its own Qt/VC++ runtime and say what is missing."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

import main as entry
from newxky import runtime_manifest

ALL = runtime_manifest.RUNTIME_FILES


def make_bundle(root: Path, names=ALL):
    for name in names:
        path = root / "_internal" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x")
    bank = root / "题库"
    bank.mkdir(parents=True, exist_ok=True)
    (bank / "default-bank.json").write_text("{}", encoding="utf-8")
    return root / "_internal"


def test_complete_bundle_reports_nothing(tmp_path):
    make_bundle(tmp_path)
    assert runtime_manifest.missing_runtime(tmp_path / "_internal") == []
    assert runtime_manifest.missing_bank(tmp_path) == []
    assert runtime_manifest.startup_problem(tmp_path / "_internal", tmp_path) == ""


def test_missing_qt_dll_is_named_with_actionable_steps(tmp_path):
    make_bundle(tmp_path, [name for name in ALL if not name.startswith("PySide6/")])
    message = runtime_manifest.startup_problem(tmp_path / "_internal", tmp_path)
    assert "PySide6/Qt6Core.dll" in message
    assert "PySide6/plugins/platforms/qwindows.dll" in message
    assert "不要只复制 NewXKY.exe" in message
    assert "Visual C++" in message


@pytest.mark.parametrize("name", [
    "python311.dll",
    "VCRUNTIME140.dll",
    "MSVCP140.dll",
    "ucrtbase.dll",
    "api-ms-win-core-sysinfo-l1-2-0.dll",
    "api-ms-win-crt-runtime-l1-1-0.dll",
])
def test_every_runtime_file_is_required(tmp_path, name):
    make_bundle(tmp_path, [entry for entry in ALL if entry != name])
    assert name in runtime_manifest.startup_problem(tmp_path / "_internal", tmp_path)


def test_bank_inside_internal_is_accepted(tmp_path):
    make_bundle(tmp_path)
    (tmp_path / "题库" / "default-bank.json").unlink()
    inner = tmp_path / "_internal" / "题库"
    inner.mkdir(parents=True, exist_ok=True)
    (inner / "default-bank.json").write_text("{}", encoding="utf-8")
    assert runtime_manifest.missing_bank(tmp_path) == []


def test_missing_bank_is_reported(tmp_path):
    make_bundle(tmp_path)
    (tmp_path / "题库" / "default-bank.json").unlink()
    assert runtime_manifest.missing_bank(tmp_path)
    assert "题库/default-bank.json" in runtime_manifest.startup_problem(
        tmp_path / "_internal", tmp_path)


def test_frozen_startup_problem_uses_the_manifest(tmp_path, monkeypatch):
    make_bundle(tmp_path, [name for name in ALL if name != "MSVCP140.dll"])
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "_internal"), raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "NewXKY.exe"))
    message = entry._startup_problem()
    assert "MSVCP140.dll" in message
    assert str(tmp_path) in message


def test_source_run_never_blocks_startup(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert entry._startup_problem() == ""


def test_packaging_ships_the_runtime_checker():
    root = Path(__file__).resolve().parents[1]
    checker = root / "scripts" / "check_runtime.cmd"
    assert checker.is_file()
    raw = checker.read_bytes()
    # cmd.exe parses batch files with the console code page; non-ASCII bytes
    # inside the script corrupt the command block on some systems.
    assert all(byte < 128 for byte in raw)
    text = checker.read_text(encoding="ascii")
    assert r"_internal\PySide6\Qt6Core.dll" in text
    for name in runtime_manifest.RUNTIME_FILES:
        assert name.replace("/", "\\") in text, name
