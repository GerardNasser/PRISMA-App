"""Cluster membership rows must survive merges and trash-empties intact."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from prismapi.db.base import get_sessionmaker
from prismapi.db.models import RecordClusterMember

pytestmark = pytest.mark.asyncio


_RIS_TWO = """\
TY  - JOUR
TI  - Active green walls and the microbiome
AU  - Doe, A
PY  - 2022
DO  - 10.1000/walls.1
ER  -

TY  - JOUR
TI  - A completely different paper about soil
AU  - Lee, K
PY  - 2020
DO  - 10.1000/other.7
ER  -
"""

_RIS_SHARED = """\
TY  - JOUR
TI  - A completely different paper about soil
AU  - Lee, Kim
PY  - 2020
DO  - 10.1000/other.7
ER  -
"""


async def _project(dispatcher):
    p = await dispatcher.call(
        "projects.create",
        {
            "name": "T",
            "slug": "t",
            "field_config_id": "general__custom",
            "branch_choices": {},
        },
    )
    return p["id"]


async def test_manual_merge_keeps_member_rows_physically(dispatcher, local_identity):
    pid = await _project(dispatcher)
    await dispatcher.call(
        "searches.run",
        {"project_id": pid, "database": "ris_import", "query": "u", "payload": _RIS_TWO},
    )
    await dispatcher.call("dedup.run", {"project_id": pid})
    clusters = (await dispatcher.call("dedup.clusters.list", {"project_id": pid}))["clusters"]
    assert len(clusters) == 2

    merged = await dispatcher.call(
        "dedup.manual_merge",
        {
            "project_id": pid,
            "cluster_ids": [clusters[0]["id"], clusters[1]["id"]],
            "canonical_cluster_id": clusters[0]["id"],
        },
    )
    assert merged["size"] == 2

    # The re-pointed member row previously fell to the losing cluster's
    # delete-orphan cascade: size said 2 but only 1 physical row remained.
    Session = get_sessionmaker()
    async with Session() as session:
        rows = (
            await session.execute(
                select(RecordClusterMember).where(
                    RecordClusterMember.cluster_id == uuid.UUID(clusters[0]["id"])
                )
            )
        ).scalars().all()
    assert len(rows) == 2


async def test_trash_empty_updates_clusters_losing_a_member(dispatcher, local_identity):
    pid = await _project(dispatcher)
    await dispatcher.call(
        "searches.run",
        {"project_id": pid, "database": "ris_import", "query": "a", "payload": _RIS_TWO},
    )
    s2 = await dispatcher.call(
        "searches.run",
        {"project_id": pid, "database": "ris_import", "query": "b", "payload": _RIS_SHARED},
    )
    await dispatcher.call("dedup.run", {"project_id": pid})
    clusters = (await dispatcher.call("dedup.clusters.list", {"project_id": pid}))["clusters"]
    shared = next(c for c in clusters if c["size"] == 2)

    # Trash search B: the shared cluster keeps its canonical (from search A)
    # but loses B's member. Its bookkeeping previously kept the ghost.
    await dispatcher.call(
        "trash.soft_delete", {"entity_type": "search", "entity_id": s2["id"]}
    )
    await dispatcher.call("trash.empty", {"confirm": "DELETE", "project_id": pid})

    clusters = (await dispatcher.call("dedup.clusters.list", {"project_id": pid}))["clusters"]
    updated = next(c for c in clusters if c["id"] == shared["id"])
    assert updated["size"] == 1
    assert len(updated["members"]) == 1
    assert updated["canonical"] is not None
