#!/usr/bin/env python3
"""Import local CSVs into a separate training SQLite and print Elo leaders (no live API).

The CSV results use football-data.co.uk team ids, not football-data.org ones, so they
are never written into the app cache (data/cache/prognoz.db); use --db to pick a file.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from sklearn.metrics import log_loss

from football_prognoz.config import APP_HOME, ROOT_DIR, load_settings
from football_prognoz.data.csv_loader import load_csv
from football_prognoz.data.store import SQLiteStore
from football_prognoz.models.elo import build_elo
from football_prognoz.models.predictor import Predictor
from football_prognoz.services.features import FeatureService

DEFAULT_TRAIN_DB = APP_HOME / "data" / "cache" / "train.db"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_TRAIN_DB, help="training SQLite file")
    args = parser.parse_args(argv)
    db_path = args.db.resolve()
    if db_path == load_settings().db_path.resolve():
        parser.error("refusing to import CSV results into the app cache; pick another --db")
    store = SQLiteStore(db_path)
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
    print(f"imported {imported} matches into {db_path}")

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
