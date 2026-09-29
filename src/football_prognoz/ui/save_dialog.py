"""'Save as' dialog for the CSV export that can never freeze the window.

Flet 0.80 desktop `FilePicker.save_file` goes through the Flutter file_picker plugin
(NSSavePanel on macOS). Under `flet run` the Flet client has no user-selected-file
entitlement, and on some macOS versions the sheet's completion handler runs off the
main thread (flutter_file_picker #1704/#1741, flet #5334/#5700): the panel does not
show or never answers, while the window stays sheet-modal — the app looks frozen.

So on macOS the dialog is a separate `osascript` process (`choose file name`), run in a
worker thread; the app window never waits for it. Elsewhere the Flet FilePicker is
used with a timeout. Any failure falls back to the app's data/exports folder.
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

__all__ = [
    "DIALOG_TIMEOUT_S",
    "SaveDialogUnavailable",
    "choose_save_path_macos",
    "dialog_kind",
    "macos_script",
    "parse_osascript",
]

DIALOG_TIMEOUT_S = 15 * 60  # a forgotten dialog must not hold the export forever
USER_CANCELED = "-128"


class SaveDialogUnavailable(RuntimeError):
    """The native dialog could not be shown; the caller saves to data/exports."""


def dialog_kind(*, platform: str | None = None, web: bool = False, real_page: bool = True) -> str:
    """'macos' (osascript), 'flet' (FilePicker service) or 'none' (data/exports)."""
    if web or not real_page:
        return "none"
    name = platform or sys.platform
    if name == "darwin":
        return "macos"
    if name.startswith(("win", "linux")):
        return "flet"
    return "none"


def _applescript(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def macos_script(title: str, directory: Path, file_name: str) -> str:
    """AppleScript for a native save panel; prints the POSIX path of the choice."""
    location = ""
    if directory.is_dir():
        location = f" default location (POSIX file {_applescript(str(directory))} as alias)"
    return (
        "activate\n"
        f"set chosen to choose file name with prompt {_applescript(title)}"
        f" default name {_applescript(file_name)}{location}\n"
        "POSIX path of chosen"
    )


def parse_osascript(returncode: int, stdout: str, stderr: str) -> Path | None:
    """Path on success, None when the user pressed Cancel, raise otherwise."""
    if returncode == 0:
        value = stdout.strip()
        if not value:
            raise SaveDialogUnavailable("пустой ответ окна сохранения")
        return Path(value)
    if USER_CANCELED in (stderr or ""):
        return None
    detail = (stderr or "").strip().splitlines()
    raise SaveDialogUnavailable(detail[-1] if detail else f"osascript: код {returncode}")


def choose_save_path_macos(
    title: str,
    directory: Path,
    file_name: str,
    *,
    runner: Callable[..., Any] = subprocess.run,
    timeout: float = DIALOG_TIMEOUT_S,
) -> Path | None:
    """Blocking: call from a worker thread only."""
    try:
        done = runner(
            ["osascript", "-e", macos_script(title, directory, file_name)],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise SaveDialogUnavailable("окно сохранения не ответило") from exc
    except OSError as exc:
        raise SaveDialogUnavailable(str(exc)) from exc
    return parse_osascript(done.returncode, done.stdout or "", done.stderr or "")
