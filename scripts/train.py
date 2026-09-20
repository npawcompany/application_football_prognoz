#!/usr/bin/env python3
"""Import local CSVs into SQLite and print Elo leaders (no live API)."""

from __future__ import annotations

from sklearn.metrics import log_loss

from football_prognoz.config import ROOT_DIR, load_settings
from football_prognoz.data.csv_loader import load_csv
from football_prognoz.data.store import SQLiteStore
from football_prognoz.models.elo import build_elo
from football_prognoz.models.predictor import Predictor
from football_prognoz.services.features import FeatureService


def main() -> None:
    settings = load_settings()
    store = SQLiteStore(settings.db_path)
    csv_dir = ROOT_DIR / "data" / "csv"
    files = sorted(csv_dir.glob("*.csv"))
    if not files:
        sample = ROOT_DIR / "data" / "samples" / "sample_results.csv"
        files = [sample]
        print(f"No files in {csv_dir}, using {sample}")
    imported = 0
    for path in files:
        matches = load_csv(path)
        store.upsert_matches(matches)
        imported += len(matches)
        print(f"{path.name}: {len(matches)} matches")
    print(f"imported {imported} matches into {settings.db_path}")

    all_matches = [m for m in store.list_matches() if m.status.is_finished()]
    elo = build_elo(all_matches)
    top = sorted(elo.items(), key=lambda item: item[1], reverse=True)[:8]
    print("Elo leaders (team id -> rating):")
    for team_id, rating in top:
        print(f"  {team_id}: {rating:.1f}")

    predictor = Predictor()
    features = FeatureService(store)
    y_true: list[int] = []
    y_pred: list[list[float]] = []
    for match in all_matches[-40:]:
        if match.score.home is None or match.score.away is None:
            continue
        feats = features.build(match)
        probs = predictor.predict(match, feats)
        if match.score.home > match.score.away:
            y_true.append(0)
        elif match.score.home == match.score.away:
            y_true.append(1)
        else:
            y_true.append(2)
        y_pred.append([probs.home, probs.draw, probs.away])
    if y_true:
        loss = log_loss(y_true, y_pred, labels=[0, 1, 2])
        print(f"log_loss on last {len(y_true)} matches: {loss:.3f}")


if __name__ == "__main__":
    main()
