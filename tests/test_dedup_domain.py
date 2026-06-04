"""Pure-function tests for the dedup domain logic."""

from __future__ import annotations

import uuid

from prismapi.domain.dedup import (
    RecordSnapshot,
    cluster_records,
    normalize_doi,
    normalize_pmid,
    normalize_title,
)


def _u() -> uuid.UUID:
    return uuid.uuid4()


def test_normalize_doi_strips_prefix_and_lowercases():
    assert normalize_doi("https://doi.org/10.1038/S41591-021-01552-X") == "10.1038/s41591-021-01552-x"
    assert normalize_doi("dx.doi.org/10.1000/foo") == "10.1000/foo"
    assert normalize_doi("") is None


def test_normalize_pmid_digits_only():
    assert normalize_pmid("PMID: 12345678") == "12345678"
    assert normalize_pmid(" 12345678 ") == "12345678"


def test_normalize_title_punctuation_and_unicode():
    assert normalize_title("Sálter et al.: A study, 2014?") == "salter et al a study 2014"


def test_doi_match_collapses_records():
    a = RecordSnapshot(_u(), "Plant microbiome study", 2022, "10.1000/X", None, "Smith J", completeness=6)
    b = RecordSnapshot(_u(), "Plant Microbiome Study", 2022, "https://doi.org/10.1000/X", None, "Smith, J", completeness=4)
    decisions = cluster_records([a, b])
    keys = {d.cluster_key for d in decisions}
    assert len(keys) == 1
    methods = {d.method for d in decisions}
    assert methods == {"doi"}


def test_pmid_match_when_doi_missing():
    a = RecordSnapshot(_u(), "Indoor plants 16S", 2020, None, "999999", "Doe", completeness=5)
    b = RecordSnapshot(_u(), "Different title entirely", 2020, None, "999999", "Doe", completeness=3)
    decisions = cluster_records([a, b])
    assert len({d.cluster_key for d in decisions}) == 1


def test_title_year_norm_match():
    a = RecordSnapshot(_u(), "A long enough title for matching", 2021, None, None, "Lee K", completeness=4)
    b = RecordSnapshot(_u(), "A long enough title for matching.", 2021, None, None, "Lee, K.", completeness=4)
    decisions = cluster_records([a, b])
    keys = {d.cluster_key for d in decisions}
    assert len(keys) == 1
    assert any(d.method == "title_year_norm" for d in decisions)


def test_fuzzy_title_with_author_overlap_and_year_within_tolerance():
    a = RecordSnapshot(
        _u(),
        "Active green walls modulate built-environment microbial communities",
        2022,
        None,
        None,
        "Smith J; Doe A",
        completeness=5,
    )
    b = RecordSnapshot(
        _u(),
        "Active green walls modulate built environment microbial community",
        2023,
        None,
        None,
        "Smith, John; Doe, Alex",
        completeness=4,
    )
    decisions = cluster_records([a, b])
    methods = {d.method for d in decisions}
    assert "fuzzy_title" in methods
    keys = {d.cluster_key for d in decisions}
    assert len(keys) == 1


def test_distinct_records_stay_separate():
    a = RecordSnapshot(_u(), "Microbiome of office green walls", 2022, None, None, "A", 4)
    b = RecordSnapshot(_u(), "Mass spectrometry of soil", 2022, None, None, "B", 4)
    decisions = cluster_records([a, b])
    keys = {d.cluster_key for d in decisions}
    assert len(keys) == 2
