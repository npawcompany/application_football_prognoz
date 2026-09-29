"""Betting-market probabilities derived from the statistical model (read-only facts).

A `Market` is one bookmaker selection ("Тотал больше 2.5"). Its probabilities come from
the model's score matrix (goals) or from API-Football averages (corners, cards, fouls,
penalties). Nothing here is produced or changed by the LLM.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

CONFIDENCE_LEVELS = ("low", "medium", "high")
CONFIDENCE_LABELS = {"low": "низкая", "medium": "средняя", "high": "высокая"}

# Group id -> Russian title, in the order the UI filter shows them.
MARKET_GROUPS: dict[str, str] = {
    "1x2": "Исход 1X2",
    "double_chance": "Двойной шанс",
    "dnb": "Ничья — возврат",
    "totals": "Тотал голов",
    "team_totals": "Индивидуальный тотал",
    "handicap": "Азиатская фора",
    "euro_handicap": "Европейская фора",
    "btts": "Обе забьют",
    "win_to_nil": "Победа всухую",
    "correct_score": "Точный счёт",
    "corners": "Угловые",
    "cards": "Жёлтые карточки",
    "fouls": "Фолы",
    "penalty": "Пенальти",
}

SET_PIECE_GROUPS = frozenset({"corners", "cards", "fouls", "penalty"})

NOTE_NO_KEY = "нет данных (нужен ключ API-Football)"
NOTE_PENDING = "загружаем статистику API-Football…"
NOTE_MISSING = "нет данных API-Football по последним матчам команд"


@dataclass(frozen=True)
class Market:
    """One selection. `win` is None when there is no data: the row says why in `note`.

    For whole-number handicaps and draw-no-bet a stake can be refunded (`push`);
    then win + push + lose = 1 and the fair odds are (1 − push) / win.
    """

    key: str  # stable id, e.g. "total_over_2.5"; the LLM must quote these ids
    group: str  # key of MARKET_GROUPS
    label: str  # Russian, e.g. "Тотал больше 2.5"
    win: float | None
    push: float = 0.0
    popularity: int = 99  # lower = more popular with bookmakers, shown first
    confidence: str = ""  # low | medium | high | "" when unavailable
    note: str = ""

    @property
    def available(self) -> bool:
        return self.win is not None

    @property
    def lose(self) -> float | None:
        if self.win is None:
            return None
        return max(0.0, 1.0 - self.win - self.push)

    @property
    def has_push(self) -> bool:
        return self.push > 1e-9

    @property
    def effective(self) -> float | None:
        """Win probability with refunds taken out: win / (win + lose)."""
        if self.win is None:
            return None
        settled = 1.0 - self.push
        return self.win / settled if settled > 1e-12 else 0.0

    @property
    def fair_odds(self) -> float | None:
        """Decimal odds without bookmaker margin: 1 / effective probability."""
        eff = self.effective
        if eff is None or eff <= 1e-9:
            return None
        return 1.0 / eff

    @property
    def group_label(self) -> str:
        return MARKET_GROUPS.get(self.group, self.group)

    @property
    def confidence_label(self) -> str:
        return CONFIDENCE_LABELS.get(self.confidence, "")

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"id": self.key, "group": self.group, "label": self.label}
        if self.win is None:
            data["note"] = self.note
            return data
        data["probability"] = round(self.effective or 0.0, 4)
        data["win"] = round(self.win, 4)
        if self.has_push:
            data["push"] = round(self.push, 4)
        odds = self.fair_odds
        data["fair_odds"] = round(odds, 2) if odds is not None else None
        data["confidence"] = self.confidence
        return data


@dataclass(frozen=True)
class TeamSetPieces:
    """Per-match averages from API-Football `/fixtures/statistics` + penalty events.

    *_for: what the team did / got (corners won, yellow cards received, fouls
    committed, penalties awarded); *_against: the same for its opponents.
    """

    matches: int
    corners_for: float | None = None
    corners_against: float | None = None
    yellow_for: float | None = None
    yellow_against: float | None = None
    fouls_for: float | None = None
    fouls_against: float | None = None
    penalties_for: float | None = None
    penalties_against: float | None = None
    penalty_matches: int = 0  # matches whose events were read for penalties

    def to_dict(self) -> dict[str, Any]:
        def r(value: float | None) -> float | None:
            return None if value is None else round(value, 2)

        return {
            "matches": self.matches,
            "corners_for": r(self.corners_for),
            "corners_against": r(self.corners_against),
            "yellow_for": r(self.yellow_for),
            "yellow_against": r(self.yellow_against),
            "fouls_for": r(self.fouls_for),
            "fouls_against": r(self.fouls_against),
            "penalties_for": r(self.penalties_for),
            "penalties_against": r(self.penalties_against),
            "penalty_matches": self.penalty_matches,
        }


@dataclass(frozen=True)
class MarketsTable:
    markets: tuple[Market, ...]
    lambda_home: float
    lambda_away: float
    method: str = ""
    sources: tuple[str, ...] = field(default_factory=tuple)

    def by_key(self, key: str) -> Market | None:
        for market in self.markets:
            if market.key == key:
                return market
        return None

    @property
    def keys(self) -> frozenset[str]:
        return frozenset(m.key for m in self.markets)

    @property
    def available_keys(self) -> frozenset[str]:
        return frozenset(m.key for m in self.markets if m.available)

    def sorted(self) -> list[Market]:
        """Popular markets first; stable within the same popularity."""
        order = {m.key: index for index, m in enumerate(self.markets)}
        return sorted(self.markets, key=lambda m: (m.popularity, order[m.key]))

    def groups(self) -> list[str]:
        present = {m.group for m in self.markets}
        return [g for g in MARKET_GROUPS if g in present]

    def in_group(self, group: str | None) -> list[Market]:
        rows = self.sorted()
        if not group:
            return rows
        return [m for m in rows if m.group == group]

    def to_json(self, *, available_only: bool = False) -> dict[str, Any]:
        rows = [m for m in self.sorted() if m.available or not available_only]
        return {
            "lambda_home": round(self.lambda_home, 3),
            "lambda_away": round(self.lambda_away, 3),
            "method": self.method,
            "markets": [m.to_dict() for m in rows],
        }
