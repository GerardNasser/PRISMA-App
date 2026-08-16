"""Projects RPC handlers — ported from the Phase-1 router."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from prismapi.db.base import utcnow
from prismapi.db.models import Project, ProjectMember, Protocol
from prismapi.fields.loader import field_registry
from prismapi.rpc.dispatcher import rpc
from prismapi.rpc.errors import CONFLICT, NOT_FOUND, VALIDATION, RpcError
from prismapi.services.audit import record_audit


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    slug: str = Field(min_length=1, max_length=100, pattern=r"^[a-z0-9-]+$")
    description: str | None = None
    field_config_id: str
    branch_choices: dict = Field(default_factory=dict)


def _project_out(p: Project) -> dict:
    return {
        "id": str(p.id),
        "name": p.name,
        "slug": p.slug,
        "description": p.description,
        "field_config_id": p.field_config_id,
        "field_config_version": p.field_config_version,
        "branch_choices": p.branch_choices,
        "owner_identity_id": str(p.owner_identity_id),
        "deleted_at": p.deleted_at.isoformat() if p.deleted_at else None,
        "created_at": p.created_at.isoformat(),
        "updated_at": p.updated_at.isoformat(),
    }


@rpc("projects.create")
async def create(
    params: ProjectCreate, session: AsyncSession, identity_id: uuid.UUID
) -> dict:
    cfg = field_registry.by_id(params.field_config_id)
    if cfg is None:
        raise RpcError(VALIDATION, f"Unknown field config: {params.field_config_id}")
    required_keys = {
        b["key"] for b in cfg.data.get("branch_choices", []) if b.get("required", True)
    }
    missing = required_keys - set(params.branch_choices.keys())
    if missing:
        raise RpcError(
            VALIDATION,
            "Missing required branch_choices",
            {"missing": sorted(missing)},
        )
    existing = await session.scalar(select(Project).where(Project.slug == params.slug))
    if existing is not None:
        raise RpcError(CONFLICT, "Slug already taken")
    project = Project(
        name=params.name,
        slug=params.slug,
        description=params.description,
        owner_identity_id=identity_id,
        field_config_id=cfg.id,
        field_config_version=cfg.version,
        branch_choices=params.branch_choices,
    )
    session.add(project)
    await session.flush()
    session.add(ProjectMember(project_id=project.id, identity_id=identity_id, role="owner"))
    await record_audit(
        session,
        project_id=project.id,
        actor_identity_id=identity_id,
        action="project.create",
        entity_type="project",
        entity_id=str(project.id),
        payload={"field_config_id": cfg.id, "version": cfg.version},
    )
    await session.commit()
    await session.refresh(project)
    return _project_out(project)


class ProjectsList(BaseModel):
    include_trash: bool = False


@rpc("projects.list")
async def list_(
    params: ProjectsList, session: AsyncSession, identity_id: uuid.UUID
) -> dict:
    q = (
        select(Project)
        .join(ProjectMember, ProjectMember.project_id == Project.id)
        .where(ProjectMember.identity_id == identity_id)
    )
    if not params.include_trash:
        q = q.where(Project.deleted_at.is_(None))
    rows = await session.execute(q.order_by(Project.created_at.desc()))
    return {"projects": [_project_out(p) for p in rows.scalars().all()]}


class ProjectGet(BaseModel):
    project_id: str


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
        raise RpcError(NOT_FOUND, "Project not found")  # don't leak existence
    return project


@rpc("projects.get")
async def get(
    params: ProjectGet, session: AsyncSession, identity_id: uuid.UUID
) -> dict:
    project = await _assert_member(session, uuid.UUID(params.project_id), identity_id)
    return _project_out(project)


class ProjectTrash(BaseModel):
    project_id: str


@rpc("projects.soft_delete")
async def soft_delete(
    params: ProjectTrash, session: AsyncSession, identity_id: uuid.UUID
) -> dict:
    project = await _assert_member(session, uuid.UUID(params.project_id), identity_id)
    if project.deleted_at is not None:
        return _project_out(project)
    project.deleted_at = utcnow()
    await record_audit(
        session,
        project_id=project.id,
        actor_identity_id=identity_id,
        action="project.soft_delete",
        entity_type="project",
        entity_id=str(project.id),
        payload={},
    )
    await session.commit()
    await session.refresh(project)
    return _project_out(project)


@rpc("projects.restore")
async def restore(
    params: ProjectTrash, session: AsyncSession, identity_id: uuid.UUID
) -> dict:
    project = await _assert_member(session, uuid.UUID(params.project_id), identity_id)
    project.deleted_at = None
    await record_audit(
        session,
        project_id=project.id,
        actor_identity_id=identity_id,
        action="project.restore",
        entity_type="project",
        entity_id=str(project.id),
        payload={},
    )
    await session.commit()
    await session.refresh(project)
    return _project_out(project)


# ---- protocol ----

class PicoIn(BaseModel):
    P: str | None = None
    I: str | None = None
    C: str | None = None
    O: str | None = None
    T: str | None = None
    S: str | None = None


class ReviewerConfigIn(BaseModel):
    n_reviewers: int = Field(default=2, ge=1, le=20)
    alpha_threshold: float = Field(default=0.67, ge=0.0, le=1.0)
    kappa_threshold: float = Field(default=0.6, ge=0.0, le=1.0)
    conflict_strategy: str = Field(
        default="third_reviewer",
        pattern=r"^(third_reviewer|discussion|lead_arbiter)$",
    )


class ProtocolUpsert(BaseModel):
    project_id: str
    title: str = Field(min_length=1, max_length=500)
    background: str | None = None
    objectives: str | None = None
    research_questions: str | None = None
    pico: PicoIn = Field(default_factory=PicoIn)
    eligibility_criteria: dict = Field(default_factory=dict)
    search_strategy_notes: str | None = None
    registration_registry: str | None = None
    registration_id: str | None = None
    registration_url: str | None = None
    registration_status: str | None = None
    notes: str | None = None
    reviewer_config: ReviewerConfigIn = Field(default_factory=ReviewerConfigIn)


def _protocol_out(p: Protocol) -> dict:
    return {
        "id": str(p.id),
        "project_id": str(p.project_id),
        "version": p.version,
        "title": p.title,
        "background": p.background,
        "objectives": p.objectives,
        "research_questions": p.research_questions,
        "pico": p.pico,
        "eligibility_criteria": p.eligibility_criteria,
        "search_strategy_notes": p.search_strategy_notes,
        "registration_registry": p.registration_registry,
        "registration_id": p.registration_id,
        "registration_url": p.registration_url,
        "registration_status": p.registration_status,
        "notes": p.notes,
        "reviewer_config": p.reviewer_config or {},
        "created_at": p.created_at.isoformat(),
    }


@rpc("protocols.save")
async def protocols_save(
    params: ProtocolUpsert, session: AsyncSession, identity_id: uuid.UUID
) -> dict:
    project = await _assert_member(session, uuid.UUID(params.project_id), identity_id)
    latest = await session.scalar(
        select(func.coalesce(func.max(Protocol.version), 0)).where(
            Protocol.project_id == project.id
        )
    )
    new_version = (latest or 0) + 1
    cfg = field_registry.by_id(project.field_config_id)
    snapshot = cfg.data if cfg is not None else {}
    protocol = Protocol(
        project_id=project.id,
        version=new_version,
        title=params.title,
        background=params.background,
        objectives=params.objectives,
        research_questions=params.research_questions,
        pico=params.pico.model_dump(),
        eligibility_criteria=params.eligibility_criteria,
        search_strategy_notes=params.search_strategy_notes,
        registration_registry=params.registration_registry,
        registration_id=params.registration_id,
        registration_url=params.registration_url,
        registration_status=params.registration_status,
        notes=params.notes,
        snapshot_field_config=snapshot,
        reviewer_config=params.reviewer_config.model_dump(),
    )
    session.add(protocol)
    await record_audit(
        session,
        project_id=project.id,
        actor_identity_id=identity_id,
        action="protocol.save",
        entity_type="protocol",
        entity_id=str(protocol.id),
        payload={"version": new_version},
    )
    await session.commit()
    await session.refresh(protocol)
    return _protocol_out(protocol)


class ProtocolGet(BaseModel):
    project_id: str


@rpc("protocols.latest")
async def protocols_latest(
    params: ProtocolGet, session: AsyncSession, identity_id: uuid.UUID
) -> dict | None:
    project = await _assert_member(session, uuid.UUID(params.project_id), identity_id)
    p = await session.scalar(
        select(Protocol)
        .where(Protocol.project_id == project.id, Protocol.deleted_at.is_(None))
        .order_by(Protocol.version.desc())
    )
    return _protocol_out(p) if p else None


@rpc("protocols.versions")
async def protocols_versions(
    params: ProtocolGet, session: AsyncSession, identity_id: uuid.UUID
) -> dict:
    project = await _assert_member(session, uuid.UUID(params.project_id), identity_id)
    rows = await session.execute(
        select(Protocol)
        .where(Protocol.project_id == project.id)
        .order_by(Protocol.version.asc())
    )
    return {"versions": [_protocol_out(p) for p in rows.scalars().all()]}
