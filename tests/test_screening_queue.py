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


async def test_extraction_queue_is_the_full_text_included_pool(
    dispatcher, local_identity
):
    p = await dispatcher.call(
        "projects.create",
        {
            "name": "T2",
            "slug": "t2",
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

    # Include both at title/abstract; then include one and exclude one at
    # full text: extraction must offer only the full-text include.
    for c in ta:
        await dispatcher.call(
            "screening.decision",
            {
                "project_id": pid,
                "cluster_id": c["id"],
                "stage": "title_abstract",
                "decision": "include",
            },
        )
    await dispatcher.call(
        "screening.decision",
        {
            "project_id": pid,
            "cluster_id": ta[0]["id"],
            "stage": "full_text",
            "decision": "include",
        },
    )
    await dispatcher.call(
        "screening.decision",
        {
            "project_id": pid,
            "cluster_id": ta[1]["id"],
            "stage": "full_text",
            "decision": "exclude",
            "exclusion_code": "OFF_TOPIC",
        },
    )
    pool = (
        await dispatcher.call(
            "screening.queue", {"project_id": pid, "stage": "extraction"}
        )
    )["clusters"]
    assert [c["id"] for c in pool] == [ta[0]["id"]]


async def test_rob_resave_updates_tool_label(dispatcher, local_identity):
    p = await dispatcher.call(
        "projects.create",
        {
            "name": "T3",
            "slug": "t3",
            "field_config_id": "general__custom",
            "branch_choices": {"primary_design": "rct"},
        },
    )
    pid = p["id"]
    await dispatcher.call(
        "searches.run",
        {"project_id": pid, "database": "ris_import", "query": "u", "payload": _RIS},
    )
    await dispatcher.call("dedup.run", {"project_id": pid})
    clusters = (await dispatcher.call("dedup.clusters.list", {"project_id": pid}))["clusters"]
    cid = clusters[0]["id"]

    saved = await dispatcher.call(
        "rob.save",
        {
            "project_id": pid,
            "cluster_id": cid,
            "judgements": {"randomization": {"judgement": "low"}},
        },
    )
    assert saved["tool"] == "RoB_2"

    # The project pivots to a prognostic design (branch choices can change
    # via a statefile merge); a re-save must relabel the row for the tool
    # its judgements were validated against.
    import uuid as uuid_mod

    from prismapi.db.base import get_sessionmaker
    from prismapi.db.models import Project

    Session = get_sessionmaker()
    async with Session() as session:
        proj = await session.get(Project, uuid_mod.UUID(pid))
        proj.branch_choices = {"primary_design": "prognostic"}
        await session.commit()
    saved = await dispatcher.call(
        "rob.save",
        {
            "project_id": pid,
            "cluster_id": cid,
            "judgements": {"participation": {"judgement": "low"}},
        },
    )
    assert saved["tool"] == "QUIPS"
