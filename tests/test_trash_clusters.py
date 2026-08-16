"""Emptying trashed searches must survive the cluster canonical-record FK.

Regression for: record_clusters.canonical_record_id is RESTRICT, so
hard-deleting a search whose record anchors a cluster raised a FK error and
rolled back the whole wipe.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio


_RIS_A = """\
TY  - JOUR
TI  - Indoor plants modulate microbiome
AU  - Smith, J
PY  - 2023
DO  - 10.1000/test.42
ER  -
"""

_RIS_B = """\
TY  - JOUR
TI  - Indoor plants modulate microbiome
AU  - Smith, John
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
            "field_config_id": "health__omics",
            "branch_choices": {},
        },
    )
    pid = p["id"]
    s1 = await dispatcher.call(
        "searches.run",
        {"project_id": pid, "database": "ris_import", "query": "a", "payload": _RIS_A},
    )
    s2 = await dispatcher.call(
        "searches.run",
        {"project_id": pid, "database": "ris_import", "query": "b", "payload": _RIS_B},
    )
    await dispatcher.call("dedup.run", {"project_id": pid})
    return pid, s1["id"], s2["id"]


async def test_empty_trash_with_canonical_record_in_trashed_search(
    dispatcher, local_identity
):
    pid, s1, _s2 = await _seed(dispatcher)

    # Search A's record is the canonical of the shared-DOI cluster (imported
    # first). Trash search A and empty: the cluster must be re-pointed to
    # search B's copy, not blow up the wipe.
    await dispatcher.call("trash.soft_delete", {"entity_type": "search", "entity_id": s1})
    result = await dispatcher.call("trash.empty", {"confirm": "DELETE", "project_id": pid})
    assert result["deleted"]["search"] == 1

    clusters = (await dispatcher.call("dedup.clusters.list", {"project_id": pid}))["clusters"]
    assert len(clusters) == 2
    for c in clusters:
        assert c["canonical"] is not None


async def test_empty_trash_deletes_cluster_when_no_member_survives(
    dispatcher, local_identity
):
    pid, s1, s2 = await _seed(dispatcher)

    # Trash both searches: every record dies, so both clusters go too.
    await dispatcher.call("trash.soft_delete", {"entity_type": "search", "entity_id": s1})
    await dispatcher.call("trash.soft_delete", {"entity_type": "search", "entity_id": s2})
    result = await dispatcher.call("trash.empty", {"confirm": "DELETE", "project_id": pid})
    assert result["deleted"]["search"] == 2

    clusters = (await dispatcher.call("dedup.clusters.list", {"project_id": pid}))["clusters"]
    assert clusters == []
