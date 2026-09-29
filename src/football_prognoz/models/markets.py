"""Markets table from the model's score matrix (docs/FORECAST.md, «Таблица ставок»).

1. Independent Poisson grid 0…MAX_GOALS on the model's λ (Elo-shifted, as in
   `Predictor`), normalised to 1.
2. The grid is re-weighted so that its home / draw / away sums equal the final 1X2
   probabilities of the model (the 65/35 Poisson + Elo blend). Every goal market is
   therefore consistent with the 1X2 the user sees, and complementary selections
   (over / under, yes / no) add up to exactly 100 %.
3. Corners, yellow cards, fouls and penalties: Poisson on the sum of team averages
   from API-Football match statistics, only when those averages exist.

No factor outside the model is applied. The LLM never touches these numbers.
"""

from __future__ import annotations

import math
from collections.abc import Callable

from football_prognoz.domain.markets import (
    NOTE_NO_KEY,
    Market,
    MarketsTable,
    TeamSetPieces,
)
from football_prognoz.domain.prediction import Probabilities
from football_prognoz.models.predictor import MAX_GOALS, poisson_pmf

Matrix = list[list[float]]

TOTAL_LINES = (0.5, 1.5, 2.5, 3.5, 4.5)
TEAM_TOTAL_LINES = (0.5, 1.5, 2.5)
HANDICAP_LINES = (-1.5, -1.0, -0.5, 0.5, 1.0, 1.5)
CORNER_LINES = (8.5, 9.5, 10.5)
CARD_LINES = (3.5, 4.5, 5.5)
FOUL_LINES = (20.5, 23.5, 26.5)
TOP_SCORES = 5
MIN_SET_PIECE_MATCHES = 2

METHOD = (
    "Сетка счетов Пуассона 0–8 на ожидаемых голах модели (Elo + Пуассон), "
    "перевзвешенная к итоговым 1X2; угловые, карточки, фолы и пенальти — "
    "Пуассон на средних API-Football за последние матчи."
)


def score_matrix(lam_home: float, lam_away: float, max_goals: int = MAX_GOALS) -> Matrix:
    cells = [
        [poisson_pmf(i, lam_home) * poisson_pmf(j, lam_away) for j in range(max_goals + 1)]
        for i in range(max_goals + 1)
    ]
    total = sum(map(sum, cells))
    if total <= 0:
        return cells
    return [[p / total for p in row] for row in cells]


def outcome_sums(matrix: Matrix) -> tuple[float, float, float]:
    home = draw = away = 0.0
    for i, row in enumerate(matrix):
        for j, p in enumerate(row):
            if i > j:
                home += p
            elif i == j:
                draw += p
            else:
                away += p
    return home, draw, away


def calibrate_to_1x2(matrix: Matrix, target: Probabilities) -> Matrix:
    """Scale home-win / draw / away-win cells so their sums equal `target`."""
    target = target.normalized()
    home, draw, away = outcome_sums(matrix)
    scale = (
        target.home / home if home > 1e-12 else 1.0,
        target.draw / draw if draw > 1e-12 else 1.0,
        target.away / away if away > 1e-12 else 1.0,
    )
    out = [
        [p * (scale[0] if i > j else scale[1] if i == j else scale[2]) for j, p in enumerate(row)]
        for i, row in enumerate(matrix)
    ]
    total = sum(map(sum, out))
    return [[p / total for p in row] for row in out] if total > 0 else out


def _mass(matrix: Matrix, predicate: Callable[[int, int], bool]) -> float:
    return sum(p for i, row in enumerate(matrix) for j, p in enumerate(row) if predicate(i, j))


def market_confidence(probability: float, sample: int) -> str:
    """Documented rule: small sample → low; ≥70 % with ≥10 matches → high; ≥55 % → medium."""
    if sample < 4:
        return "low"
    if probability >= 0.70 and sample >= 10:
        return "high"
    if probability >= 0.55:
        return "medium"
    return "low"


def _set_piece_confidence(probability: float, sample: int) -> str:
    # Averages over a handful of matches: never "high".
    if sample < 3:
        return "low"
    return "medium" if probability >= 0.55 else "low"


def _fmt(line: float) -> str:
    return f"{line:g}"


def _signed(line: float) -> str:
    """ASCII signed line for keys: "+0.5", "-1"."""
    return f"{line:+g}"


def _shown(line: float) -> str:
    """Signed line for labels, with a typographic minus: "+0.5", "−1"."""
    return _signed(line).replace("-", "−")


class _Builder:
    def __init__(self, sample: int) -> None:
        self.sample = sample
        self.rows: list[Market] = []

    def add(
        self,
        key: str,
        group: str,
        label: str,
        win: float,
        popularity: int,
        *,
        push: float = 0.0,
        confidence: str | None = None,
    ) -> None:
        win = min(1.0, max(0.0, win))
        push = min(1.0 - win, max(0.0, push))
        settled = 1.0 - push
        eff = win / settled if settled > 1e-12 else 0.0
        self.rows.append(
            Market(
                key=key,
                group=group,
                label=label,
                win=win,
                push=push,
                popularity=popularity,
                confidence=confidence or market_confidence(eff, self.sample),
            )
        )

    def missing(self, key: str, group: str, label: str, popularity: int, note: str) -> None:
        self.rows.append(Market(key, group, label, None, popularity=popularity, note=note))


def _goal_markets(b: _Builder, m: Matrix) -> None:
    p1, px, p2 = outcome_sums(m)
    b.add("1x2_1", "1x2", "П1 — победа хозяев", p1, 1)
    b.add("1x2_x", "1x2", "Х — ничья", px, 1)
    b.add("1x2_2", "1x2", "П2 — победа гостей", p2, 1)

    for line in TOTAL_LINES:
        over = _mass(m, lambda i, j, ln=line: i + j > ln)
        pop = 2 if line == 2.5 else 5
        b.add(f"total_over_{_fmt(line)}", "totals", f"Тотал больше {_fmt(line)}", over, pop)
        b.add(f"total_under_{_fmt(line)}", "totals", f"Тотал меньше {_fmt(line)}", 1 - over, pop)

    yes = _mass(m, lambda i, j: i > 0 and j > 0)
    b.add("btts_yes", "btts", "Обе забьют — да", yes, 3)
    b.add("btts_no", "btts", "Обе забьют — нет", 1 - yes, 3)

    b.add("dc_1x", "double_chance", "1X — хозяева не проиграют", p1 + px, 4)
    b.add("dc_x2", "double_chance", "X2 — гости не проиграют", px + p2, 4)
    b.add("dc_12", "double_chance", "12 — кто-то победит", p1 + p2, 4)

    b.add("dnb_1", "dnb", "П1, ничья — возврат", p1, 7, push=px)
    b.add("dnb_2", "dnb", "П2, ничья — возврат", p2, 7, push=px)

    for side, sign, name in (("1", 1, "хозяева"), ("2", -1, "гости")):
        for line in HANDICAP_LINES:

            def margin(i: int, j: int, s: int = sign, ln: float = line) -> float:
                return s * (i - j) + ln

            win = _mass(m, lambda i, j, f=margin: f(i, j) > 1e-9)
            push = _mass(m, lambda i, j, f=margin: abs(f(i, j)) <= 1e-9)
            pop = 6 if abs(line) == 0.5 else 8
            b.add(
                f"ah_{side}_{_signed(line)}",
                "handicap",
                f"Фора {side} ({_shown(line)}) — {name}",
                win,
                pop,
                push=push,
            )

    for side, sign, name in (("1", 1, "хозяев"), ("2", -1, "гостей")):
        tt = (lambda i, j: i) if sign == 1 else (lambda i, j: j)
        for line in TEAM_TOTAL_LINES:
            over = _mass(m, lambda i, j, g=tt, ln=line: g(i, j) > ln)
            ln = _fmt(line)
            b.add(f"tt{side}_over_{ln}", "team_totals", f"ИТ {name} больше {ln}", over, 9)
            b.add(f"tt{side}_under_{ln}", "team_totals", f"ИТ {name} меньше {ln}", 1 - over, 9)

    # European (3-way) handicap: the "draw with handicap" is its own outcome.
    for fav, sign, other in (("1", 1, "2"), ("2", -1, "1")):
        d = (lambda i, j: i - j) if sign == 1 else (lambda i, j: j - i)
        b.add(
            f"eh_{fav}_-1",
            "euro_handicap",
            f"П{fav} (−1)",
            _mass(m, lambda i, j, f=d: f(i, j) >= 2),
            10,
        )
        b.add(
            f"eh_x_{fav}-1",
            "euro_handicap",
            f"Х (фора −1 у {'хозяев' if fav == '1' else 'гостей'})",
            _mass(m, lambda i, j, f=d: f(i, j) == 1),
            10,
        )
        b.add(
            f"eh_{other}_+1_vs{fav}",
            "euro_handicap",
            f"П{other} (+1)",
            _mass(m, lambda i, j, f=d: f(i, j) <= 0),
            10,
        )

    b.add(
        "wtn_1", "win_to_nil", "Хозяева победят всухую", _mass(m, lambda i, j: i > 0 and j == 0), 11
    )
    b.add(
        "wtn_2", "win_to_nil", "Гости победят всухую", _mass(m, lambda i, j: j > 0 and i == 0), 11
    )

    cells = sorted(
        ((p, i, j) for i, row in enumerate(m) for j, p in enumerate(row)),
        key=lambda c: (-c[0], c[1] + c[2]),
    )
    for p, i, j in cells[:TOP_SCORES]:
        b.add(f"cs_{i}-{j}", "correct_score", f"Точный счёт {i}:{j}", p, 12, confidence="low")


def poisson_over(line: float, lam: float) -> float:
    """P(X > line) for X ~ Poisson(lam); line is a half-number."""
    k_max = math.floor(line)
    cdf = sum(poisson_pmf(k, lam) for k in range(k_max + 1))
    return min(1.0, max(0.0, 1.0 - cdf))


def _pair_lambda(home: TeamSetPieces, away: TeamSetPieces, attr: str) -> float | None:
    """(home_for + away_against)/2 + (away_for + home_against)/2, like K1/K2 for goals."""
    hf, ha = getattr(home, f"{attr}_for"), getattr(home, f"{attr}_against")
    af, aa = getattr(away, f"{attr}_for"), getattr(away, f"{attr}_against")
    if None in (hf, ha, af, aa):
        return None
    return (hf + aa) / 2 + (af + ha) / 2


SET_PIECE_SPECS = (
    ("corners", "corners", "Угловые", CORNER_LINES, 13),
    ("cards", "yellow", "Жёлтые карточки", CARD_LINES, 14),
    ("fouls", "fouls", "Фолы", FOUL_LINES, 15),
)


def _set_piece_markets(
    b: _Builder,
    pieces: tuple[TeamSetPieces, TeamSetPieces] | None,
    note: str,
) -> None:
    home, away = pieces if pieces else (None, None)
    for group, attr, title, lines, pop in SET_PIECE_SPECS:
        lam = None
        sample = 0
        if home is not None and away is not None:
            sample = min(home.matches, away.matches)
            if sample >= MIN_SET_PIECE_MATCHES:
                lam = _pair_lambda(home, away, attr)
        for line in lines:
            ln = _fmt(line)
            if lam is None:
                reason = note if pieces is None else NOTE_MISSING_LOCAL
                b.missing(f"{group}_over_{ln}", group, f"{title}: больше {ln}", pop, reason)
                b.missing(f"{group}_under_{ln}", group, f"{title}: меньше {ln}", pop, reason)
                continue
            over = poisson_over(line, lam)
            b.add(
                f"{group}_over_{ln}",
                group,
                f"{title}: больше {ln}",
                over,
                pop,
                confidence=_set_piece_confidence(over, sample),
            )
            b.add(
                f"{group}_under_{ln}",
                group,
                f"{title}: меньше {ln}",
                1 - over,
                pop,
                confidence=_set_piece_confidence(1 - over, sample),
            )
    lam_pen = None
    pen_sample = 0
    if home is not None and away is not None:
        pen_sample = min(home.penalty_matches, away.penalty_matches)
        if pen_sample >= MIN_SET_PIECE_MATCHES:
            lam_pen = _pair_lambda(home, away, "penalties")
    if lam_pen is None:
        reason = note if pieces is None else NOTE_MISSING_LOCAL
        b.missing("penalty_yes", "penalty", "Будет пенальти — да", 16, reason)
        b.missing("penalty_no", "penalty", "Будет пенальти — нет", 16, reason)
    else:
        yes = 1.0 - math.exp(-lam_pen)
        b.add(
            "penalty_yes",
            "penalty",
            "Будет пенальти — да",
            yes,
            16,
            confidence=_set_piece_confidence(yes, pen_sample),
        )
        b.add(
            "penalty_no",
            "penalty",
            "Будет пенальти — нет",
            1 - yes,
            16,
            confidence=_set_piece_confidence(1 - yes, pen_sample),
        )


NOTE_MISSING_LOCAL = "мало матчей со статистикой API-Football"


def build_markets(
    lam_home: float,
    lam_away: float,
    probabilities: Probabilities,
    *,
    sample_matches: int,
    set_pieces: tuple[TeamSetPieces, TeamSetPieces] | None = None,
    set_pieces_note: str = NOTE_NO_KEY,
    sources: tuple[str, ...] = (),
) -> MarketsTable:
    matrix = calibrate_to_1x2(score_matrix(lam_home, lam_away), probabilities)
    builder = _Builder(sample_matches)
    _goal_markets(builder, matrix)
    _set_piece_markets(builder, set_pieces, set_pieces_note)
    return MarketsTable(
        markets=tuple(builder.rows),
        lambda_home=lam_home,
        lambda_away=lam_away,
        method=METHOD,
        sources=sources,
    )
