"""Startup rules: minimum splash time and the required-keys gate. Pure, no I/O, no Flet."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from football_prognoz.config import Settings

SPLASH_MIN_SECONDS = 3.0

# Only football-data.org is required: every screen (calendar, leagues, forecast) is built
# from its fixtures and standings. Ollama, API-Football and GNews only add optional blocks
# (AI analysis, player status, news) and the app works without them.
REQUIRED_KEYS: dict[str, str] = {"FOOTBALL_DATA_API_KEY": "Ключ football-data.org"}


class SplashTimer:
    """The splash stays at least `min_seconds`, and longer while loading is not done."""

    def __init__(
        self,
        min_seconds: float = SPLASH_MIN_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.min_seconds = min_seconds
        self._clock = clock
        self.started_at = clock()
        self.loaded_at: float | None = None

    def mark_loaded(self) -> None:
        if self.loaded_at is None:
            self.loaded_at = self._clock()

    @property
    def loaded(self) -> bool:
        return self.loaded_at is not None

    def elapsed(self) -> float:
        return self._clock() - self.started_at

    def remaining(self) -> float:
        """Seconds to keep the splash after loading has finished (0 = hide now)."""
        return max(0.0, self.min_seconds - self.elapsed())

    def can_hide(self) -> bool:
        return self.loaded and self.remaining() <= 0.0


def missing_required_keys(settings: Settings) -> list[str]:
    """Env names of required keys that are empty in the current settings."""
    missing: list[str] = []
    if not settings.football_data_api_key.strip():
        missing.append("FOOTBALL_DATA_API_KEY")
    return missing


class GateState(StrEnum):
    OPEN = "open"
    MISSING = "missing"  # a required key is empty
    REJECTED = "rejected"  # the key is present but football-data.org refused it
    CHECKING = "checking"  # a freshly saved key is being validated


# Sections that stay reachable while the gate is closed.
GATE_ALLOWED_SECTIONS = frozenset({"settings"})


@dataclass
class KeyGate:
    """Blocks every section except Settings until the required keys are saved and valid."""

    state: GateState = GateState.OPEN
    missing: list[str] = field(default_factory=list)
    error: str = ""

    @classmethod
    def from_settings(cls, settings: Settings, *, key_rejected: bool = False) -> KeyGate:
        gate = cls()
        gate.evaluate(settings, key_rejected=key_rejected)
        return gate

    @property
    def locked(self) -> bool:
        return self.state is not GateState.OPEN

    def evaluate(self, settings: Settings, *, key_rejected: bool = False) -> GateState:
        self.missing = missing_required_keys(settings)
        if self.missing:
            self.state = GateState.MISSING
            self.error = ""
        elif key_rejected:
            self.state = GateState.REJECTED
        else:
            self.state = GateState.OPEN
            self.error = ""
        return self.state

    def allows(self, section: str) -> bool:
        return not self.locked or section in GATE_ALLOWED_SECTIONS

    def target(self, section: str) -> str:
        """Section that navigation to `section` actually opens."""
        return section if self.allows(section) else "settings"

    def start_check(self) -> None:
        self.state = GateState.CHECKING
        self.error = ""

    def check_passed(self) -> None:
        self.state = GateState.OPEN
        self.missing = []
        self.error = ""

    def check_failed(self, message: str, *, rejected: bool) -> None:
        """A rejected key keeps the gate closed; a network failure lets the user in.

        Without network the key cannot be proven wrong, and the cached data still works,
        so only an explicit 400/401/403 from football-data.org keeps the gate locked.
        """
        if rejected:
            self.state = GateState.REJECTED
            self.error = message
        else:
            self.state = GateState.OPEN
            self.error = ""

    def notice(self) -> str:
        if self.state is GateState.MISSING:
            names = ", ".join(REQUIRED_KEYS.get(key, key) for key in self.missing)
            return f"Чтобы начать, укажите обязательный ключ: {names}. Остальные — по желанию."
        if self.state is GateState.REJECTED:
            detail = f" ({self.error})" if self.error else ""
            return f"football-data.org не принял ключ{detail}. Проверьте его и сохраните снова."
        if self.state is GateState.CHECKING:
            return "Проверяем ключ football-data.org…"
        return ""
