"""Soft-deleted rows must never outrank, mask, or silently absorb live work."""

from __future__ import annotations

import pytest

from prismapi.rpc.errors import RpcError

pytestmark = pytest.mark.asyncio


_RIS = """\
TY  - JOUR
TI  - Indoor plants modulate microbiome
AU  - Smith, J
PY  - 2023
DO  - 10.1000/test.42
ER  -

TY  - JOUR
TI  - A completely different paper about soil
AU  - Lee, K
PY  - 2020
DO  - 10.1000/other.7
ER  -
"""


async def _seed(dispatcher):
    p = await dispatcher.call(
        "projects.create",
        {
            "name": "T",
            "slug": "t",
            "field_config_id": "general__custom",
            "branch_choices": {},
        },
    )
    pid = p["id"]
    await dispatcher.call(
        "searches.run",
        {"project_id": pid, "database": "ris_import", "query": "u", "payload": _RIS},
    )
    await dispatcher.call("dedup.run", {"project_id": pid})
    clusters = (await dispatcher.call("dedup.clusters.list", {"project_id": pid}))["clusters"]
    return pid, clusters


async def _decide(dispatcher, pid, cluster_id, decision="include"):
    return await dispatcher.call(
        "screening.decision",
        {
            "project_id": pid,
            "cluster_id": cluster_id,
            "stage": "title_abstract",
            "decision": decision,
        },
    )


async def test_live_decision_survives_merge_against_tombstone(dispatcher, local_identity):
    pid, clusters = await _seed(dispatcher)
    a, b = clusters[0], clusters[1]

    trashed = await _decide(dispatcher, pid, a["id"], "exclude")
    await dispatcher.call(
        "trash.soft_delete", {"entity_type": "screening", "entity_id": trashed["id"]}
    )
    live = await _decide(dispatcher, pid, b["id"], "include")

    await dispatcher.call(
        "dedup.manual_merge",
        {
            "project_id": pid,
            "cluster_ids": [a["id"], b["id"]],
            "canonical_cluster_id": a["id"],
        },
    )
    decisions = (
        await dispatcher.call(
            "screening.decisions.list", {"project_id": pid, "stage": "title_abstract"}
        )
    )["decisions"]
    # The live include from B must win over A's trashed exclude.
    assert len(decisions) == 1
    assert decisions[0]["id"] == live["id"]
    assert decisions[0]["decision"] == "include"
    assert decisions[0]["cluster_id"] == a["id"]


async def test_dedup_rerun_guard_counts_trashed_work(dispatcher, local_identity):
    pid, clusters = await _seed(dispatcher)
    d = await _decide(dispatcher, pid, clusters[0]["id"])
    await dispatcher.call(
        "trash.soft_delete", {"entity_type": "screening", "entity_id": d["id"]}
    )
    # The only work is in the trash; the cascade would still destroy it.
    with pytest.raises(RpcError) as exc:
        await dispatcher.call("dedup.run", {"project_id": pid})
    assert exc.value.data["would_delete"]["screening_decisions"] == 1


async def test_redeciding_resurrects_a_trashed_decision(dispatcher, local_identity):
    pid, clusters = await _seed(dispatcher)
    cid = clusters[0]["id"]
    d = await _decide(dispatcher, pid, cid, "maybe")
    await dispatcher.call(
        "trash.soft_delete", {"entity_type": "screening", "entity_id": d["id"]}
    )
    # Trashed decisions are hidden from the list...
    listed = (
        await dispatcher.call(
            "screening.decisions.list", {"project_id": pid, "stage": "title_abstract"}
        )
    )["decisions"]
    assert listed == []
    # ...and deciding again produces a live row, not an edit on the tombstone.
    await _decide(dispatcher, pid, cid, "include")
    listed = (
        await dispatcher.call(
            "screening.decisions.list", {"project_id": pid, "stage": "title_abstract"}
        )
    )["decisions"]
    assert len(listed) == 1
    assert listed[0]["decision"] == "include"
    trash = await dispatcher.call("trash.list", {"project_id": pid})
    assert trash["screening"] == []


async def test_irr_ignores_trashed_decisions(dispatcher, local_identity):
    pid, clusters = await _seed(dispatcher)
    d = await _decide(dispatcher, pid, clusters[0]["id"])
    await dispatcher.call(
        "trash.soft_delete", {"entity_type": "screening", "entity_id": d["id"]}
    )
    irr = await dispatcher.call(
        "screening.irr", {"project_id": pid, "stage": "title_abstract"}
    )
    assert irr["n_items"] == 0
