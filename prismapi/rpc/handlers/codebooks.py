"""Codebook RPC handlers (versioned, like protocols)."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from prismapi.db.models import Codebook, CodebookRule, Project, ProjectMember
from prismapi.rpc.dispatcher import rpc
from prismapi.rpc.errors import NOT_FOUND, RpcError
from prismapi.services.audit import record_audit


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


class CodebookRuleIn(BaseModel):
    code: str = Field(min_length=1, max_length=80)
    direction: str = Field(pattern=r"^(include|exclude|flag)$")
    category: str | None = None
    rationale: str = Field(min_length=1)
    examples: list[str] = Field(default_factory=list)


class CodebookSave(BaseModel):
    project_id: str
    notes: str | None = None
    rules: list[CodebookRuleIn]


def _codebook_out(cb: Codebook) -> dict:
    return {
        "id": str(cb.id),
        "project_id": str(cb.project_id),
        "version": cb.version,
        "notes": cb.notes,
        "rules": [
            {
                "id": str(r.id),
                "code": r.code,
                "direction": r.direction,
                "category": r.category,
                "rationale": r.rationale,
                "examples": r.examples,
            }
            for r in cb.rules
        ],
        "created_at": cb.created_at.isoformat(),
    }


@rpc("codebooks.save")
async def save(params: CodebookSave, session: AsyncSession, identity_id: uuid.UUID) -> dict:
    project = await _assert_member(session, uuid.UUID(params.project_id), identity_id)
    latest = await session.scalar(
        select(func.coalesce(func.max(Codebook.version), 0)).where(
            Codebook.project_id == project.id
        )
    )
    new_version = (latest or 0) + 1
    cb = Codebook(project_id=project.id, version=new_version, notes=params.notes)
    session.add(cb)
    await session.flush()
    for r in params.rules:
        session.add(
            CodebookRule(
                codebook_id=cb.id,
                code=r.code,
                direction=r.direction,
                category=r.category,
                rationale=r.rationale,
                examples=r.examples,
            )
        )
    await record_audit(
        session,
        project_id=project.id,
        actor_identity_id=identity_id,
        action="codebook.save",
        entity_type="codebook",
        entity_id=str(cb.id),
        payload={"version": new_version, "n_rules": len(params.rules)},
    )
    await session.commit()
    await session.refresh(cb)
    return _codebook_out(cb)


class CodebookGet(BaseModel):
    project_id: str


@rpc("codebooks.latest")
async def latest(
    params: CodebookGet, session: AsyncSession, identity_id: uuid.UUID
) -> dict | None:
    project = await _assert_member(session, uuid.UUID(params.project_id), identity_id)
    cb = await session.scalar(
        select(Codebook)
        .where(Codebook.project_id == project.id, Codebook.deleted_at.is_(None))
        .order_by(Codebook.version.desc())
    )
    return _codebook_out(cb) if cb else None


@rpc("codebooks.versions")
async def versions(
    params: CodebookGet, session: AsyncSession, identity_id: uuid.UUID
) -> dict:
    project = await _assert_member(session, uuid.UUID(params.project_id), identity_id)
    rows = await session.execute(
        select(Codebook)
        .where(Codebook.project_id == project.id)
        .order_by(Codebook.version.asc())
    )
    return {"versions": [_codebook_out(cb) for cb in rows.scalars().all()]}
