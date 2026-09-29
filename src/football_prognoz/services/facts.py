"""Structured facts package for the LLM explainer.

Everything here is computed from the SQLite cache (football-data.org) and, when
available, the API-Football player-status report. The LLM only reads this package;
it does not change the 1X2 probabilities.
"""

from __future__ import annotations

from typing import Any

from football_prognoz.data.store import SQLiteStore
from football_prognoz.domain.match import Match
from football_prognoz.domain.news import NewsReport, TeamNews
from football_prognoz.domain.player_status import PlayerStatusReport, TeamStatus
from football_prognoz.domain.prediction import (
    FactsPackage,
    MatchFeatures,
    Probabilities,
    Scoreline,
)
from football_prognoz.models.elo import HOME_ADVANTAGE

SRC_FOOTBALL_DATA = "football-data.org: календарь, результаты, таблица (кэш SQLite)"
SRC_MODEL = "Локальная модель Elo + Пуассон (вероятности 1X2)"
SRC_HISTORY = "История прогнозов приложения (SQLite forecast_history)"
HOME_AWAY_WINDOW = 10
_POINTS = {"W": 3, "D": 1, "L": 0}


def _goals_for_against(match: Match, team_id: int) -> tuple[int, int] | None:
    if match.score.home is None or match.score.away is None:
        return None
    if match.home_id == team_id:
        return match.score.home, match.score.away
    return match.score.away, match.score.home


def _record(games: list[Match], team_id: int) -> dict[str, Any]:
    won = draw = lost = gf = ga = 0
    for item in games:
        goals = _goals_for_against(item, team_id)
        if goals is None:
            continue
        scored, conceded = goals
        gf += scored
        ga += conceded
        if scored > conceded:
            won += 1
        elif scored == conceded:
            draw += 1
        else:
            lost += 1
    played = won + draw + lost
    return {
        "played": played,
        "won": won,
        "draw": draw,
        "lost": lost,
        "goals_for": gf,
        "goals_against": ga,
    }


def _avg(games: list[Match], team_id: int, *, scored: bool) -> float | None:
    values = []
    for item in games:
        goals = _goals_for_against(item, team_id)
        if goals is not None:
            values.append(goals[0] if scored else goals[1])
    return round(sum(values) / len(values), 2) if values else None


def _trend(recent: float | None, season: float | None) -> str:
    if recent is None or season is None:
        return "нет данных"
    if recent - season >= 0.3:
        return "выше среднего за сезон"
    if season - recent >= 0.3:
        return "ниже среднего за сезон"
    return "на уровне сезона"


def _form_points(form: str) -> int | None:
    chars = [c for c in form if c in _POINTS]
    return sum(_POINTS[c] for c in chars) if chars else None


def _team_status_facts(status: TeamStatus) -> dict[str, Any]:
    return {
        "absences": [
            {
                "player": a.player_name,
                "status": "не сыграет" if a.is_certain else "под вопросом",
                "reason": a.reason,
                "suspension": a.is_suspension,
                "key_player": a.key_player,
                "expected_return": a.expected_return,
            }
            for a in status.absences
        ],
        "recent_red_cards": [
            {
                "player": c.player_name,
                "detail": c.detail,
                "date": c.fixture_date,
                "minute": c.minute,
            }
            for c in status.red_cards
        ],
        "recent_transfers": [
            {
                "player": t.player_name,
                "direction": "пришёл" if t.direction == "in" else "ушёл",
                "other_team": t.other_team,
                "date": t.date,
                "type": t.kind,
            }
            for t in status.transfers
        ],
        "lineup": (
            {
                "formation": status.lineup.formation,
                "start_xi": [p.name for p in status.lineup.start_xi],
                "coach": status.lineup.coach,
            }
            if status.lineup is not None and status.lineup.start_xi
            else None
        ),
        "top_rated_last_match": [
            {"player": r.player_name, "rating": r.rating} for r in status.top_ratings
        ],
    }


def player_status_facts(report: PlayerStatusReport | None) -> dict[str, Any] | None:
    if report is None or not report.has_data():
        return None
    return {
        "home": _team_status_facts(report.home),
        "away": _team_status_facts(report.away),
        "notes": list(report.notes),
        "verified_live": False,
    }


def _team_news_facts(team: TeamNews) -> list[dict[str, Any]]:
    return [
        {
            "title": item.title,
            "source": item.source,
            "published": item.published_at.date().isoformat(),
            "topic": item.topic_label,
        }
        for item in team.items
    ]


def news_facts(report: NewsReport | None) -> dict[str, Any] | None:
    """Indirect factor: recent headlines. Unverified, never part of 1X2."""
    if report is None or not report.has_data():
        return None
    return {
        "home": _team_news_facts(report.home),
        "away": _team_news_facts(report.away),
        "provider": report.provider,
        "note": "заголовки СМИ не проверены и не меняют вероятности 1X2",
    }


class FactsService:
    def __init__(self, store: SQLiteStore) -> None:
        self._store = store

    def build(
        self,
        match: Match,
        features: MatchFeatures,
        probabilities: Probabilities,
        scoreline: Scoreline | None = None,
        player_status: PlayerStatusReport | None = None,
        news: NewsReport | None = None,
        history_summary: dict[str, Any] | None = None,
    ) -> FactsPackage:
        history = [
            item
            for item in self._store.list_matches(match.competition_code)
            if item.status.is_finished() and item.utc_date < match.utc_date
        ]
        home_games = [m for m in history if match.home_id in {m.home_id, m.away_id}]
        away_games = [m for m in history if match.away_id in {m.home_id, m.away_id}]
        home_at_home = [m for m in home_games if m.home_id == match.home_id][-HOME_AWAY_WINDOW:]
        away_on_road = [m for m in away_games if m.away_id == match.away_id][-HOME_AWAY_WINDOW:]

        def rest_days(games: list[Match]) -> int | None:
            if not games:
                return None
            return max(0, (match.utc_date - games[-1].utc_date).days)

        def standing(row: Any) -> dict[str, Any] | None:
            if row is None:
                return None
            return {
                "position": row.position,
                "points": row.points,
                "played": row.played,
                "goal_diff": row.goals_for - row.goals_against,
            }

        data: dict[str, Any] = {
            "sample_matches": features.sample_matches,
            "elo": {
                "home": round(features.home_elo, 1),
                "away": round(features.away_elo, 1),
                "gap": round(features.home_elo - features.away_elo, 1),
                "gap_with_home_advantage": round(
                    features.home_elo + HOME_ADVANTAGE - features.away_elo, 1
                ),
            },
            "form": {
                "home": features.home_form,
                "away": features.away_form,
                "home_points_last5": _form_points(features.home_form),
                "away_points_last5": _form_points(features.away_form),
            },
            "home_away": {
                "home_team_at_home": _record(home_at_home, match.home_id),
                "away_team_away": _record(away_on_road, match.away_id),
                "window": HOME_AWAY_WINDOW,
            },
            "goal_trends": {
                side: {
                    "recent_for": round(recent_for, 2),
                    "recent_against": round(recent_against, 2),
                    "season_for": _avg(games, team_id, scored=True),
                    "season_against": _avg(games, team_id, scored=False),
                    "attack_trend": _trend(recent_for, _avg(games, team_id, scored=True)),
                    "defence_trend": _trend(recent_against, _avg(games, team_id, scored=False)),
                }
                for side, team_id, games, recent_for, recent_against in (
                    (
                        "home",
                        match.home_id,
                        home_games,
                        features.home_recent_goals_for,
                        features.home_recent_goals_against,
                    ),
                    (
                        "away",
                        match.away_id,
                        away_games,
                        features.away_recent_goals_for,
                        features.away_recent_goals_against,
                    ),
                )
            },
            "standings": {
                "home": standing(features.home_standing),
                "away": standing(features.away_standing),
            },
            "head_to_head": {
                "summary": features.h2h_summary,
                "matches": [
                    {
                        "date": m.utc_date.date().isoformat(),
                        "home": m.home_name,
                        "away": m.away_name,
                        "score": f"{m.score.home}:{m.score.away}",
                    }
                    for m in features.h2h_matches
                ],
            },
            "rest_days": {
                "home": rest_days(home_games),
                "away": rest_days(away_games),
                "note": "только по матчам этой лиги в кэше",
            },
            "player_status": player_status_facts(player_status),
            "news": news_facts(news),
            "historical_accuracy": history_summary,
        }
        if scoreline is not None:
            data["preliminary_score"] = scoreline.label
        sources = [SRC_FOOTBALL_DATA, SRC_MODEL]
        if player_status is not None and player_status.has_data():
            sources.extend(player_status.sources)
        if news is not None and news.has_data():
            sources.extend(news.sources)
        if history_summary is not None:
            sources.append(SRC_HISTORY)
        return FactsPackage(data=data, sources=tuple(dict.fromkeys(sources)))
