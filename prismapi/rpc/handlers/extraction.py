"""Extraction + RoB RPC handlers."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from prismapi.db.models import Extraction, Project, ProjectMember, RoBAssessment
from prismapi.fields.loader import field_registry
from prismapi.rpc.dispatcher import rpc
from prismapi.rpc.errors import CONFLICT, NOT_FOUND, VALIDATION, RpcError
from prismapi.services.extraction import (
    resolve_rob_spec,
    upsert_extraction,
    upsert_rob,
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


class TemplateGet(BaseModel):
    project_id: str


@rpc("extraction.template")
async def template(
    params: TemplateGet, session: AsyncSession, identity_id: uuid.UUID
) -> dict:
    project = await _assert_member(session, uuid.UUID(params.project_id), identity_id)
    cfg = field_registry.by_id(project.field_config_id)
    if cfg is None:
        raise RpcError(NOT_FOUND, "Project field config not loaded")
    return cfg.data["extraction_template"]


class ExtractionIn(BaseModel):
    project_id: str
    cluster_id: str
    payload: dict
    status: str = Field(default="draft", pattern=r"^(draft|submitted)$")
    notes: str | None = None


@rpc("extraction.save")
async def save(
    params: ExtractionIn, session: AsyncSession, identity_id: uuid.UUID
) -> dict:
    project = await _assert_member(session, uuid.UUID(params.project_id), identity_id)
    try:
        e = await upsert_extraction(
            session,
            project=project,
            reviewer_id=identity_id,
            cluster_id=uuid.UUID(params.cluster_id),
            payload=params.payload,
            status=params.status,
            notes=params.notes,
        )
    except ValueError as exc:
        raise RpcError(VALIDATION, str(exc)) from exc
    return {
        "id": str(e.id),
        "cluster_id": str(e.cluster_id),
        "reviewer_identity_id": str(e.reviewer_identity_id),
        "template_base": e.template_base,
        "payload": e.payload,
        "status": e.status,
        "notes": e.notes,
    }


class ExtractionList(BaseModel):
    project_id: str


@rpc("extraction.list")
async def list_(
    params: ExtractionList, session: AsyncSession, identity_id: uuid.UUID
) -> dict:
    project = await _assert_member(session, uuid.UUID(params.project_id), identity_id)
    rows = await session.execute(
        select(Extraction)
        .where(Extraction.project_id == project.id, Extraction.deleted_at.is_(None))
        .order_by(Extraction.created_at.asc())
    )
    return {
        "extractions": [
            {
                "id": str(e.id),
                "cluster_id": str(e.cluster_id),
                "reviewer_identity_id": str(e.reviewer_identity_id),
                "template_base": e.template_base,
                "payload": e.payload,
                "status": e.status,
                "notes": e.notes,
            }
            for e in rows.scalars().all()
        ]
    }


class RoBTool(BaseModel):
    project_id: str


@rpc("rob.tool")
async def rob_tool(
    params: RoBTool, session: AsyncSession, identity_id: uuid.UUID
) -> dict:
    project = await _assert_member(session, uuid.UUID(params.project_id), identity_id)
    cfg = field_registry.by_id(project.field_config_id)
    if cfg is None:
        raise RpcError(NOT_FOUND, "Project field config not loaded")
    if not cfg.data.get("modules", {}).get("risk_of_bias", True):
        raise RpcError(CONFLICT, "Risk-of-bias module is disabled for this project")
    return resolve_rob_spec(cfg)


class RoBSave(BaseModel):
    project_id: str
    cluster_id: str
    judgements: dict
    overall: str | None = None
    notes: str | None = None


@rpc("rob.save")
async def rob_save(
    params: RoBSave, session: AsyncSession, identity_id: uuid.UUID
) -> dict:
    project = await _assert_member(session, uuid.UUID(params.project_id), identity_id)
    try:
        r = await upsert_rob(
            session,
            project=project,
            reviewer_id=identity_id,
            cluster_id=uuid.UUID(params.cluster_id),
            judgements=params.judgements,
            overall=params.overall,
            notes=params.notes,
        )
    except ValueError as exc:
        raise RpcError(VALIDATION, str(exc)) from exc
    return {
        "id": str(r.id),
        "cluster_id": str(r.cluster_id),
        "reviewer_identity_id": str(r.reviewer_identity_id),
        "tool": r.tool,
        "judgements": r.judgements,
        "overall": r.overall,
        "notes": r.notes,
    }


class RoBList(BaseModel):
    project_id: str


@rpc("rob.list")
async def rob_list(
    params: RoBList, session: AsyncSession, identity_id: uuid.UUID
) -> dict:
    project = await _assert_member(session, uuid.UUID(params.project_id), identity_id)
    rows = await session.execute(
        select(RoBAssessment)
        .where(RoBAssessment.project_id == project.id, RoBAssessment.deleted_at.is_(None))
        .order_by(RoBAssessment.created_at.asc())
    )
    return {
        "rob": [
            {
                "id": str(r.id),
                "cluster_id": str(r.cluster_id),
                "reviewer_identity_id": str(r.reviewer_identity_id),
                "tool": r.tool,
                "judgements": r.judgements,
                "overall": r.overall,
                "notes": r.notes,
            }
            for r in rows.scalars().all()
        ]
    }
