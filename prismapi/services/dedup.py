"""Project-level de-duplication service: orchestrates `domain.dedup`."""

from __future__ import annotations

import uuid
from collections import defaultdict

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from prismapi.db.models import (
    Extraction,
    Project,
    Record,
    RecordCluster,
    RecordClusterMember,
    RoBAssessment,
    ScreeningDecision,
    Search,
)
from prismapi.domain.dedup import RecordSnapshot, cluster_records
from prismapi.rpc.errors import VALIDATION, RpcError
from prismapi.services.audit import record_audit


async def screening_work_counts(session: AsyncSession, project_id: uuid.UUID) -> dict:
    """Live screening, extraction, and RoB rows that a cluster reset would delete."""
    counts = {}
    for name, model in (
        ("screening_decisions", ScreeningDecision),
        ("extractions", Extraction),
        ("rob_assessments", RoBAssessment),
    ):
        counts[name] = (
            await session.scalar(
                select(func.count(model.id)).where(
                    model.project_id == project_id,
                    model.deleted_at.is_(None),
                )
            )
        ) or 0
    return counts


def _completeness(r: Record) -> int:
    score = 0
    for v in (r.title, r.abstract, r.authors, r.journal, r.year, r.doi, r.pmid, r.url):
        if v:
            score += 1
    return score


async def run_dedup(
    session: AsyncSession,
    *,
    project: Project,
    user_id: uuid.UUID | None,
    reset: bool = True,
    force: bool = False,
) -> dict:
    """Rebuild the dedup clusters for the project from scratch.

    Deleting clusters cascades to every screening decision, extraction, and
    RoB assessment attached to them. If any such work exists, the reset is
    refused unless `force` is set; a forced reset takes a snapshot first.

    Returns a summary: {input, output, by_method, reduction_pct}.
    """
    if reset:
        work = await screening_work_counts(session, project.id)
        if any(work.values()):
            if not force:
                raise RpcError(
                    VALIDATION,
                    "Re-running dedup deletes existing screening, extraction, and "
                    "risk-of-bias work. Pass force=true to proceed; a snapshot is "
                    "taken first.",
                    {"would_delete": work},
                )
            from prismapi.services.snapshot import take_snapshot  # lazy to avoid cycle

            await take_snapshot(
                session,
                project=project,
                kind="pre_dedup",
                actor_identity_id=user_id,
            )
        await session.execute(
            delete(RecordCluster).where(RecordCluster.project_id == project.id)
        )

    # Records whose search sits in the trash are excluded from clustering.
    rows = await session.execute(
        select(Record)
        .join(Search, Record.search_id == Search.id)
        .where(Record.project_id == project.id, Search.deleted_at.is_(None))
    )
    records = list(rows.scalars().all())
    snapshots = [
        RecordSnapshot(
            id=r.id,
            title=r.title or "",
            year=r.year,
            doi=r.doi,
            pmid=r.pmid,
            authors=r.authors,
            completeness=_completeness(r),
        )
        for r in records
    ]
    decisions = cluster_records(snapshots)

    # Group decisions by cluster_key.
    by_key: dict[str, list[tuple[uuid.UUID, str, float]]] = defaultdict(list)
    for d in decisions:
        by_key[d.cluster_key].append((d.record_id, d.method, d.score))

    record_by_id = {r.id: r for r in records}

    method_counts: dict[str, int] = defaultdict(int)
    clusters: list[RecordCluster] = []
    for key, members in by_key.items():
        # canonical = first member (which is also the most-complete due to ordering)
        canonical_id, primary_method, _ = members[0]
        method_counts[primary_method] += 1
        cluster = RecordCluster(
            project_id=project.id,
            canonical_record_id=canonical_id,
            size=len(members),
            method=primary_method,
            confidence=min(m[2] for m in members),
            merge_graph={
                "cluster_key": key,
                "members": [
                    {
                        "record_id": str(rid),
                        "method": method,
                        "score": score,
                        "title": (record_by_id[rid].title or "")[:200],
                    }
                    for (rid, method, score) in members
                ],
            },
        )
        session.add(cluster)
        await session.flush()
        for rid, method, score in members:
            session.add(
                RecordClusterMember(
                    cluster_id=cluster.id,
                    record_id=rid,
                    match_reason=method,
                    match_score=score,
                )
            )
        clusters.append(cluster)

    summary = {
        "input": len(records),
        "output": len(clusters),
        "duplicates_removed": len(records) - len(clusters),
        "reduction_pct": (
            round(100.0 * (len(records) - len(clusters)) / len(records), 2) if records else 0.0
        ),
        "by_method": dict(method_counts),
    }
    await record_audit(
        session,
        project_id=project.id,
        actor_identity_id=user_id,
        action="dedup.run",
        entity_type="project",
        entity_id=str(project.id),
        payload=summary,
    )
    await session.commit()
    return summary
