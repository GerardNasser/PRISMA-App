"""Database-backed predicates for the phase gates.

`gate_state` builds the full `GateState` snapshot that
`prismapi.domain.phases.gate_satisfied` evaluates. The completion rules:

- A rater is done with title/abstract screening when they have a live
  (non-soft-deleted) decision for every cluster in the project.
- A cluster advances to full text when its final title/abstract decision is
  include or maybe. The final decision is the conflict resolution if one
  exists, otherwise the unanimous decision once every rater has voted.
  Conflicted, unresolved clusters do not advance.
- A rater is done with full-text screening when they have a live decision for
  every advanced cluster. If title/abstract is complete and no cluster
  advanced, full text is trivially complete.
- Extraction counts once any live extraction has been submitted (not draft).
- Risk of bias counts once any live assessment exists.
- Synthesis is not part of this beta, so `has_synthesis` is always False and
  the report phase stays locked.

Screening-eligible raters are project members whose role is not read_only.
"""

from __future__ import annotations

import uuid
from collections import defaultdict

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from prismapi.db.models import (
    ConflictResolution,
    Extraction,
    Project,
    ProjectMember,
    Protocol,
    Record,
    RecordCluster,
    RoBAssessment,
    ScreeningDecision,
)
from prismapi.domain.phases import GateState

ADVANCING_DECISIONS = frozenset({"include", "maybe"})


async def _rater_identity_ids(session: AsyncSession, project_id: uuid.UUID) -> set[uuid.UUID]:
    """Identity ids of members who screen (everyone except read_only)."""
    rows = await session.scalars(
        select(ProjectMember.identity_id).where(
            ProjectMember.project_id == project_id,
            ProjectMember.role != "read_only",
        )
    )
    return set(rows)


async def _live_cluster_ids(session: AsyncSession, project_id: uuid.UUID) -> set[uuid.UUID]:
    rows = await session.scalars(
        select(RecordCluster.id).where(RecordCluster.project_id == project_id)
    )
    return set(rows)


def _stage_done_raters(
    decisions: list[tuple[uuid.UUID, uuid.UUID]],
    raters: set[uuid.UUID],
    pool: set[uuid.UUID],
) -> int:
    """Count raters holding a decision for every cluster in `pool`.

    `decisions` is (reviewer_identity_id, cluster_id) pairs for one stage.
    An empty pool means no work exists at this stage, so nobody counts as
    done — callers handle the trivially-complete case themselves.
    """
    if not pool:
        return 0
    per_rater: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
    for reviewer_id, cluster_id in decisions:
        if cluster_id in pool:
            per_rater[reviewer_id].add(cluster_id)
    return sum(1 for r in raters if per_rater.get(r, set()) >= pool)


async def _stage_decisions(
    session: AsyncSession, project_id: uuid.UUID, stage: str
) -> list[tuple[uuid.UUID, uuid.UUID, str]]:
    """Live decisions for one stage as (reviewer, cluster, decision) tuples."""
    rows = await session.execute(
        select(
            ScreeningDecision.reviewer_identity_id,
            ScreeningDecision.cluster_id,
            ScreeningDecision.decision,
        ).where(
            ScreeningDecision.project_id == project_id,
            ScreeningDecision.stage == stage,
            ScreeningDecision.deleted_at.is_(None),
        )
    )
    return [tuple(row) for row in rows]


def _full_text_pool(
    ta_decisions: list[tuple[uuid.UUID, uuid.UUID, str]],
    resolutions: dict[uuid.UUID, str],
    raters: set[uuid.UUID],
    clusters: set[uuid.UUID],
) -> tuple[set[uuid.UUID], int]:
    """(advancing clusters, pending-conflict count) at title/abstract.

    A cluster is pending when every rater has voted, the votes disagree, and
    no arbitration exists yet — its fate is undecided, so the pool cannot be
    treated as final while any remain.
    """
    by_cluster: dict[uuid.UUID, dict[uuid.UUID, str]] = defaultdict(dict)
    for reviewer_id, cluster_id, decision in ta_decisions:
        if cluster_id in clusters:
            by_cluster[cluster_id][reviewer_id] = decision
    pool: set[uuid.UUID] = set()
    pending = 0
    for cluster_id in clusters:
        if cluster_id in resolutions:
            if resolutions[cluster_id] in ADVANCING_DECISIONS:
                pool.add(cluster_id)
            continue
        votes = by_cluster.get(cluster_id, {})
        if raters and raters <= set(votes):
            distinct = {votes[r] for r in raters}
            if len(distinct) == 1:
                if distinct <= ADVANCING_DECISIONS:
                    pool.add(cluster_id)
            else:
                pending += 1
    return pool, pending


async def _ta_resolutions(
    session: AsyncSession, project_id: uuid.UUID
) -> dict[uuid.UUID, str]:
    rows = await session.execute(
        select(ConflictResolution.cluster_id, ConflictResolution.final_decision).where(
            ConflictResolution.project_id == project_id,
            ConflictResolution.stage == "title_abstract",
        )
    )
    return {row[0]: row[1] for row in rows}


async def full_text_pool_ids(
    session: AsyncSession, project_id: uuid.UUID
) -> set[uuid.UUID]:
    """Ids of clusters whose final title/abstract decision advances them."""
    raters = await _rater_identity_ids(session, project_id)
    clusters = await _live_cluster_ids(session, project_id)
    ta_decisions = await _stage_decisions(session, project_id, "title_abstract")
    resolutions = await _ta_resolutions(session, project_id)
    pool, _pending = _full_text_pool(ta_decisions, resolutions, raters, clusters)
    return pool


async def gate_state(session: AsyncSession, project_id: uuid.UUID) -> GateState:
    """Assemble the `GateState` snapshot for a project from the database."""
    project_exists = bool(
        await session.scalar(select(func.count(Project.id)).where(Project.id == project_id))
    )
    raters = await _rater_identity_ids(session, project_id)
    has_protocol = (
        await session.scalar(
            select(func.count(Protocol.id)).where(Protocol.project_id == project_id)
        )
    ) > 0
    n_records = (
        await session.scalar(
            select(func.count(Record.id)).where(Record.project_id == project_id)
        )
    ) or 0
    clusters = await _live_cluster_ids(session, project_id)

    ta_decisions = await _stage_decisions(session, project_id, "title_abstract")
    ft_decisions = await _stage_decisions(session, project_id, "full_text")
    resolutions = await _ta_resolutions(session, project_id)

    n_ta_done = _stage_done_raters(
        [(r, c) for r, c, _ in ta_decisions], raters, clusters
    )
    ft_pool, n_pending = _full_text_pool(ta_decisions, resolutions, raters, clusters)
    # Real count only — an empty pool reports zero done, and the gate logic
    # decides whether that means "nothing to read" or "conflicts unresolved".
    n_ft_done = (
        _stage_done_raters([(r, c) for r, c, _ in ft_decisions], raters, ft_pool)
        if ft_pool
        else 0
    )

    has_extraction = bool(
        await session.scalar(
            select(func.count(Extraction.id)).where(
                Extraction.project_id == project_id,
                Extraction.status != "draft",
                Extraction.deleted_at.is_(None),
            )
        )
    )
    has_rob = bool(
        await session.scalar(
            select(func.count(RoBAssessment.id)).where(
                RoBAssessment.project_id == project_id,
                RoBAssessment.deleted_at.is_(None),
            )
        )
    )

    return GateState(
        project_exists=project_exists,
        n_raters=len(raters),
        has_protocol=has_protocol,
        n_records=n_records,
        n_clusters=len(clusters),
        n_ta_done_raters=n_ta_done,
        n_ft_done_raters=n_ft_done,
        n_ft_pool=len(ft_pool),
        n_conflicts_pending=n_pending,
        has_extraction=has_extraction,
        has_rob=has_rob,
        has_synthesis=False,
    )
