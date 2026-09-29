"""Forecast history collection: the training / evaluation dataset for VKR §3.3.

Rules (docs/FORECAST.md, "История прогнозов"):
- one row per (match_id, model_version); re-runs update, never duplicate;
- a pre-match forecast is frozen at kick-off: after that only status / real score
  change, the probabilities and facts are never overwritten with post-match data;
- a forecast first computed after kick-off is stored with made_after_kickoff = 1
  and excluded from quality evaluation;
- collection uses only local data (SQLite + football-data.org league refresh), so it
  does not spend API-Football / GNews / LLM quotas.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Iterable
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from football_prognoz.data.store import SQLiteStore
from football_prognoz.domain.history import (
    STATUS_CANCELLED,
    STATUS_FINISHED,
    STATUS_LIVE,
    STATUS_POSTPONED,
    STATUS_SCHEDULED,
    STATUS_SUSPENDED,
    CollectionResult,
    ForecastRecord,
    outcome_from_score,
)
from football_prognoz.domain.match import Match, MatchStatus
from football_prognoz.domain.prediction import MatchFeatures, Probabilities
from football_prognoz.models.markets import build_markets
from football_prognoz.models.predictor import (
    MODEL_VERSION,
    Predictor,
    goals_only_lambda,
    top_scorelines,
)
from football_prognoz.services.facts import SRC_FOOTBALL_DATA, SRC_MODEL, FactsService
from football_prognoz.services.features import FeatureService

log = logging.getLogger(__name__)

DAYS_BACK = 14
DAYS_AHEAD = 14

STALE_RESULT_AFTER = timedelta(hours=2)  # force a league refresh for such results

# progress(done, total, message)
Progress = Callable[[int, int, str], None]

_STATUS_MAP = {
    MatchStatus.SCHEDULED: STATUS_SCHEDULED,
    MatchStatus.TIMED: STATUS_SCHEDULED,
    MatchStatus.IN_PLAY: STATUS_LIVE,
    MatchStatus.PAUSED: STATUS_LIVE,
    MatchStatus.FINISHED: STATUS_FINISHED,
    MatchStatus.AWARDED: STATUS_FINISHED,
    MatchStatus.POSTPONED: STATUS_POSTPONED,
    MatchStatus.SUSPENDED: STATUS_SUSPENDED,
    MatchStatus.CANCELLED: STATUS_CANCELLED,
}


def record_status(status: MatchStatus) -> str:
    return _STATUS_MAP.get(status, STATUS_SCHEDULED)


def _features_dict(features: MatchFeatures) -> dict[str, object]:
    return {
        "home_form": features.home_form,
        "away_form": features.away_form,
        "home_elo": round(features.home_elo, 1),
        "away_elo": round(features.away_elo, 1),
        "home_recent_goals_for": round(features.home_recent_goals_for, 3),
        "home_recent_goals_against": round(features.home_recent_goals_against, 3),
        "away_recent_goals_for": round(features.away_recent_goals_for, 3),
        "away_recent_goals_against": round(features.away_recent_goals_against, 3),
        "home_position": features.home_position,
        "away_position": features.away_position,
        "h2h": features.h2h_summary,
        "sample_matches": features.sample_matches,
    }


class ForecastHistoryService:
    def __init__(
        self,
        store: SQLiteStore,
        *,
        features: FeatureService | None = None,
        predictor: Predictor | None = None,
        facts: FactsService | None = None,
        refresh: Callable[[str, bool], list[Match]] | None = None,
        model_version: str = MODEL_VERSION,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._store = store
        self._features = features or FeatureService(store)
        self._predictor = predictor or Predictor()
        self._facts = facts or FactsService(store)
        self._refresh = refresh
        self.model_version = model_version
        self._now = now or (lambda: datetime.now(UTC))

    # --- record building ------------------------------------------------------

    def build_record(self, match: Match, now: datetime) -> ForecastRecord:
        features = self._features.build(match)
        probs = self._predictor.predict(match, features)
        scoreline = self._predictor.preliminary_score(features)
        lam_home, lam_away = goals_only_lambda(features)
        facts = self._facts.build(match, features, probs, scoreline)
        outcomes = sorted(
            (("1", probs.home), ("X", probs.draw), ("2", probs.away)),
            key=lambda item: -item[1],
        )
        likely = [{"outcome": label, "probability": round(p, 4)} for label, p in outcomes] + [
            {"score": s.label, "probability": round(s.probability, 4)}
            for s in top_scorelines(lam_home, lam_away, 3)
        ]
        started = now >= match.utc_date or not (
            match.status.is_upcoming() or match.status == MatchStatus.POSTPONED
        )
        return ForecastRecord(
            match_id=match.id,
            model_version=self.model_version,
            competition_code=match.competition_code,
            kickoff_utc=match.utc_date,
            home_id=match.home_id,
            home_name=match.home_name,
            away_id=match.away_id,
            away_name=match.away_name,
            p_home=round(probs.home, 6),
            p_draw=round(probs.draw, 6),
            p_away=round(probs.away, 6),
            predicted_outcome=probs.favorite_label,
            predicted_score=scoreline.label,
            score_probability=round(scoreline.probability, 6),
            expected_home=round(scoreline.expected_home, 4),
            expected_away=round(scoreline.expected_away, 4),
            likely_outcomes=tuple(likely),
            facts={"direct": _features_dict(features), "indirect": facts.data},
            sources=tuple(dict.fromkeys((SRC_FOOTBALL_DATA, SRC_MODEL, *facts.sources))),
            sample_matches=features.sample_matches,
            forecast_at=now,
            made_after_kickoff=started,
            status=record_status(match.status),
            markets=self._markets_json(features, probs),
        )

    def _markets_json(
        self, features: MatchFeatures, probs: Probabilities
    ) -> dict[str, object] | None:
        """Goal markets only: collection stays local and spends no API-Football quota."""
        try:
            lam_home, lam_away = self._predictor.goal_lambdas(features)
            table = build_markets(lam_home, lam_away, probs, sample_matches=features.sample_matches)
        except Exception as exc:  # noqa: BLE001 — optional column, never blocks collection
            log.warning("Markets for history failed: %s", exc)
            return None
        return table.to_json(available_only=True)

    # --- results --------------------------------------------------------------

    def apply_result(self, record: ForecastRecord, match: Match) -> bool:
        """Copy status / final score from football-data.org onto an existing row."""
        status = record_status(match.status)
        home = away = outcome = None
        correct = None
        if status == STATUS_FINISHED:
            home, away = match.score.home, match.score.away
            outcome = outcome_from_score(home, away)
            correct = None if outcome is None else outcome == record.predicted_outcome
        return self._store.update_forecast_result(
            record.match_id,
            record.model_version,
            status=status,
            kickoff_utc=match.utc_date,
            actual_home=home,
            actual_away=away,
            actual_outcome=outcome,
            is_correct=correct,
        )

    def fill_results(self, now: datetime | None = None) -> int:
        """Rows whose kick-off passed but result is unknown: read the match from SQLite."""
        now = now or self._now()
        filled = 0
        for record in self._store.list_forecast_records(self.model_version, unresolved_before=now):
            match = self._store.get_match(record.match_id)
            if match is not None and self.apply_result(record, match):
                filled += 1
        return filled

    # --- collection -----------------------------------------------------------

    def upsert(self, match: Match, now: datetime) -> str:
        """Returns 'inserted' | 'updated' | 'unchanged' (forecast part only)."""
        existing = self._store.get_forecast_record(match.id, self.model_version)
        if existing is None:
            record = self.build_record(match, now)
            if self._store.insert_forecast_record(record):
                return "inserted"
            return "unchanged"  # a concurrent run inserted it first
        # Pre-match rows may be refreshed with fresher data while the match has not
        # started; after kick-off the stored forecast is frozen.
        still_before = now < match.utc_date and (
            match.status.is_upcoming() or match.status == MatchStatus.POSTPONED
        )
        if existing.made_after_kickoff or not still_before:
            return "unchanged"
        record = self.build_record(match, now)
        if record.made_after_kickoff:
            return "unchanged"
        comparable = replace(record, forecast_at=existing.forecast_at, status=existing.status)
        if comparable == replace(existing, status=existing.status):
            return "unchanged"
        return "updated" if self._store.update_forecast_prediction(record) else "unchanged"

    def targets(self, matches: Iterable[Match], now: datetime) -> list[Match]:
        start = now - timedelta(days=DAYS_BACK)
        end = now + timedelta(days=DAYS_AHEAD)
        return sorted(
            (
                m
                for m in matches
                if start <= m.utc_date <= end and m.status != MatchStatus.CANCELLED
            ),
            key=lambda m: (m.utc_date, m.id),
        )

    def collect(
        self,
        codes: Iterable[str],
        *,
        progress: Progress | None = None,
        cancel: threading.Event | None = None,
    ) -> CollectionResult:
        """Forecast every upcoming / recent match of `codes`, then fill real results."""
        cancel = cancel or threading.Event()
        report = progress or (lambda _d, _t, _m: None)
        codes = [c for c in dict.fromkeys(code.strip().upper() for code in codes) if c]
        errors: list[str] = []
        matches: list[Match] = []
        for index, code in enumerate(codes):
            if cancel.is_set():
                return CollectionResult(cancelled=True, errors=tuple(errors))
            report(0, 0, f"Обновляем матчи {code} ({index + 1}/{len(codes)})…")
            try:
                if self._refresh is None:
                    league = self._store.list_matches(code)
                else:
                    league = self._refresh(code, self._needs_fresh_results(code))
            except Exception as exc:  # noqa: BLE001 — keep going with the cache
                log.warning("History refresh %s failed: %s", code, exc)
                errors.append(f"{code}: {exc}")
                league = self._store.list_matches(code)
            matches.extend(league)

        now = self._now()
        targets = self.targets(matches, now)
        counts = {"inserted": 0, "updated": 0, "unchanged": 0}
        post_kickoff = results = 0
        total = len(targets)
        cancelled = False
        for done, match in enumerate(targets, start=1):
            if cancel.is_set():
                cancelled = True
                break
            try:
                outcome = self.upsert(match, now)
                counts[outcome] += 1
                record = self._store.get_forecast_record(match.id, self.model_version)
                if record is not None:
                    if outcome == "inserted" and record.made_after_kickoff:
                        post_kickoff += 1
                    if (
                        self.apply_result(record, match)
                        and record_status(match.status) == STATUS_FINISHED
                    ):
                        results += 1
            except Exception as exc:  # noqa: BLE001 — one bad match must not stop the run
                log.warning("History for match %s failed: %s", match.id, exc)
                errors.append(f"{match.label}: {exc}")
            report(done, total, f"{match.home_name} — {match.away_name}")

        if not cancelled:
            results += self.fill_results(now)
        return CollectionResult(
            inserted=counts["inserted"],
            updated=counts["updated"],
            unchanged=counts["unchanged"],
            results_filled=results,
            post_kickoff=post_kickoff,
            total=total,
            cancelled=cancelled,
            errors=tuple(errors),
        )

    def _needs_fresh_results(self, code: str) -> bool:
        """Bypass the 6 h league TTL only when a stored forecast awaits its result."""
        cutoff = self._now() - STALE_RESULT_AFTER
        return any(
            record.competition_code == code
            for record in self._store.list_forecast_records(
                self.model_version, unresolved_before=cutoff
            )
        )

    def records(self) -> list[ForecastRecord]:
        return self._store.list_forecast_records(self.model_version)
