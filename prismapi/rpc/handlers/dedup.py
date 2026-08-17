"""Dedup RPC: run, list clusters, manual merge."""

from __future__ import annotations

import uuid

from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from prismapi.db.models import (
    ConflictResolution,
    Extraction,
    Project,
    ProjectMember,
    Record,
    RecordCluster,
    RecordClusterMember,
    RoBAssessment,
    ScreeningDecision,
)
from prismapi.rpc.dispatcher import rpc
from prismapi.rpc.errors import NOT_FOUND, VALIDATION, RpcError
from prismapi.services.audit import record_audit
from prismapi.services.dedup import run_dedup


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


class DedupRun(BaseModel):
    project_id: str
    force: bool = False


@rpc("dedup.run")
async def run(
    params: DedupRun, session: AsyncSession, identity_id: uuid.UUID
) -> dict:
    project = await _assert_member(session, uuid.UUID(params.project_id), identity_id)
    return await run_dedup(
        session, project=project, user_id=identity_id, reset=True, force=params.force
    )


class ClustersList(BaseModel):
    project_id: str
    limit: int = 200
    offset: int = 0


def _cluster_out(c: RecordCluster) -> dict:
    members = c.merge_graph.get("members", []) if isinstance(c.merge_graph, dict) else []
    return {
        "id": str(c.id),
        "canonical_record_id": str(c.canonical_record_id),
        "size": c.size,
        "method": c.method,
        "confidence": c.confidence,
        "members": members,
    }


def _canonical_out(r: Record | None) -> dict | None:
    if r is None:
        return None
    return {
        "id": str(r.id),
        "title": r.title,
        "abstract": r.abstract,
        "authors": r.authors,
        "journal": r.journal,
        "year": r.year,
        "doi": r.doi,
        "pmid": r.pmid,
        "url": r.url,
        "publication_type": r.publication_type,
    }


@rpc("dedup.clusters.list")
async def clusters(
    params: ClustersList, session: AsyncSession, identity_id: uuid.UUID
) -> dict:
    await _assert_member(session, uuid.UUID(params.project_id), identity_id)
    rows = await session.execute(
        select(RecordCluster)
        .where(RecordCluster.project_id == uuid.UUID(params.project_id))
        .order_by(RecordCluster.size.desc(), RecordCluster.created_at.asc())
        .offset(params.offset)
        .limit(params.limit)
    )
    clusters = list(rows.scalars().all())
    # Bulk-load canonical records so the screening UI has abstract + metadata.
    canonical_ids = [c.canonical_record_id for c in clusters]
    canonical_map: dict[uuid.UUID, Record] = {}
    if canonical_ids:
        rec_rows = await session.execute(
            select(Record).where(Record.id.in_(canonical_ids))
        )
        canonical_map = {r.id: r for r in rec_rows.scalars().all()}
    out = []
    for c in clusters:
        d = _cluster_out(c)
        d["canonical"] = _canonical_out(canonical_map.get(c.canonical_record_id))
        out.append(d)
    return {"clusters": out}


# Work tables a manual merge must carry over: (model, counter key, natural
# key columns beyond cluster_id, whether rows can be soft-deleted).
_WORK_TABLES = (
    (ScreeningDecision, "decisions", ("reviewer_identity_id", "stage"), True),
    (Extraction, "extractions", ("reviewer_identity_id",), True),
    (RoBAssessment, "rob", ("reviewer_identity_id",), True),
    (ConflictResolution, "resolutions", ("stage",), False),
)


async def _migrate_cluster_work(
    session: AsyncSession,
    losing_id: uuid.UUID,
    canonical_id: uuid.UUID,
    migrated: dict[str, int],
    dropped: dict[str, int],
) -> None:
    """Re-point screening/extraction/RoB work from a merged-away cluster.

    When both clusters hold a row for the same natural key, a LIVE row always
    wins: a soft-deleted row on the canonical side is replaced (its tombstone
    deleted) rather than silently outranking real work. Two live rows keep
    the canonical one; two tombstones keep the canonical tombstone.
    """
    for model, counter, key_cols, soft_deletable in _WORK_TABLES:
        losing_rows = (
            await session.execute(select(model).where(model.cluster_id == losing_id))
        ).scalars().all()
        if not losing_rows:
            continue
        canonical_rows = (
            await session.execute(select(model).where(model.cluster_id == canonical_id))
        ).scalars().all()

        def key_of(row):
            return tuple(getattr(row, c) for c in key_cols)

        canonical_by_key = {key_of(r): r for r in canonical_rows}
        for row in losing_rows:
            existing = canonical_by_key.get(key_of(row))
            if existing is None:
                row.cluster_id = canonical_id
                canonical_by_key[key_of(row)] = row
                migrated[counter] += 1
                continue
            row_live = not soft_deletable or row.deleted_at is None
            existing_live = not soft_deletable or existing.deleted_at is None
            if row_live and not existing_live:
                # The losing side has the real work; drop the tombstone.
                await session.delete(existing)
                await session.flush()
                row.cluster_id = canonical_id
                canonical_by_key[key_of(row)] = row
                migrated[counter] += 1
            else:
                await session.delete(row)
                dropped[counter] += 1

    await session.flush()


class ManualMerge(BaseModel):
    project_id: str
    cluster_ids: list[str]
    canonical_cluster_id: str | None = None
    notes: str | None = None


@rpc("dedup.manual_merge")
async def manual_merge(
    params: ManualMerge, session: AsyncSession, identity_id: uuid.UUID
) -> dict:
    project = await _assert_member(session, uuid.UUID(params.project_id), identity_id)
    if len(params.cluster_ids) < 2:
        raise RpcError(VALIDATION, "Need at least 2 clusters to merge")
    cluster_uuids = [uuid.UUID(c) for c in params.cluster_ids]
    clusters = (
        (
            await session.execute(
                select(RecordCluster).where(RecordCluster.id.in_(cluster_uuids))
            )
        )
        .scalars()
        .all()
    )
    if len(clusters) != len(cluster_uuids):
        raise RpcError(NOT_FOUND, "One or more clusters not found")
    if any(c.project_id != project.id for c in clusters):
        raise RpcError(NOT_FOUND, "Cluster from a different project")
    canonical = next(
        (c for c in clusters if params.canonical_cluster_id and str(c.id) == params.canonical_cluster_id),
        clusters[0],
    )
    new_members: list[dict] = []
    migrated: dict[str, int] = {"decisions": 0, "extractions": 0, "rob": 0, "resolutions": 0}
    dropped: dict[str, int] = {"decisions": 0, "extractions": 0, "rob": 0, "resolutions": 0}
    for c in clusters:
        new_members.extend(c.merge_graph.get("members", []))
        if c.id != canonical.id:
            # Bulk UPDATE, not per-row attribute assignment: rows moved via
            # the ORM stay in the losing cluster's `members` collection, and
            # session.delete(c) fires its delete-orphan cascade over that
            # collection — deleting the freshly re-pointed rows.
            await session.execute(
                update(RecordClusterMember)
                .where(RecordClusterMember.cluster_id == c.id)
                .values(
                    cluster_id=canonical.id,
                    match_reason="manual_merge",
                    match_score=1.0,
                )
            )
            session.expire(c, ["members"])
            await _migrate_cluster_work(session, c.id, canonical.id, migrated, dropped)
            await session.delete(c)
    canonical.size = len(new_members)
    canonical.method = "manual_merge"
    canonical.confidence = 1.0
    canonical.merge_graph = {
        **(canonical.merge_graph or {}),
        "members": new_members,
        "manual_notes": params.notes,
    }
    await record_audit(
        session,
        project_id=project.id,
        actor_identity_id=identity_id,
        action="dedup.manual_merge",
        entity_type="cluster",
        entity_id=str(canonical.id),
        payload={
            "merged_cluster_ids": params.cluster_ids,
            "notes": params.notes,
            "work_migrated": migrated,
            "work_dropped_as_duplicate": dropped,
        },
    )
    await session.commit()
    await session.refresh(canonical)
    return _cluster_out(canonical)
