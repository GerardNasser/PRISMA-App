"""Walk one project through every phase gate and watch each unlock.

These tests exercise prismapi.services.phase_completion.gate_state through the
phases.state RPC, seeding the database directly between calls.
"""

from __future__ import annotations

import uuid

import pytest

from prismapi.db.base import Base, get_engine, get_sessionmaker
from prismapi.db.models import (
    ConflictResolution,
    Extraction,
    Project,
    ProjectMember,
    Protocol,
    Record,
    RecordCluster,
    RoBAssessment,
    ScreeningDecision,
    Search,
)
from prismapi.services.members import upsert_foreign_identity

pytestmark = pytest.mark.asyncio


async def _phases(dispatcher, project_id):
    result = await dispatcher.call("phases.state", {"project_id": project_id})
    return {entry["phase"]: entry for entry in result}


@pytest.fixture
async def seeded(dispatcher, local_identity):
    """Project with two raters, a protocol, one search, two records, two clusters."""
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = get_sessionmaker()
    async with Session() as session:
        owner_id = uuid.UUID(local_identity["id"])
        second = await upsert_foreign_identity(
            session, last_name="Reviewer", orcid=None, email="second@example.edu"
        )
        project = Project(
            name="Walkthrough",
            slug="walkthrough",
            owner_identity_id=owner_id,
            field_config_id="general__custom",
            field_config_version="1.0",
        )
        session.add(project)
        await session.flush()
        session.add_all(
            [
                ProjectMember(project_id=project.id, identity_id=owner_id, role="owner"),
                ProjectMember(project_id=project.id, identity_id=second.id, role="reviewer"),
            ]
        )
        session.add(Protocol(project_id=project.id, version=1, title="P"))
        search = Search(
            project_id=project.id,
            database="ris_import",
            query_string="q",
            status="completed",
        )
        session.add(search)
        await session.flush()
        records = [
            Record(
                project_id=project.id,
                search_id=search.id,
                database="ris_import",
                external_id=f"r{i}",
                title=f"Record {i}",
            )
            for i in range(2)
        ]
        session.add_all(records)
        await session.flush()
        clusters = [
            RecordCluster(
                project_id=project.id,
                canonical_record_id=r.id,
                method="doi",
            )
            for r in records
        ]
        session.add_all(clusters)
        await session.commit()
        return {
            "project_id": str(project.id),
            "raters": [owner_id, second.id],
            "clusters": [c.id for c in clusters],
        }


async def _decide(session, project_id, cluster_id, reviewer_id, stage, decision):
    session.add(
        ScreeningDecision(
            project_id=uuid.UUID(project_id),
            cluster_id=cluster_id,
            reviewer_identity_id=reviewer_id,
            stage=stage,
            decision=decision,
        )
    )


async def test_full_text_locked_until_every_rater_finishes_ta(dispatcher, seeded):
    phases = await _phases(dispatcher, seeded["project_id"])
    assert phases["title_abstract"]["open"] is True
    assert phases["full_text"]["open"] is False
    assert "0/2" in phases["full_text"]["reason"]

    Session = get_sessionmaker()
    async with Session() as session:
        for cluster_id in seeded["clusters"]:
            await _decide(
                session, seeded["project_id"], cluster_id, seeded["raters"][0],
                "title_abstract", "include",
            )
        await session.commit()

    phases = await _phases(dispatcher, seeded["project_id"])
    assert phases["full_text"]["open"] is False
    assert "1/2" in phases["full_text"]["reason"]


async def test_gates_unlock_through_full_workflow(dispatcher, seeded):
    Session = get_sessionmaker()
    project_id = seeded["project_id"]

    # Both raters include both clusters at title/abstract.
    async with Session() as session:
        for cluster_id in seeded["clusters"]:
            for rater in seeded["raters"]:
                await _decide(session, project_id, cluster_id, rater, "title_abstract", "include")
        await session.commit()
    phases = await _phases(dispatcher, project_id)
    assert phases["full_text"]["open"] is True
    assert phases["extraction"]["open"] is False

    # Both raters finish full text.
    async with Session() as session:
        for cluster_id in seeded["clusters"]:
            for rater in seeded["raters"]:
                await _decide(session, project_id, cluster_id, rater, "full_text", "include")
        await session.commit()
    phases = await _phases(dispatcher, project_id)
    assert phases["extraction"]["open"] is True
    assert phases["rob"]["open"] is False

    # One submitted extraction opens risk of bias.
    async with Session() as session:
        session.add(
            Extraction(
                project_id=uuid.UUID(project_id),
                cluster_id=seeded["clusters"][0],
                reviewer_identity_id=seeded["raters"][0],
                template_base="general",
                payload={"design": "rct"},
                status="submitted",
            )
        )
        await session.commit()
    phases = await _phases(dispatcher, project_id)
    assert phases["rob"]["open"] is True
    assert phases["synthesis"]["open"] is False

    # An assessment opens synthesis; report stays locked (no synthesis module).
    async with Session() as session:
        session.add(
            RoBAssessment(
                project_id=uuid.UUID(project_id),
                cluster_id=seeded["clusters"][0],
                reviewer_identity_id=seeded["raters"][0],
                tool="ROBINS_I",
                judgements={"confounding": {"judgement": "low"}},
            )
        )
        await session.commit()
    phases = await _phases(dispatcher, project_id)
    assert phases["synthesis"]["open"] is True
    assert phases["report"]["open"] is False


async def test_conflicted_cluster_blocks_pool_until_resolved(dispatcher, seeded):
    Session = get_sessionmaker()
    project_id = seeded["project_id"]
    disputed, agreed = seeded["clusters"]

    async with Session() as session:
        await _decide(session, project_id, agreed, seeded["raters"][0], "title_abstract", "exclude")
        await _decide(session, project_id, agreed, seeded["raters"][1], "title_abstract", "exclude")
        await _decide(session, project_id, disputed, seeded["raters"][0], "title_abstract", "include")
        await _decide(session, project_id, disputed, seeded["raters"][1], "title_abstract", "exclude")
        await session.commit()

    # TA is done for both raters, but the disputed cluster is unresolved, so
    # nothing has advanced: full text is trivially complete and extraction opens
    # only after the conflict resolution decides the pool.
    phases = await _phases(dispatcher, project_id)
    assert phases["full_text"]["open"] is True

    async with Session() as session:
        session.add(
            ConflictResolution(
                project_id=uuid.UUID(project_id),
                cluster_id=disputed,
                stage="title_abstract",
                arbiter_identity_id=seeded["raters"][0],
                final_decision="include",
                rationale="Arbiter call",
            )
        )
        await session.commit()

    # The disputed cluster now advances, so full text has real work again.
    phases = await _phases(dispatcher, project_id)
    assert phases["extraction"]["open"] is False
    assert "0/2" in phases["extraction"]["reason"]


async def test_soft_deleted_decisions_do_not_count(dispatcher, seeded):
    import datetime

    Session = get_sessionmaker()
    project_id = seeded["project_id"]
    async with Session() as session:
        for cluster_id in seeded["clusters"]:
            for rater in seeded["raters"]:
                await _decide(session, project_id, cluster_id, rater, "title_abstract", "include")
        await session.commit()

    async with Session() as session:
        from sqlalchemy import select

        decision = (await session.scalars(select(ScreeningDecision))).first()
        decision.deleted_at = datetime.datetime.now(datetime.UTC)
        await session.commit()

    phases = await _phases(dispatcher, project_id)
    assert phases["full_text"]["open"] is False
    assert "1/2" in phases["full_text"]["reason"]
