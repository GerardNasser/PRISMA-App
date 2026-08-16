from __future__ import annotations

import uuid

from sqlalchemy import JSON, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from prismapi.db.base import Base, TimestampMixin


class AuditLog(Base, TimestampMixin):
    """Immutable record of every state-changing action.

    Aytug et al. (2012) transparency: every procedural and judgment call should
    be recorded so the methods section can be reconstructed.
    """

    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True
    )
    actor_identity_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("identities.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class JudgmentCall(Base, TimestampMixin):
    """A reviewer-recorded methodological judgment call.

    Examples: choice of effect-size metric, decision to pool across primer
    regions, decision to exclude a study for "too broad", choice of estimator.
    """

    __tablename__ = "judgment_calls"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    actor_identity_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("identities.id", ondelete="SET NULL"), nullable=True
    )
    phase: Mapped[str] = mapped_column(String(40), nullable=False)
    # phase ∈ {protocol, search, dedup, screening, extraction, rob, synthesis, pubbias, certainty, reporting}
    topic: Mapped[str] = mapped_column(String(200), nullable=False)
    decision: Mapped[str] = mapped_column(Text, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    alternatives_considered: Mapped[str | None] = mapped_column(Text, nullable=True)
