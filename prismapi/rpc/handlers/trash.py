"""Trash RPC handlers (Layer-2 safety).

Project-level soft_delete / restore live in projects.py. Generic per-entity
soft_delete + restore + list + empty live here.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from prismapi.rpc.dispatcher import rpc
from prismapi.rpc.errors import VALIDATION, RpcError
from prismapi.services.trash import (
    empty_trash,
    list_trash,
    restore,
    soft_delete,
)


class TrashAction(BaseModel):
    entity_type: str
    entity_id: str


@rpc("trash.soft_delete")
async def soft_delete_endpoint(
    params: TrashAction, session: AsyncSession, identity_id: uuid.UUID
) -> dict:
    try:
        row = await soft_delete(
            session,
            entity_type=params.entity_type,
            entity_id=uuid.UUID(params.entity_id),
            actor_identity_id=identity_id,
        )
    except ValueError as exc:
        raise RpcError(VALIDATION, str(exc)) from exc
    return {"id": str(row.id), "deleted_at": row.deleted_at.isoformat() if row.deleted_at else None}


@rpc("trash.restore")
async def restore_endpoint(
    params: TrashAction, session: AsyncSession, identity_id: uuid.UUID
) -> dict:
    try:
        row = await restore(
            session,
            entity_type=params.entity_type,
            entity_id=uuid.UUID(params.entity_id),
            actor_identity_id=identity_id,
        )
    except ValueError as exc:
        raise RpcError(VALIDATION, str(exc)) from exc
    return {"id": str(row.id), "deleted_at": None}


class TrashList(BaseModel):
    project_id: str | None = None


@rpc("trash.list")
async def list_endpoint(
    params: TrashList, session: AsyncSession, identity_id: uuid.UUID
) -> dict:
    pid = uuid.UUID(params.project_id) if params.project_id else None
    return await list_trash(session, project_id=pid)


class TrashEmpty(BaseModel):
    confirm: str  # must equal "DELETE"
    project_id: str | None = None
    age_only: bool = False


@rpc("trash.empty")
async def empty_endpoint(
    params: TrashEmpty, session: AsyncSession, identity_id: uuid.UUID
) -> dict:
    if params.confirm != "DELETE":
        raise RpcError(VALIDATION, "Type DELETE to confirm trash emptying")
    pid = uuid.UUID(params.project_id) if params.project_id else None
    deleted = await empty_trash(
        session,
        actor_identity_id=identity_id,
        age_only=params.age_only,
        project_id=pid,
    )
    return {"deleted": deleted}
