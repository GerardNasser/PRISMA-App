"""Pure-function IRR tests with worked examples.

Krippendorff α reference values are taken from Hayes & Krippendorff 2007 and
the Krippendorff 2018 textbook example.
"""

from __future__ import annotations

from prismapi.domain.irr import (
    cohens_kappa,
    fleiss_kappa,
    interpret_alpha,
    krippendorff_alpha,
    percent_agreement,
)


def test_percent_agreement_basic():
    ratings = [
        ["A", "A"],
        ["A", "B"],
        ["B", "B"],
        ["A", "A"],
    ]
    assert percent_agreement(ratings) == 0.75


def test_cohens_kappa_perfect_agreement():
    assert cohens_kappa(["A", "B", "A", "B"], ["A", "B", "A", "B"]) == 1.0


def test_cohens_kappa_chance_agreement_yields_zero():
    # Equal marginals: both raters say A 50% and B 50%, random matching => κ ≈ 0
    a = ["A", "A", "B", "B"]
    b = ["A", "B", "A", "B"]
    k = cohens_kappa(a, b)
    assert -0.01 < k < 0.01


def test_krippendorff_alpha_perfect():
    ratings = [
        ["A", "A", "A"],
        ["B", "B", "B"],
        ["A", "A", "A"],
    ]
    assert krippendorff_alpha(ratings, "nominal") == 1.0


def test_krippendorff_alpha_no_better_than_chance():
    # Different raters disagree systematically.
    ratings = [
        ["A", "B"],
        ["B", "A"],
        ["A", "B"],
        ["B", "A"],
    ]
    a = krippendorff_alpha(ratings, "nominal")
    assert a <= 0


def test_krippendorff_alpha_hand_computed_two_raters_binary():
    # 4 items, 2 raters, balanced marginals (A=4, B=4):
    # 2 fully agree, 2 fully disagree → hand-computed α = 1 - (0.5)/(4/7) = 0.125
    ratings = [
        ["A", "A"],
        ["B", "B"],
        ["A", "B"],
        ["B", "A"],
    ]
    a = krippendorff_alpha(ratings, "nominal")
    assert abs(a - 0.125) < 0.01


def test_interpret_alpha_bands():
    assert interpret_alpha(0.95) == "strong"
    assert interpret_alpha(0.70) == "acceptable"
    assert interpret_alpha(0.4) == "weak"
    assert interpret_alpha(0.0) == "no_better_than_chance"


def test_fleiss_kappa_perfect():
    ratings = [
        ["A", "A", "A"],
        ["B", "B", "B"],
        ["C", "C", "C"],
    ]
    assert fleiss_kappa(ratings) == 1.0


def test_fleiss_kappa_chance():
    # 3 raters, 2 categories, randomized assignments.
    ratings = [
        ["A", "B", "A"],
        ["B", "A", "B"],
        ["A", "A", "B"],
        ["B", "B", "A"],
    ]
    k = fleiss_kappa(ratings)
    assert k < 0.2
