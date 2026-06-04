"""Layer-4 safety: per-project snapshots.

A snapshot is a `.prismaproj` zip stored under `app_data_dir/snapshots/<project_uuid>/`.
The `Snapshot` row records the location + sha256 + manifest counts so the user
can browse and restore them from Settings.

Auto-snapshots are taken:
- on first open of a project in a session (`auto_on_open`),
- before any state-file import (`pre_import`),
- before any schema migration (`pre_migration`),
- before any restore (`pre_restore`).

Manual snapshots are user-driven and never auto-evict.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from prismapi.config import get_settings
from prismapi.db.models import Project, Snapshot
from prismapi.db.models.snapshot import Snapshot as SnapshotModel
from prismapi.services.audit import record_audit


def _snapshot_dir_for(project_id: uuid.UUID) -> Path:
    base = get_settings().snapshots_dir / str(project_id)
    base.mkdir(parents=True, exist_ok=True)
    return base


async def take_snapshot(
    session: AsyncSession,
    *,
    project: Project,
    kind: str,
    label: str | None = None,
    actor_identity_id: uuid.UUID | None = None,
) -> Snapshot:
    """Take a snapshot by exporting the project as a `.prismaproj` to disk."""
    from prismapi.statefile.exporter import export_project  # lazy to avoid cycle

    ts = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    label = label or f"{kind} {ts}"
    target_dir = _snapshot_dir_for(project.id)
    safe_label = "".join(c for c in label if c.isalnum() or c in "-_") or "snapshot"
    out_path = target_dir / f"{ts}-{safe_label}.prismaproj"

    manifest = await export_project(session, project=project, output_path=out_path)
    payload_bytes = out_path.read_bytes()
    sha = hashlib.sha256(payload_bytes).hexdigest()

    snap = SnapshotModel(
        project_id=project.id,
        label=label,
        kind=kind,
        relative_path=str(out_path.relative_to(get_settings().app_data_dir)),
        size_bytes=len(payload_bytes),
        sha256=sha,
        manifest=manifest.model_dump(mode="json"),
    )
    session.add(snap)
    await session.flush()

    await record_audit(
        session,
        project_id=project.id,
        actor_identity_id=actor_identity_id,
        action="snapshot.create",
        entity_type="snapshot",
        entity_id=str(snap.id),
        payload={"kind": kind, "label": label, "sha256": sha},
    )
    await _enforce_auto_cap(session, project_id=project.id)
    await session.commit()
    return snap


async def _enforce_auto_cap(session: AsyncSession, *, project_id: uuid.UUID) -> None:
    cap = get_settings().snapshot_auto_cap
    rows = (
        (
            await session.execute(
                select(SnapshotModel)
                .where(
                    SnapshotModel.project_id == project_id,
                    SnapshotModel.kind != "manual",
                    SnapshotModel.is_pinned.is_(False),
                )
                .order_by(SnapshotModel.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    for old in rows[cap:]:
        path = get_settings().app_data_dir / old.relative_path
        if path.exists():
            path.unlink(missing_ok=True)
        await session.delete(old)


async def list_snapshots(
    session: AsyncSession, *, project_id: uuid.UUID
) -> list[SnapshotModel]:
    rows = (
        (
            await session.execute(
                select(SnapshotModel)
                .where(SnapshotModel.project_id == project_id)
                .order_by(SnapshotModel.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


async def delete_snapshot(
    session: AsyncSession,
    *,
    snapshot_id: uuid.UUID,
    actor_identity_id: uuid.UUID | None = None,
) -> None:
    snap = await session.get(SnapshotModel, snapshot_id)
    if snap is None:
        return
    path = get_settings().app_data_dir / snap.relative_path
    if path.exists():
        path.unlink(missing_ok=True)
    project_id = snap.project_id
    await session.delete(snap)
    await record_audit(
        session,
        project_id=project_id,
        actor_identity_id=actor_identity_id,
        action="snapshot.delete",
        entity_type="snapshot",
        entity_id=str(snapshot_id),
        payload={},
    )
    await session.commit()
