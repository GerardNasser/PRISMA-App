"""screening.queue: title/abstract sees everything, full text sees the pool."""

from __future__ import annotations

import pytest

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


async def test_full_text_queue_is_the_advanced_pool(dispatcher, local_identity):
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

    ta = (
        await dispatcher.call(
            "screening.queue", {"project_id": pid, "stage": "title_abstract"}
        )
    )["clusters"]
    assert len(ta) == 2

    ft = (
        await dispatcher.call(
            "screening.queue", {"project_id": pid, "stage": "full_text"}
        )
    )["clusters"]
    assert ft == []

    # The single rater includes one cluster and excludes the other: only the
    # included one advances to full text.
    await dispatcher.call(
        "screening.decision",
        {
            "project_id": pid,
            "cluster_id": ta[0]["id"],
            "stage": "title_abstract",
            "decision": "include",
        },
    )
    await dispatcher.call(
        "screening.decision",
        {
            "project_id": pid,
            "cluster_id": ta[1]["id"],
            "stage": "title_abstract",
            "decision": "exclude",
        },
    )
    ft = (
        await dispatcher.call(
            "screening.queue", {"project_id": pid, "stage": "full_text"}
        )
    )["clusters"]
    assert [c["id"] for c in ft] == [ta[0]["id"]]
