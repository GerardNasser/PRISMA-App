"""Screening + IRR RPC handlers."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from prismapi.db.models import Project, ProjectMember, ScreeningDecision
from prismapi.rpc.dispatcher import rpc
from prismapi.rpc.errors import NOT_FOUND, RpcError
from prismapi.services.screening import (
    compute_irr,
    resolve_conflict,
    upsert_decision,
)


async def _assert_member(
    session: AsyncSession, project_id: uuid.UUID, identity_id: uuid.UUID
) -> Project:
    project = await session.get(Project, project_id)
    if project is None:
        raise RpcError(NOT_FOUND, "Project not found")
    if project.owner_identity_id == identity_id:
        return project
    member = await session.scalar(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.identity_id == identity_id,
        )
    )
    if member is None:
        raise RpcError(NOT_FOUND, "Project not found")
    return project


class DecisionIn(BaseModel):
    project_id: str
    cluster_id: str
    stage: str = Field(pattern=r"^(title_abstract|full_text)$")
    decision: str = Field(pattern=r"^(include|exclude|maybe)$")
    exclusion_code: str | None = None
    notes: str | None = None
    confidence: int = Field(default=3, ge=1, le=5)


@rpc("screening.decision")
async def decision(
    params: DecisionIn, session: AsyncSession, identity_id: uuid.UUID
) -> dict:
    project = await _assert_member(session, uuid.UUID(params.project_id), identity_id)
    d = await upsert_decision(
        session,
        project_id=project.id,
        reviewer_id=identity_id,
        cluster_id=uuid.UUID(params.cluster_id),
        stage=params.stage,
        decision=params.decision,
        exclusion_code=params.exclusion_code,
        notes=params.notes,
        confidence=params.confidence,
    )
    return {
        "id": str(d.id),
        "cluster_id": str(d.cluster_id),
        "reviewer_identity_id": str(d.reviewer_identity_id),
        "stage": d.stage,
        "decision": d.decision,
        "exclusion_code": d.exclusion_code,
        "notes": d.notes,
        "confidence": d.confidence,
    }


class IrrIn(BaseModel):
    project_id: str
    stage: str = Field(default="title_abstract", pattern=r"^(title_abstract|full_text)$")


@rpc("screening.irr")
async def irr(params: IrrIn, session: AsyncSession, identity_id: uuid.UUID) -> dict:
    project = await _assert_member(session, uuid.UUID(params.project_id), identity_id)
    return await compute_irr(session, project=project, stage=params.stage)


class ResolveIn(BaseModel):
    project_id: str
    cluster_id: str
    stage: str = Field(pattern=r"^(title_abstract|full_text)$")
    final_decision: str = Field(pattern=r"^(include|exclude)$")
    rationale: str = Field(min_length=1)


@rpc("screening.resolve_conflict")
async def resolve(
    params: ResolveIn, session: AsyncSession, identity_id: uuid.UUID
) -> dict:
    project = await _assert_member(session, uuid.UUID(params.project_id), identity_id)
    r = await resolve_conflict(
        session,
        project_id=project.id,
        arbiter_id=identity_id,
        cluster_id=uuid.UUID(params.cluster_id),
        stage=params.stage,
        final_decision=params.final_decision,
        rationale=params.rationale,
    )
    return {
        "id": str(r.id),
        "cluster_id": str(r.cluster_id),
        "stage": r.stage,
        "final_decision": r.final_decision,
        "rationale": r.rationale,
    }


class DecisionsList(BaseModel):
    project_id: str
    stage: str | None = None


@rpc("screening.decisions.list")
async def decisions_list(
    params: DecisionsList, session: AsyncSession, identity_id: uuid.UUID
) -> dict:
    project = await _assert_member(session, uuid.UUID(params.project_id), identity_id)
    q = select(ScreeningDecision).where(ScreeningDecision.project_id == project.id)
    if params.stage:
        q = q.where(ScreeningDecision.stage == params.stage)
    rows = await session.execute(q.order_by(ScreeningDecision.created_at.asc()))
    return {
        "decisions": [
            {
                "id": str(d.id),
                "cluster_id": str(d.cluster_id),
                "reviewer_identity_id": str(d.reviewer_identity_id),
                "stage": d.stage,
                "decision": d.decision,
                "exclusion_code": d.exclusion_code,
                "notes": d.notes,
                "confidence": d.confidence,
            }
            for d in rows.scalars().all()
        ]
    }


class QueueIn(BaseModel):
    project_id: str
    stage: str = Field(default="title_abstract", pattern=r"^(title_abstract|full_text)$")
    limit: int = 1000
    offset: int = 0


@rpc("screening.queue")
async def queue(
    params: QueueIn, session: AsyncSession, identity_id: uuid.UUID
) -> dict:
    """Clusters eligible for screening at a stage.

    Title/abstract screens every cluster; full text screens only clusters
    whose final title/abstract decision was include or maybe.
    """
    from prismapi.db.models import Record, RecordCluster
    from prismapi.rpc.handlers.dedup import _canonical_out, _cluster_out
    from prismapi.services.phase_completion import full_text_pool_ids

    project = await _assert_member(session, uuid.UUID(params.project_id), identity_id)
    q = select(RecordCluster).where(RecordCluster.project_id == project.id)
    if params.stage == "full_text":
        pool = await full_text_pool_ids(session, project.id)
        if not pool:
            return {"clusters": []}
        q = q.where(RecordCluster.id.in_(pool))
    rows = await session.execute(
        q.order_by(RecordCluster.size.desc(), RecordCluster.created_at.asc())
        .offset(params.offset)
        .limit(params.limit)
    )
    clusters = list(rows.scalars().all())
    canonical_ids = [c.canonical_record_id for c in clusters]
    canonical_map = {}
    if canonical_ids:
        rec_rows = await session.execute(select(Record).where(Record.id.in_(canonical_ids)))
        canonical_map = {r.id: r for r in rec_rows.scalars().all()}
    out = []
    for c in clusters:
        d = _cluster_out(c)
        d["canonical"] = _canonical_out(canonical_map.get(c.canonical_record_id))
        out.append(d)
    return {"clusters": out}
