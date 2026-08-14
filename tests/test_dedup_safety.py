"""Dedup must not silently destroy screening, extraction, or RoB work."""

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


async def _project_with_decisions(dispatcher):
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
    await dispatcher.call(
        "searches.run",
        {"project_id": pid, "database": "ris_import", "query": "u", "payload": _RIS},
    )
    await dispatcher.call("dedup.run", {"project_id": pid})
    clusters = (await dispatcher.call("dedup.clusters.list", {"project_id": pid}))["clusters"]
    for c in clusters:
        await dispatcher.call(
            "screening.decision",
            {
                "project_id": pid,
                "cluster_id": c["id"],
                "stage": "title_abstract",
                "decision": "include",
            },
        )
    return pid, clusters


async def test_dedup_rerun_refused_once_screening_exists(dispatcher, local_identity):
    pid, _ = await _project_with_decisions(dispatcher)
    with pytest.raises(RpcError) as exc:
        await dispatcher.call("dedup.run", {"project_id": pid})
    assert exc.value.data["would_delete"]["screening_decisions"] == 2

    decisions = await dispatcher.call(
        "screening.decisions.list", {"project_id": pid, "stage": "title_abstract"}
    )
    assert len(decisions["decisions"]) == 2


async def test_forced_dedup_rerun_takes_snapshot_first(dispatcher, local_identity):
    pid, _ = await _project_with_decisions(dispatcher)
    summary = await dispatcher.call("dedup.run", {"project_id": pid, "force": True})
    assert summary["input"] == 2

    snaps = await dispatcher.call("snapshots.list", {"project_id": pid})
    kinds = [s["kind"] for s in snaps["snapshots"]]
    assert "pre_dedup" in kinds


async def test_manual_merge_preserves_screening_decisions(dispatcher, local_identity):
    pid, clusters = await _project_with_decisions(dispatcher)
    assert len(clusters) == 2
    keep, lose = clusters[0], clusters[1]

    merged = await dispatcher.call(
        "dedup.manual_merge",
        {
            "project_id": pid,
            "cluster_ids": [keep["id"], lose["id"]],
            "canonical_cluster_id": keep["id"],
        },
    )
    assert merged["id"] == keep["id"]

    # The decision that lived on the losing cluster collides with the
    # reviewer's existing decision on the canonical cluster, so exactly one
    # decision survives — nothing is cascade-deleted at the DB level.
    decisions = await dispatcher.call(
        "screening.decisions.list", {"project_id": pid, "stage": "title_abstract"}
    )
    assert len(decisions["decisions"]) == 1
    assert decisions["decisions"][0]["cluster_id"] == keep["id"]
