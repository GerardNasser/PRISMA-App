"""Layer-2 safety: soft-delete + trash + emptying.

Soft-delete sets `deleted_at` on the row(s). Restore clears it. Empty Trash
hard-deletes rows past retention. Hard-delete cascades via SQLAlchemy
relationship `cascade='all, delete-orphan'` for child rows, and via FK
`ondelete='CASCADE'` at the DB level.
"""

from __future__ import annotations

import shutil
import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from prismapi.config import get_settings
from prismapi.db.base import utcnow
from prismapi.db.models import (
    Codebook,
    Extraction,
    Project,
    Protocol,
    Record,
    RecordCluster,
    RecordClusterMember,
    RoBAssessment,
    ScreeningDecision,
    Search,
)
from prismapi.services.audit import record_audit

# Model registry for trash operations.
_TRASHABLE: dict[str, type] = {
    "project": Project,
    "search": Search,
    "screening": ScreeningDecision,
    "extraction": Extraction,
    "rob": RoBAssessment,
    "codebook": Codebook,
    "protocol": Protocol,
}


async def soft_delete(
    session: AsyncSession,
    *,
    entity_type: str,
    entity_id: uuid.UUID,
    actor_identity_id: uuid.UUID | None = None,
) -> Any:
    """Set deleted_at on one row (project, search, decision, ...); commits."""
    model = _TRASHABLE.get(entity_type)
    if model is None:
        raise ValueError(f"Soft-delete not supported for entity: {entity_type}")
    row = await session.get(model, entity_id)
    if row is None:
        raise ValueError(f"{entity_type} not found")
    row.deleted_at = utcnow()
    await record_audit(
        session,
        project_id=getattr(row, "project_id", None) or (row.id if isinstance(row, Project) else None),
        actor_identity_id=actor_identity_id,
        action="trash.soft_delete",
        entity_type=entity_type,
        entity_id=str(entity_id),
        payload={},
    )
    await session.commit()
    await session.refresh(row)
    return row


async def restore(
    session: AsyncSession,
    *,
    entity_type: str,
    entity_id: uuid.UUID,
    actor_identity_id: uuid.UUID | None = None,
) -> Any:
    """Clear deleted_at on one trashed row; commits."""
    model = _TRASHABLE.get(entity_type)
    if model is None:
        raise ValueError(f"Restore not supported for entity: {entity_type}")
    row = await session.get(model, entity_id)
    if row is None:
        raise ValueError(f"{entity_type} not found")
    row.deleted_at = None
    await record_audit(
        session,
        project_id=getattr(row, "project_id", None) or (row.id if isinstance(row, Project) else None),
        actor_identity_id=actor_identity_id,
        action="trash.restore",
        entity_type=entity_type,
        entity_id=str(entity_id),
        payload={},
    )
    await session.commit()
    await session.refresh(row)
    return row


async def list_trash(
    session: AsyncSession,
    *,
    project_id: uuid.UUID | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Return all soft-deleted rows. Scoped to a project if supplied."""
    out: dict[str, list[dict[str, Any]]] = {}
    for name, model in _TRASHABLE.items():
        q = select(model).where(model.deleted_at.is_not(None))
        if project_id is not None and hasattr(model, "project_id") and model is not Project:
            q = q.where(model.project_id == project_id)
        if project_id is not None and model is Project:
            q = q.where(model.id == project_id)
        rows = (await session.execute(q)).scalars().all()
        out[name] = [
            {
                "id": str(r.id),
                "deleted_at": r.deleted_at.isoformat() if r.deleted_at else None,
                "project_id": str(getattr(r, "project_id", r.id)),
                "summary": _summarise(r, name),
            }
            for r in rows
        ]
    return out


def _summarise(row: Any, kind: str) -> str:
    if kind == "project":
        return row.name
    if kind == "search":
        return f"{row.database}: {row.query_string[:80]}"
    if kind == "screening":
        return f"{row.stage}/{row.decision}"
    if kind == "extraction":
        return row.status
    if kind == "rob":
        return row.tool
    if kind == "codebook":
        return f"v{row.version}"
    if kind == "protocol":
        return f"v{row.version}: {row.title[:80]}"
    return str(row.id)


def _record_completeness(r: Record) -> int:
    """Rough completeness score so the richest record becomes canonical."""
    fields = (r.title, r.abstract, r.authors, r.journal, r.year, r.doi, r.pmid)
    return sum(1 for f in fields if f)


async def _detach_clusters_from_searches(
    session: AsyncSession, search_ids: list[uuid.UUID]
) -> None:
    """Prepare clusters for the hard-delete of `search_ids`.

    Deleting a search cascades its records away. Every cluster holding a
    doomed record needs its bookkeeping rewritten — not only clusters whose
    canonical record dies (the RESTRICT FK case), but also clusters that
    merely lose a member, whose `size` and `merge_graph` would otherwise
    keep counting ghosts. Clusters with no surviving member are deleted;
    a replaced canonical is the most complete surviving record.
    """
    if not search_ids:
        return
    doomed_records = set(
        await session.scalars(select(Record.id).where(Record.search_id.in_(search_ids)))
    )
    if not doomed_records:
        return
    affected_ids = set(
        await session.scalars(
            select(RecordClusterMember.cluster_id).where(
                RecordClusterMember.record_id.in_(doomed_records)
            )
        )
    )
    affected_ids |= set(
        await session.scalars(
            select(RecordCluster.id).where(
                RecordCluster.canonical_record_id.in_(doomed_records)
            )
        )
    )
    if not affected_ids:
        return
    clusters = (
        await session.execute(
            select(RecordCluster).where(RecordCluster.id.in_(affected_ids))
        )
    ).scalars().all()
    member_rows = await session.execute(
        select(RecordClusterMember.cluster_id, RecordClusterMember.record_id).where(
            RecordClusterMember.cluster_id.in_(affected_ids)
        )
    )
    members_by_cluster: dict[uuid.UUID, list[uuid.UUID]] = {}
    all_member_ids: set[uuid.UUID] = set()
    for cluster_id, record_id in member_rows:
        members_by_cluster.setdefault(cluster_id, []).append(record_id)
        all_member_ids.add(record_id)
    surviving_ids = all_member_ids - doomed_records
    records_by_id: dict[uuid.UUID, Record] = {}
    if surviving_ids:
        rec_rows = await session.execute(
            select(Record).where(Record.id.in_(surviving_ids))
        )
        records_by_id = {r.id: r for r in rec_rows.scalars().all()}

    doomed_strs = {str(rid) for rid in doomed_records}
    for cluster in clusters:
        survivors = [
            rid
            for rid in members_by_cluster.get(cluster.id, [])
            if rid not in doomed_records
        ]
        if not survivors:
            await session.delete(cluster)
            continue
        best = max(
            survivors,
            key=lambda rid: (
                _record_completeness(records_by_id[rid]) if rid in records_by_id else -1,
                str(rid),
            ),
        )
        cluster.canonical_record_id = best
        cluster.size = len(survivors)
        graph = cluster.merge_graph or {}
        members = graph.get("members", [])
        cluster.merge_graph = {
            **graph,
            "members": [m for m in members if m.get("record_id") not in doomed_strs],
        }
    await session.flush()


async def empty_trash(
    session: AsyncSession,
    *,
    actor_identity_id: uuid.UUID | None = None,
    age_only: bool = False,
    project_id: uuid.UUID | None = None,
) -> dict[str, int]:
    """Hard-delete rows whose deleted_at is set.

    - `age_only=True` keeps items younger than `trash_retention_days`.
    - `project_id` scopes the wipe to one project.
    """
    cutoff = utcnow() - timedelta(days=get_settings().trash_retention_days)
    deleted: dict[str, int] = {}
    project_being_deleted = False
    deleted_project_ids: list[uuid.UUID] = []
    for name, model in _TRASHABLE.items():
        q = select(model).where(model.deleted_at.is_not(None))
        if age_only:
            q = q.where(model.deleted_at < cutoff)
        if project_id is not None and hasattr(model, "project_id") and model is not Project:
            q = q.where(model.project_id == project_id)
        if project_id is not None and model is Project:
            q = q.where(model.id == project_id)
        rows = (await session.execute(q)).scalars().all()
        if model is Search:
            await _detach_clusters_from_searches(session, [r.id for r in rows])
        for r in rows:
            await session.delete(r)
        deleted[name] = len(rows)
        if model is Project and rows:
            project_being_deleted = True
            deleted_project_ids = [r.id for r in rows]
    # If the project itself was hard-deleted, audit at the no-project scope.
    await record_audit(
        session,
        project_id=None if project_being_deleted else project_id,
        actor_identity_id=actor_identity_id,
        action="trash.empty",
        entity_type="trash",
        entity_id=None,
        payload={
            "age_only": age_only,
            "deleted": deleted,
            "project_id": str(project_id) if project_id else None,
        },
    )
    await session.commit()
    # Snapshot rows cascade with the project; their files on disk do not.
    for pid in deleted_project_ids:
        snap_dir = get_settings().snapshots_dir / str(pid)
        if snap_dir.exists():
            shutil.rmtree(snap_dir, ignore_errors=True)
    return deleted
