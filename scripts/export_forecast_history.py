#!/usr/bin/env python3
"""Export forecast_history and its calibration summary to CSV (VKR §3.3). No live API."""

from __future__ import annotations

from football_prognoz.config import EXPORTS_DIR, load_settings
from football_prognoz.data.store import SQLiteStore
from football_prognoz.models.predictor import MODEL_VERSION
from football_prognoz.services.calibration import (
    calibration,
    export_calibration_csv,
    export_csv,
)


def main() -> None:
    store = SQLiteStore(load_settings().db_path)
    records = store.list_forecast_records()
    history_path = EXPORTS_DIR / "forecast_history.csv"
    summary_path = EXPORTS_DIR / "forecast_calibration.csv"
    rows = export_csv(records, history_path)
    report = calibration([r for r in records if r.model_version == MODEL_VERSION], MODEL_VERSION)
    export_calibration_csv(report, summary_path)
    print(f"{rows} rows -> {history_path}")
    print(f"summary -> {summary_path}")
    if report.evaluated:
        print(
            f"evaluated={report.evaluated} accuracy={report.accuracy:.3f} "
            f"brier={report.brier:.4f} log_loss={report.log_loss:.4f}"
        )
    else:
        print("no finished pre-match forecasts yet")


if __name__ == "__main__":
    main()
