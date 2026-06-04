"""Screening + IRR RPC tests (with a foreign identity to exercise two-reviewer α)."""

from __future__ import annotations

import uuid

import pytest

from prismapi.db.base import get_sessionmaker
from prismapi.db.models import Identity, ProjectMember


async def _seed_foreign_reviewer(project_id: str) -> uuid.UUID:
    Session = get_sessionmaker()
    async with Session() as session:
        foreign = Identity(
            last_name="Rittmeyer",
            email="rachel@example.edu",
            display_name="Rittmeyer (rachel@example.edu)",
            is_local=False,
        )
        session.add(foreign)
        await session.flush()
        session.add(
            ProjectMember(
                project_id=uuid.UUID(project_id), identity_id=foreign.id, role="reviewer"
            )
        )
        await session.commit()
        return foreign.id


async def _make_project_with_clusters(dispatcher, n: int = 6) -> tuple[str, list[str]]:
    p = await dispatcher.call(
        "projects.create",
        {
            "name": "Two-reviewer demo",
            "slug": "tr",
            "field_config_id": "health__omics",
            "branch_choices": {},
        },
    )
    pid = p["id"]
    ris = "\n".join(
        f"TY  - JOUR\nTI  - Article {i}\nAU  - Author {i}\nPY  - 2020\nDO  - 10.1000/x.{i}\nER  -"
        for i in range(n)
    )
    await dispatcher.call(
        "searches.run",
        {"project_id": pid, "database": "ris_import", "query": "x", "payload": ris},
    )
    await dispatcher.call("dedup.run", {"project_id": pid})
    clusters = (await dispatcher.call("dedup.clusters.list", {"project_id": pid}))["clusters"]
    return pid, [c["id"] for c in clusters]


@pytest.mark.asyncio
async def test_single_reviewer_irr_returns_nulls(dispatcher, local_identity):
    pid, clusters = await _make_project_with_clusters(dispatcher, n=4)
    for cid, d in zip(clusters, ["include", "include", "exclude", "exclude"]):
        await dispatcher.call(
            "screening.decision",
            {"project_id": pid, "cluster_id": cid, "stage": "title_abstract", "decision": d},
        )
    irr = await dispatcher.call(
        "screening.irr", {"project_id": pid, "stage": "title_abstract"}
    )
    assert irr["n_reviewers"] == 1
    assert irr["alpha_binary"] is None


@pytest.mark.asyncio
async def test_two_reviewer_irr_and_conflict_resolve(dispatcher, local_identity):
    pid, clusters = await _make_project_with_clusters(dispatcher, n=6)

    local_decisions = ["include", "include", "exclude", "exclude", "include", "exclude"]
    for cid, d in zip(clusters, local_decisions):
        await dispatcher.call(
            "screening.decision",
            {"project_id": pid, "cluster_id": cid, "stage": "title_abstract", "decision": d},
        )

    foreign_id = await _seed_foreign_reviewer(pid)
    from prismapi.db.models import ScreeningDecision

    Session = get_sessionmaker()
    foreign_decisions = ["include", "include", "exclude", "exclude", "include", "include"]
    async with Session() as session:
        for cid, d in zip(clusters, foreign_decisions):
            session.add(
                ScreeningDecision(
                    project_id=uuid.UUID(pid),
                    cluster_id=uuid.UUID(cid),
                    reviewer_identity_id=foreign_id,
                    stage="title_abstract",
                    decision=d,
                )
            )
        await session.commit()

    irr = await dispatcher.call(
        "screening.irr", {"project_id": pid, "stage": "title_abstract"}
    )
    assert irr["n_reviewers"] == 2
    assert irr["n_items"] == 6
    assert abs(irr["percent_agreement"] - 5 / 6) < 0.001
    assert irr["alpha_binary"] is not None
    assert len(irr["conflicts"]) == 1

    cid = irr["conflicts"][0]
    res = await dispatcher.call(
        "screening.resolve_conflict",
        {
            "project_id": pid,
            "cluster_id": cid,
            "stage": "title_abstract",
            "final_decision": "exclude",
            "rationale": "Wrong setting on full read",
        },
    )
    assert res["final_decision"] == "exclude"
