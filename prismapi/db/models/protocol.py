from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import JSON, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from prismapi.db.base import Base, SoftDeleteMixin, TimestampMixin

if TYPE_CHECKING:
    from prismapi.db.models.project import Project


class Protocol(Base, TimestampMixin, SoftDeleteMixin):
    """A versioned protocol for a project. Each new save = new version row."""

    __tablename__ = "protocols"
    __table_args__ = (UniqueConstraint("project_id", "version", name="uq_protocol_version"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    background: Mapped[str | None] = mapped_column(Text, nullable=True)
    objectives: Mapped[str | None] = mapped_column(Text, nullable=True)
    research_questions: Mapped[str | None] = mapped_column(Text, nullable=True)

    pico: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    eligibility_criteria: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    search_strategy_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    registration_registry: Mapped[str | None] = mapped_column(String(50), nullable=True)
    registration_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    registration_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    registration_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    # registered | submitted | not_registered_justified | not_registered

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    snapshot_field_config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    # Reviewer-team config (added in v0.7). Holds:
    #   n_reviewers (int), alpha_threshold (float), kappa_threshold (float),
    #   conflict_strategy ∈ {"third_reviewer", "discussion", "lead_arbiter"},
    #   tiebreaker_identity_id (UUID | None).
    reviewer_config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    project: Mapped[Project] = relationship(lazy="selectin")


class PicoElement(Base, TimestampMixin):
    """Structured PICO/PICOTS rows, attached to a protocol version.

    Kept as a separate table so the wizard can render them as a repeatable
    section per category, and so they're queryable for compliance checks.
    """

    __tablename__ = "pico_elements"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    protocol_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("protocols.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category: Mapped[str] = mapped_column(String(20), nullable=False)
    # category ∈ {P, I, C, O, T, S}  (population, intervention, comparator, outcome, timing, study design)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    keywords: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
