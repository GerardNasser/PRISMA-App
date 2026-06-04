"""Search-catalog + RIS import RPC tests."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_catalog(dispatcher):
    a = await dispatcher.call("searches.adapters")
    ids = {x["id"] for x in a["adapters"]}
    assert {"pubmed", "openalex", "crossref", "ris_import"} <= ids
    f = await dispatcher.call("searches.filters")
    fids = {x["id"] for x in f["filters"]}
    assert "hooijmans_pubmed_animal" in fids
    assert "cochrane_rct_pubmed" in fids


@pytest.mark.asyncio
async def test_pairwise(dispatcher):
    body = await dispatcher.call(
        "searches.pairwise_matrix",
        {
            "groups": [
                ["16S gene", "16S rRNA"],
                ["plant wall", "green wall"],
                ["indoor air"],
            ]
        },
    )
    assert len(body["pairs"]) == 3
    assert body["pairs"][0][0].startswith('"16S gene"')


@pytest.mark.asyncio
async def test_ris_import_persists(dispatcher, local_identity):
    p = await dispatcher.call(
        "projects.create",
        {
            "name": "T",
            "slug": "t",
            "field_config_id": "social__economics",
            "branch_choices": {},
        },
    )
    pid = p["id"]
    ris = """\
TY  - JOUR
TI  - Test article one
AU  - Smith, J
PY  - 2023
DO  - 10.1000/test.1
ER  -

TY  - JOUR
TI  - Test article two
AU  - Lee, K
PY  - 2024
DO  - 10.1000/test.2
ER  -
"""
    r = await dispatcher.call(
        "searches.run",
        {"project_id": pid, "database": "ris_import", "query": "RIS upload", "payload": ris},
    )
    assert r["status"] == "completed"
    assert r["hit_count"] == 2

    recs = await dispatcher.call(
        "searches.records", {"project_id": pid, "search_id": r["id"]}
    )
    titles = {x["title"] for x in recs["records"]}
    assert titles == {"Test article one", "Test article two"}
