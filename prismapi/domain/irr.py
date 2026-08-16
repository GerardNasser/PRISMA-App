"""Inter-rater reliability metrics.

Implementations are pure-Python (numpy only) for testability:
- Krippendorff's α for nominal / ordinal / interval levels.
- Cohen's κ for two raters, categorical.
- Fleiss' κ for multiple raters, categorical.
- Percent agreement.

Krippendorff reference: Krippendorff K. 2018 *Content Analysis: An
Introduction to Its Methodology* 4th ed.; Hayes & Krippendorff 2007 *Comm
Methods and Measures* 1(1):77–89. The implementation uses the coincidence-
matrix formulation, which handles missing values and any number of raters.
"""

from __future__ import annotations

from typing import Literal

import numpy as np

Level = Literal["nominal", "ordinal", "interval"]


def percent_agreement(ratings: list[list]) -> float:
    """Fraction of items where all (non-missing) raters chose the same value.

    `ratings[i][j]` = rater j's value for item i (or None for missing).
    Items where fewer than 2 raters labeled are skipped.
    """
    eligible = 0
    agree = 0
    for row in ratings:
        present = [v for v in row if v is not None]
        if len(present) < 2:
            continue
        eligible += 1
        if len(set(present)) == 1:
            agree += 1
    return agree / eligible if eligible else 0.0


def cohens_kappa(a: list, b: list) -> float:
    """Two-rater nominal κ. Missing values must be filtered before calling."""
    if len(a) != len(b):
        raise ValueError("Cohen's κ requires equal-length rater vectors")
    paired = [(x, y) for x, y in zip(a, b, strict=True) if x is not None and y is not None]
    if not paired:
        return 0.0
    categories = sorted({c for pair in paired for c in pair})
    idx = {c: i for i, c in enumerate(categories)}
    k = len(categories)
    matrix = np.zeros((k, k), dtype=float)
    for x, y in paired:
        matrix[idx[x]][idx[y]] += 1
    total = matrix.sum()
    po = np.trace(matrix) / total
    pe = sum(matrix[i].sum() * matrix[:, i].sum() for i in range(k)) / (total * total)
    if pe == 1.0:
        return 1.0
    return float((po - pe) / (1 - pe))


def fleiss_kappa(ratings: list[list]) -> float:
    """Fleiss' κ. Each row is a list of category labels (or None for missing).

    Items where fewer than 2 raters labeled are skipped. All items must have
    the same `n` raters after filtering (Fleiss assumption) — we use the
    minimum `n` across items.
    """
    rows = [[v for v in row if v is not None] for row in ratings]
    rows = [r for r in rows if len(r) >= 2]
    if not rows:
        return 0.0
    n = min(len(r) for r in rows)
    if n < 2:
        return 0.0
    categories = sorted({v for row in rows for v in row})
    cat_idx = {c: i for i, c in enumerate(categories)}
    N = len(rows)
    k = len(categories)
    counts = np.zeros((N, k), dtype=float)
    for i, row in enumerate(rows):
        for v in row[:n]:
            counts[i, cat_idx[v]] += 1
    p_j = counts.sum(axis=0) / (N * n)
    P_i = (np.sum(counts**2, axis=1) - n) / (n * (n - 1))
    P_bar = P_i.mean()
    P_e = float(np.sum(p_j**2))
    if P_e == 1.0:
        return 1.0
    return float((P_bar - P_e) / (1 - P_e))


def _delta_nominal(a: float, b: float) -> float:
    return 0.0 if a == b else 1.0


def _delta_ordinal(a: float, b: float, marginals: dict[float, int]) -> float:
    # Between two ordinal values c and k, Krippendorff's δ²:
    #   (sum_{g=c..k} n_g - (n_c + n_k)/2)²
    if a == b:
        return 0.0
    lo, hi = sorted((a, b))
    keys = sorted(marginals)
    n_c = marginals[lo]
    n_k = marginals[hi]
    between = 0.0
    for g in keys:
        if lo <= g <= hi:
            between += marginals[g]
    diff = between - (n_c + n_k) / 2.0
    return float(diff * diff)


def _delta_interval(a: float, b: float) -> float:
    return float((a - b) ** 2)


def krippendorff_alpha(ratings: list[list], level: Level = "nominal") -> float:
    """Krippendorff's α via the coincidence-matrix formulation.

    `ratings[i][j]` = rater j's value for item i, or None for missing.
    """
    items = [[v for v in row if v is not None] for row in ratings]
    items = [r for r in items if len(r) >= 2]
    if not items:
        return 0.0
    all_values = sorted({v for row in items for v in row})
    if level == "nominal":
        n_total = sum(len(r) for r in items)
        marginals: dict = {v: 0 for v in all_values}
        for row in items:
            for v in row:
                marginals[v] += 1
        D_o_num = 0.0
        D_o_den = 0.0
        for row in items:
            m = len(row)
            if m < 2:
                continue
            counts: dict = {}
            for v in row:
                counts[v] = counts.get(v, 0) + 1
            denom = m - 1
            for v1 in counts:
                for v2 in counts:
                    if v1 == v2:
                        n_c = counts[v1]
                        pairs = n_c * (n_c - 1)
                    else:
                        pairs = counts[v1] * counts[v2]
                    D_o_num += pairs * _delta_nominal(v1, v2) / denom
            D_o_den += m
        D_e_num = 0.0
        for v1 in all_values:
            for v2 in all_values:
                D_e_num += marginals[v1] * marginals[v2] * _delta_nominal(v1, v2)
        D_e_den = n_total * (n_total - 1)
        if D_o_den == 0 or D_e_den == 0:
            return 0.0
        D_o = D_o_num / D_o_den
        D_e = D_e_num / D_e_den
        if D_e == 0:
            return 1.0
        return float(1 - D_o / D_e)

    # ordinal / interval — use numeric values
    numeric_items: list[list[float]] = [[float(v) for v in row] for row in items]
    n_total = sum(len(r) for r in numeric_items)
    marginals_num: dict[float, int] = {}
    for row in numeric_items:
        for v in row:
            marginals_num[v] = marginals_num.get(v, 0) + 1

    def _delta(a: float, b: float) -> float:
        return _delta_interval(a, b) if level == "interval" else _delta_ordinal(a, b, marginals_num)

    D_o_num = 0.0
    D_o_den = 0.0
    for row in numeric_items:
        m = len(row)
        if m < 2:
            continue
        denom = m - 1
        for i in range(m):
            for j in range(m):
                if i == j:
                    continue
                D_o_num += _delta(row[i], row[j]) / denom
        D_o_den += m

    D_e_num = 0.0
    keys = sorted(marginals_num)
    for v1 in keys:
        for v2 in keys:
            D_e_num += marginals_num[v1] * marginals_num[v2] * _delta(v1, v2)
    D_e_den = n_total * (n_total - 1)
    if D_o_den == 0 or D_e_den == 0:
        return 0.0
    D_o = D_o_num / D_o_den
    D_e = D_e_num / D_e_den
    if D_e == 0:
        return 1.0
    return float(1 - D_o / D_e)


def interpret_alpha(alpha: float) -> str:
    """Krippendorff interpretive bands."""
    if alpha >= 0.80:
        return "strong"
    if alpha >= 0.67:
        return "acceptable"
    if alpha > 0:
        return "weak"
    return "no_better_than_chance"
