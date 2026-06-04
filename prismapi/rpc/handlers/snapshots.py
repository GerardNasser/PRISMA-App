"""Snapshot RPC handlers (Layer-4 safety)."""

from __future__ import annotations

import uuid

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from prismapi.db.models import Project, ProjectMember
from prismapi.rpc.dispatcher import rpc
from prismapi.rpc.errors import NOT_FOUND, RpcError
from prismapi.services.snapshot import (
    delete_snapshot,
    list_snapshots,
    take_snapshot,
)


async def _assert_member(
    session: AsyncSession, project_id: uuid.UUID, identity_id: uuid.UUID
) -> Project:
    from sqlalchemy import select

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


class SnapshotCreate(BaseModel):
    project_id: str
    label: str | None = None
    kind: str = "manual"


@rpc("snapshots.create")
async def create(
    params: SnapshotCreate, session: AsyncSession, identity_id: uuid.UUID
) -> dict:
    project = await _assert_member(session, uuid.UUID(params.project_id), identity_id)
    snap = await take_snapshot(
        session,
        project=project,
        kind=params.kind,
        label=params.label,
        actor_identity_id=identity_id,
    )
    return {
        "id": str(snap.id),
        "project_id": str(snap.project_id),
        "kind": snap.kind,
        "label": snap.label,
        "relative_path": snap.relative_path,
        "size_bytes": snap.size_bytes,
        "sha256": snap.sha256,
        "is_pinned": snap.is_pinned,
        "created_at": snap.created_at.isoformat(),
    }


class SnapshotList(BaseModel):
    project_id: str


@rpc("snapshots.list")
async def list_(
    params: SnapshotList, session: AsyncSession, identity_id: uuid.UUID
) -> dict:
    project = await _assert_member(session, uuid.UUID(params.project_id), identity_id)
    rows = await list_snapshots(session, project_id=project.id)
    return {
        "snapshots": [
            {
                "id": str(s.id),
                "kind": s.kind,
                "label": s.label,
                "relative_path": s.relative_path,
                "size_bytes": s.size_bytes,
                "sha256": s.sha256,
                "is_pinned": s.is_pinned,
                "created_at": s.created_at.isoformat(),
            }
            for s in rows
        ]
    }


class SnapshotDelete(BaseModel):
    snapshot_id: str


@rpc("snapshots.delete")
async def delete(
    params: SnapshotDelete, session: AsyncSession, identity_id: uuid.UUID
) -> dict:
    await delete_snapshot(
        session,
        snapshot_id=uuid.UUID(params.snapshot_id),
        actor_identity_id=identity_id,
    )
    return {"deleted": params.snapshot_id}
