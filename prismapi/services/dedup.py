"""Project-level de-duplication service: orchestrates `domain.dedup`."""

from __future__ import annotations

import uuid
from collections import defaultdict

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from prismapi.db.models import Project, Record, RecordCluster, RecordClusterMember
from prismapi.domain.dedup import RecordSnapshot, cluster_records
from prismapi.services.audit import record_audit


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
) -> dict:
    """Rebuild the dedup clusters for the project from scratch.

    Returns a summary: {input, output, by_method, reduction_pct}.
    """
    if reset:
        await session.execute(
            delete(RecordCluster).where(RecordCluster.project_id == project.id)
        )

    rows = await session.execute(select(Record).where(Record.project_id == project.id))
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
