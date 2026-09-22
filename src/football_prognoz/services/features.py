from __future__ import annotations

from collections import defaultdict

from football_prognoz.data.store import SQLiteStore
from football_prognoz.domain.match import Match
from football_prognoz.domain.prediction import MatchFeatures
from football_prognoz.models.elo import INITIAL_ELO, build_elo

EloFingerprint = tuple[tuple[int, str, int | None, int | None], ...]


def _elo_fingerprint(matches: list[Match]) -> EloFingerprint:
    return tuple(
        (item.id, item.utc_date.isoformat(), item.score.home, item.score.away)
        for item in matches
        if item.status.is_finished()
    )


def _form_char(match: Match, team_id: int) -> str:
    if match.score.home is None or match.score.away is None:
        return ""
    if match.home_id == team_id:
        if match.score.home > match.score.away:
            return "W"
        if match.score.home < match.score.away:
            return "L"
        return "D"
    if match.score.away > match.score.home:
        return "W"
    if match.score.away < match.score.home:
        return "L"
    return "D"


class FeatureService:
    def __init__(self, store: SQLiteStore, form_n: int = 5) -> None:
        self._store = store
        self._form_n = form_n
        self._elo_cache: dict[str, tuple[EloFingerprint, dict[int, float]]] = {}

    def _elo_for(self, competition_code: str, history: list[Match]) -> dict[int, float]:
        fingerprint = _elo_fingerprint(history)
        cached = self._elo_cache.get(competition_code)
        if cached is not None and cached[0] == fingerprint:
            return cached[1]
        elo = build_elo(history)
        self._elo_cache[competition_code] = (fingerprint, elo)
        return elo

    def build(self, match: Match) -> MatchFeatures:
        history = [
            item
            for item in self._store.list_matches(match.competition_code)
            if item.status.is_finished() and item.utc_date < match.utc_date
        ]
        elo = self._elo_for(match.competition_code, history)
        home_games = [m for m in history if match.home_id in {m.home_id, m.away_id}]
        away_games = [m for m in history if match.away_id in {m.home_id, m.away_id}]
        h2h = [m for m in history if {m.home_id, m.away_id} == {match.home_id, match.away_id}][-5:]

        standings = {row.team_id: row for row in self._store.list_standings(match.competition_code)}
        home_row = standings.get(match.home_id)
        away_row = standings.get(match.away_id)

        return MatchFeatures(
            home_form=self._form(home_games, match.home_id),
            away_form=self._form(away_games, match.away_id),
            home_elo=elo.get(match.home_id, INITIAL_ELO),
            away_elo=elo.get(match.away_id, INITIAL_ELO),
            h2h_summary=self._h2h_summary(h2h, match),
            home_position=home_row.position if home_row else None,
            away_position=away_row.position if away_row else None,
            home_recent_goals_for=self._avg_goals(home_games[-self._form_n :], match.home_id, True),
            home_recent_goals_against=self._avg_goals(
                home_games[-self._form_n :], match.home_id, False
            ),
            away_recent_goals_for=self._avg_goals(away_games[-self._form_n :], match.away_id, True),
            away_recent_goals_against=self._avg_goals(
                away_games[-self._form_n :], match.away_id, False
            ),
            sample_matches=len(history),
            h2h_matches=tuple(h2h),
            home_standing=home_row,
            away_standing=away_row,
        )

    def _form(self, games: list[Match], team_id: int) -> str:
        chars = [_form_char(item, team_id) for item in games[-self._form_n :]]
        return "".join(c for c in chars if c) or "—"

    def _h2h_summary(self, games: list[Match], match: Match) -> str:
        if not games:
            return "Нет очных встреч"
        counts: dict[str, int] = defaultdict(int)
        for item in games:
            if item.score.winner == "DRAW" or (
                item.score.home is not None
                and item.score.away is not None
                and item.score.home == item.score.away
            ):
                counts["draw"] += 1
            elif item.score.home is not None and item.score.away is not None:
                if item.home_id == match.home_id and item.score.home > item.score.away:
                    counts["home"] += 1
                elif item.away_id == match.home_id and item.score.away > item.score.home:
                    counts["home"] += 1
                else:
                    counts["away"] += 1
        return (
            f"Последние {len(games)}: {match.home_name} {counts['home']}, "
            f"ничьи {counts['draw']}, {match.away_name} {counts['away']}"
        )

    @staticmethod
    def _avg_goals(games: list[Match], team_id: int, scored: bool) -> float:
        if not games:
            return 1.35
        values: list[int] = []
        for item in games:
            if item.score.home is None or item.score.away is None:
                continue
            if item.home_id == team_id:
                values.append(item.score.home if scored else item.score.away)
            else:
                values.append(item.score.away if scored else item.score.home)
        if not values:
            return 1.35
        return sum(values) / len(values)
