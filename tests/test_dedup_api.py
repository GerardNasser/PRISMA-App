"""Dedup pipeline + manual merge RPC tests."""

from __future__ import annotations

import pytest


def _ris_two_dupes() -> str:
    return """\
TY  - JOUR
TI  - Indoor plants modulate microbiome
AU  - Smith, J
PY  - 2023
DO  - 10.1000/test.42
ER  -

TY  - JOUR
TI  - Indoor Plants Modulate Microbiome
AU  - Smith, John
PY  - 2023
DO  - https://doi.org/10.1000/test.42
ER  -

TY  - JOUR
TI  - A completely different paper about soil
AU  - Lee, K
PY  - 2020
DO  - 10.1000/other.7
ER  -
"""


@pytest.mark.asyncio
async def test_dedup_collapses_doi_duplicates(dispatcher, local_identity):
    p = await dispatcher.call(
        "projects.create",
        {
            "name": "T",
            "slug": "t",
            "field_config_id": "health__omics",
            "branch_choices": {},
        },
    )
    pid = p["id"]
    r = await dispatcher.call(
        "searches.run",
        {
            "project_id": pid,
            "database": "ris_import",
            "query": "u",
            "payload": _ris_two_dupes(),
        },
    )
    assert r["hit_count"] == 3
    summary = await dispatcher.call("dedup.run", {"project_id": pid})
    assert summary["input"] == 3
    assert summary["output"] == 2
    assert summary["duplicates_removed"] == 1
    clusters = await dispatcher.call("dedup.clusters.list", {"project_id": pid})
    sizes = sorted(c["size"] for c in clusters["clusters"])
    assert sizes == [1, 2]


@pytest.mark.asyncio
async def test_manual_merge(dispatcher, local_identity):
    p = await dispatcher.call(
        "projects.create",
        {
            "name": "T",
            "slug": "t",
            "field_config_id": "health__omics",
            "branch_choices": {},
        },
    )
    pid = p["id"]
    ris = """\
TY  - JOUR
TI  - Active green walls and microbiome
AU  - Doe, A
PY  - 2022
DO  - 10.1000/a
ER  -

TY  - JOUR
TI  - Distinct title that should not auto-merge
AU  - Zheng, X
PY  - 2019
DO  - 10.1000/b
ER  -
"""
    await dispatcher.call(
        "searches.run",
        {"project_id": pid, "database": "ris_import", "query": "x", "payload": ris},
    )
    await dispatcher.call("dedup.run", {"project_id": pid})
    clusters = (await dispatcher.call("dedup.clusters.list", {"project_id": pid}))["clusters"]
    assert len(clusters) == 2
    cids = [c["id"] for c in clusters]
    merged = await dispatcher.call(
        "dedup.manual_merge",
        {
            "project_id": pid,
            "cluster_ids": cids,
            "canonical_cluster_id": cids[0],
            "notes": "Confirmed same study",
        },
    )
    assert merged["size"] == 2
    after = (await dispatcher.call("dedup.clusters.list", {"project_id": pid}))["clusters"]
    assert len(after) == 1
