from football_prognoz.ui.theme import (
    BREAKPOINT_MEDIUM,
    BREAKPOINT_SPLIT,
    BREAKPOINT_WIDE,
    fact_columns,
    fact_runs,
    grid_extent,
    league_runs,
    match_extent,
    match_runs,
    use_rail,
    use_split,
)


def test_grid_extent_dense_breakpoints() -> None:
    assert grid_extent(BREAKPOINT_WIDE) == 280
    assert grid_extent(1440) == 280
    assert grid_extent(BREAKPOINT_MEDIUM) == 360
    assert grid_extent(1100) == 360
    assert grid_extent(BREAKPOINT_MEDIUM - 1) == 720
    assert grid_extent(800) == 720


def test_league_and_match_runs() -> None:
    assert league_runs(1440) == 4
    assert league_runs(1100) == 2
    assert league_runs(800) == 1
    assert match_runs(1440) == 2
    assert match_runs(1100) == 1
    assert match_extent(1440) == 280
    assert match_extent(1100) == 720


def test_fact_runs() -> None:
    assert fact_runs(1440) == 4
    assert fact_runs(1100) == 2
    assert fact_runs(800) == 1


def test_fact_columns_fits_split_pane() -> None:
    assert fact_columns(1440) == 4
    assert fact_columns(720) == 2
    assert fact_columns(400) == 2
    assert fact_columns(399) == 1


def test_split_threshold() -> None:
    assert use_split(BREAKPOINT_SPLIT) is True
    assert use_split(BREAKPOINT_SPLIT - 1) is False
    assert use_split(1440) is True
    assert use_rail(BREAKPOINT_WIDE) is True
    assert use_rail(BREAKPOINT_WIDE - 1) is False
    assert use_rail(800) is False
