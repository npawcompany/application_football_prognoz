from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from football_prognoz.ui.save_dialog import (
    SaveDialogUnavailable,
    choose_save_path_macos,
    dialog_kind,
    macos_script,
    parse_osascript,
)


def test_dialog_kind_per_platform() -> None:
    assert dialog_kind(platform="darwin") == "macos"
    assert dialog_kind(platform="win32") == "flet"
    assert dialog_kind(platform="linux") == "flet"
    assert dialog_kind(platform="darwin", web=True) == "none"
    assert dialog_kind(platform="darwin", real_page=False) == "none"


def test_macos_script_quotes_and_uses_existing_folder(tmp_path: Path) -> None:
    script = macos_script('Куда "сохранить"', tmp_path, "a.csv")
    assert 'with prompt "Куда \\"сохранить\\""' in script
    assert 'default name "a.csv"' in script
    assert f'POSIX file "{tmp_path}" as alias' in script
    assert "default location" not in macos_script("t", tmp_path / "missing", "a.csv")


def test_parse_osascript_path_cancel_and_error() -> None:
    assert parse_osascript(0, "/Users/me/h.csv\n", "") == Path("/Users/me/h.csv")
    assert parse_osascript(1, "", "execution error: User canceled. (-128)") is None
    with pytest.raises(SaveDialogUnavailable):
        parse_osascript(1, "", "execution error: Not authorized (-1743)")
    with pytest.raises(SaveDialogUnavailable):
        parse_osascript(0, "  ", "")


def test_choose_save_path_macos_timeout_and_missing_binary(tmp_path: Path) -> None:
    def ok(cmd, **_kw):
        assert cmd[0] == "osascript"
        return SimpleNamespace(returncode=0, stdout=f"{tmp_path}/x.csv\n", stderr="")

    assert choose_save_path_macos("t", tmp_path, "x.csv", runner=ok) == tmp_path / "x.csv"

    def hang(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd, kw["timeout"])

    with pytest.raises(SaveDialogUnavailable):
        choose_save_path_macos("t", tmp_path, "x.csv", runner=hang, timeout=1)

    def missing(cmd, **_kw):
        raise FileNotFoundError("osascript")

    with pytest.raises(SaveDialogUnavailable):
        choose_save_path_macos("t", tmp_path, "x.csv", runner=missing)
