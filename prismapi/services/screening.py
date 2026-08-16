"""Screening + IRR services."""

from __future__ import annotations

import uuid
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from prismapi.db.models import (
    ConflictResolution,
    Project,
    ScreeningDecision,
)
from prismapi.domain.irr import (
    cohens_kappa,
    fleiss_kappa,
    interpret_alpha,
    krippendorff_alpha,
    percent_agreement,
)
from prismapi.services.audit import record_audit


async def upsert_decision(
    session: AsyncSession,
    *,
    project_id: uuid.UUID,
    reviewer_id: uuid.UUID,
    cluster_id: uuid.UUID,
    stage: str,
    decision: str,
    exclusion_code: str | None = None,
    notes: str | None = None,
    confidence: int = 3,
) -> ScreeningDecision:
    """Create or update this reviewer's decision for (cluster, stage)."""
    if stage not in {"title_abstract", "full_text"}:
        raise ValueError(f"Unknown stage: {stage}")
    if decision not in {"include", "exclude", "maybe"}:
        raise ValueError(f"Unknown decision: {decision}")
    existing = await session.scalar(
        select(ScreeningDecision).where(
            ScreeningDecision.cluster_id == cluster_id,
            ScreeningDecision.reviewer_identity_id == reviewer_id,
            ScreeningDecision.stage == stage,
        )
    )
    if existing is None:
        existing = ScreeningDecision(
            project_id=project_id,
            cluster_id=cluster_id,
            reviewer_identity_id=reviewer_id,
            stage=stage,
            decision=decision,
            exclusion_code=exclusion_code,
            notes=notes,
            confidence=confidence,
        )
        session.add(existing)
    else:
        existing.decision = decision
        existing.exclusion_code = exclusion_code
        existing.notes = notes
        existing.confidence = confidence
    await record_audit(
        session,
        project_id=project_id,
        actor_identity_id=reviewer_id,
        action="screening.decision",
        entity_type="cluster",
        entity_id=str(cluster_id),
        payload={"stage": stage, "decision": decision, "exclusion_code": exclusion_code},
    )
    await session.commit()
    await session.refresh(existing)
    return existing


async def compute_irr(
    session: AsyncSession,
    *,
    project: Project,
    stage: str,
) -> dict:
    """Compute α + κ + % agreement for this project + stage."""
    rows = (
        (
            await session.execute(
                select(ScreeningDecision).where(
                    ScreeningDecision.project_id == project.id,
                    ScreeningDecision.stage == stage,
                )
            )
        )
        .scalars()
        .all()
    )
    by_cluster: dict[uuid.UUID, dict[uuid.UUID, str]] = defaultdict(dict)
    reviewer_set: set[uuid.UUID] = set()
    for d in rows:
        by_cluster[d.cluster_id][d.reviewer_identity_id] = d.decision
        reviewer_set.add(d.reviewer_identity_id)
    reviewers = sorted(reviewer_set)

    # Build rating matrix: rows = items, cols = reviewers (None = missing).
    matrix: list[list[str | None]] = []
    for _cid, decisions in by_cluster.items():
        row: list[str | None] = [decisions.get(r) for r in reviewers]
        matrix.append(row)

    if not matrix or len(reviewers) < 2:
        return {
            "stage": stage,
            "n_items": len(matrix),
            "n_reviewers": len(reviewers),
            "alpha_binary": None,
            "fleiss_kappa": None,
            "cohens_kappa": None,
            "percent_agreement": None,
            "interpretation": None,
            "conflicts": [str(cid) for cid, d in by_cluster.items() if len({*d.values()}) > 1],
        }

    pa = percent_agreement(matrix)
    fk = fleiss_kappa(matrix) if len(reviewers) > 2 else None
    ck = cohens_kappa(*[ [m[i] for m in matrix] for i in range(2) ]) if len(reviewers) == 2 else None
    # Binary α: collapse "maybe" to "include" for the IRR calc (common practice).
    bin_matrix = [
        [None if v is None else ("include" if v in ("include", "maybe") else "exclude") for v in row]
        for row in matrix
    ]
    alpha = krippendorff_alpha(bin_matrix, level="nominal")
    conflicts = [str(cid) for cid, d in by_cluster.items() if len({*d.values()}) > 1]
    return {
        "stage": stage,
        "n_items": len(matrix),
        "n_reviewers": len(reviewers),
        "alpha_binary": round(alpha, 4),
        "fleiss_kappa": round(fk, 4) if fk is not None else None,
        "cohens_kappa": round(ck, 4) if ck is not None else None,
        "percent_agreement": round(pa, 4),
        "interpretation": interpret_alpha(alpha),
        "conflicts": conflicts,
    }


async def resolve_conflict(
    session: AsyncSession,
    *,
    project_id: uuid.UUID,
    arbiter_id: uuid.UUID,
    cluster_id: uuid.UUID,
    stage: str,
    final_decision: str,
    rationale: str,
) -> ConflictResolution:
    """Record the arbiter's final decision for a conflicted (cluster, stage)."""
    if final_decision not in {"include", "exclude"}:
        raise ValueError("Conflict resolution decision must be include or exclude")
    existing = await session.scalar(
        select(ConflictResolution).where(
            ConflictResolution.cluster_id == cluster_id,
            ConflictResolution.stage == stage,
        )
    )
    if existing is None:
        existing = ConflictResolution(
            project_id=project_id,
            cluster_id=cluster_id,
            stage=stage,
            arbiter_identity_id=arbiter_id,
            final_decision=final_decision,
            rationale=rationale,
        )
        session.add(existing)
    else:
        existing.arbiter_identity_id = arbiter_id
        existing.final_decision = final_decision
        existing.rationale = rationale
    await record_audit(
        session,
        project_id=project_id,
        actor_identity_id=arbiter_id,
        action="screening.resolve_conflict",
        entity_type="cluster",
        entity_id=str(cluster_id),
        payload={"stage": stage, "final_decision": final_decision},
    )
    await session.commit()
    await session.refresh(existing)
    return existing
