from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from prismapi.db.base import Base, SoftDeleteMixin, TimestampMixin


class ScreeningDecision(Base, TimestampMixin, SoftDeleteMixin):
    """Per-reviewer screening decision for a (cluster, stage).

    stage ∈ {title_abstract, full_text}. Decision ∈ {include, exclude, maybe}.
    Optional `exclusion_code` references a codebook rule.
    """

    __tablename__ = "screening_decisions"
    __table_args__ = (
        UniqueConstraint("cluster_id", "reviewer_identity_id", "stage", name="uq_screening_per_reviewer_stage"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    cluster_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("record_clusters.id", ondelete="CASCADE"), nullable=False, index=True
    )
    reviewer_identity_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("identities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    stage: Mapped[str] = mapped_column(String(20), nullable=False)
    decision: Mapped[str] = mapped_column(String(20), nullable=False)
    # include | exclude | maybe
    exclusion_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    # 1-5 self-rated confidence; for IRR weighting if desired


class ConflictResolution(Base, TimestampMixin):
    """When two+ reviewers disagree on a cluster decision, a third reviewer
    (or the lead) resolves it. The resolution is the final decision for that
    cluster + stage.
    """

    __tablename__ = "conflict_resolutions"
    __table_args__ = (
        UniqueConstraint("cluster_id", "stage", name="uq_conflict_per_cluster_stage"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    cluster_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("record_clusters.id", ondelete="CASCADE"), nullable=False, index=True
    )
    stage: Mapped[str] = mapped_column(String(20), nullable=False)
    arbiter_identity_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("identities.id", ondelete="CASCADE"), nullable=False
    )
    final_decision: Mapped[str] = mapped_column(String(20), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
