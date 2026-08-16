"""Regressions for the search-adapter and dedup-matching fixes."""

from __future__ import annotations

import uuid

import pytest

from prismapi.adapters.filters.library import combine_query, get_filter
from prismapi.adapters.search.ris_import import parse_ris
from prismapi.domain.dedup import RecordSnapshot, cluster_records


def _snap(title, year=2020, doi=None, pmid=None, authors=None, completeness=5):
    return RecordSnapshot(
        id=uuid.uuid4(),
        title=title,
        year=year,
        doi=doi,
        pmid=pmid,
        authors=authors,
        completeness=completeness,
    )


class TestFuzzyMatching:
    def test_subset_title_is_not_merged(self):
        # token_set_ratio scored this pair 100 and merged a paper with its
        # own follow-up publication.
        a = _snap("Effects of mindfulness on stress")
        b = _snap(
            "Effects of mindfulness on stress: a randomized controlled trial "
            "with two-year follow-up"
        )
        decisions = cluster_records([a, b])
        keys = {d.record_id: d.cluster_key for d in decisions}
        assert keys[a.id] != keys[b.id]

    def test_near_identical_titles_still_merge(self):
        a = _snap("Indoor plants modulate the built environment microbiome")
        b = _snap("Indoor plants modulate the built-environment microbiome.", year=2021)
        decisions = cluster_records([a, b])
        keys = {d.record_id: d.cluster_key for d in decisions}
        assert keys[a.id] == keys[b.id]

    def test_transitive_duplicates_via_member_identifiers(self):
        # B joins A's cluster by DOI; C carries only B's PMID. Before member
        # seeding, C could never match because only founders were indexed.
        a = _snap("A study of things", doi="10.1/x")
        b = _snap("A study of things (reprint)", doi="10.1/x", pmid="123456", completeness=4)
        c = _snap("Completely different title", pmid="123456", completeness=3)
        decisions = cluster_records([a, b, c])
        keys = {d.record_id: d.cluster_key for d in decisions}
        assert keys[a.id] == keys[b.id] == keys[c.id]

    def test_short_title_founder_is_labelled_solo(self):
        s = _snap("Short", year=2020)
        decisions = cluster_records([s])
        assert decisions[0].method == "solo"
        assert decisions[0].score == 1.0


class TestRisContinuation:
    def test_continuation_attaches_to_last_seen_tag(self):
        ris = (
            "TY  - JOUR\n"
            "AU  - Smith, J\n"
            "TI  - A title\n"
            "AU  - Jones, Belinda\n"
            "      continued surname line\n"
            "ER  -\n"
        )
        hits = parse_ris(ris.splitlines())
        assert len(hits) == 1
        # The continuation belongs to the second AU, not to TI.
        assert hits[0].title == "A title"
        assert "continued surname line" in (hits[0].authors or "")


class TestFilterCombination:
    def test_not_fragment_becomes_binary_not(self):
        frag = get_filter("exclude_reviews").fragment_for("pubmed")
        combined = combine_query("plants[tiab]", [frag])
        assert combined.startswith("(plants[tiab]) NOT (")
        assert "AND (NOT" not in combined

    def test_crossref_has_no_language_filter(self):
        assert get_filter("english_language").fragment_for("crossref") is None

    def test_openalex_fragments_are_filter_expressions(self):
        assert get_filter("english_language").fragment_for("openalex") == "language:en"
        assert get_filter("exclude_reviews").fragment_for("openalex") == "type:!review"


@pytest.mark.asyncio
async def test_openalex_adapter_sends_filter_param(monkeypatch):
    from prismapi.adapters.search.openalex import OpenAlexAdapter

    captured = {}

    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"results": [], "meta": {}}

    class _Client:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, params=None):
            captured.update(params or {})
            return _Resp()

    monkeypatch.setattr("prismapi.adapters.search.openalex.httpx.AsyncClient", _Client)
    adapter = OpenAlexAdapter()
    async for _ in adapter.search("plants", filters=["language:en", "type:!review"]):
        pass
    assert captured["filter"] == "language:en,type:!review"
    assert "AND" not in captured["search"]
