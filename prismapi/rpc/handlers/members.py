"""RPC handlers for per-project member (rater) enrollment."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from prismapi.db.models.identity import Identity
from prismapi.db.models.project import ProjectMember
from prismapi.rpc.dispatcher import rpc
from prismapi.services import members as members_service
from prismapi.services.audit import record_audit


class EnrollIn(BaseModel):
    project_id: uuid.UUID
    last_name: str = Field(..., min_length=1, max_length=200)
    orcid: str | None = None
    email: str | None = None
    institution: str | None = None
    role: str = Field("reviewer")


class ListIn(BaseModel):
    project_id: uuid.UUID


class RemoveIn(BaseModel):
    project_id: uuid.UUID
    member_id: uuid.UUID


def _serialise_identity(i: Identity) -> dict:
    return {
        "id": str(i.id),
        "last_name": i.last_name,
        "orcid": i.orcid,
        "email": i.email,
        "institution": i.institution,
        "display_name": i.display_name,
        "is_local": i.is_local,
    }


def _serialise_member(m: ProjectMember) -> dict:
    return {
        "id": str(m.id),
        "project_id": str(m.project_id),
        "identity_id": str(m.identity_id),
        "role": m.role,
        "identity": _serialise_identity(m.identity),
    }


@rpc("members.enroll")
async def enroll(
    params: EnrollIn, session: AsyncSession, identity_id: uuid.UUID
) -> dict:
    member = await members_service.enroll_member(
        session,
        project_id=params.project_id,
        last_name=params.last_name,
        orcid=params.orcid,
        email=params.email,
        institution=params.institution,
        role=params.role,
    )
    await record_audit(
        session,
        project_id=params.project_id,
        actor_identity_id=identity_id,
        action="members.enroll",
        entity_type="project_member",
        entity_id=str(member.id),
        payload={
            "role": params.role,
            "identity_id": str(member.identity_id),
        },
    )
    await session.commit()
    await session.refresh(member, ["identity"])
    return _serialise_member(member)


@rpc("members.list")
async def list_(params: ListIn, session: AsyncSession) -> list[dict]:
    rows = await members_service.list_members(session, project_id=params.project_id)
    # Hydrate identity relationship for serialisation.
    out: list[dict] = []
    for m in rows:
        await session.refresh(m, ["identity"])
        out.append(_serialise_member(m))
    return out


@rpc("members.remove")
async def remove(
    params: RemoveIn, session: AsyncSession, identity_id: uuid.UUID
) -> dict:
    await members_service.remove_member(
        session, project_id=params.project_id, member_id=params.member_id,
    )
    await record_audit(
        session,
        project_id=params.project_id,
        actor_identity_id=identity_id,
        action="members.remove",
        entity_type="project_member",
        entity_id=str(params.member_id),
        payload={},
    )
    await session.commit()
    return {"ok": True}
