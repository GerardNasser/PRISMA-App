from __future__ import annotations

import uuid

from sqlalchemy import JSON, ForeignKey, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from prismapi.db.base import Base, SoftDeleteMixin, TimestampMixin


class Extraction(Base, TimestampMixin, SoftDeleteMixin):
    """One reviewer's extraction of one cluster.

    `payload` is the JSON document matching the field config's extraction
    template (keys = field config field `key`s). Validation against the template
    happens at write time in the service.
    """

    __tablename__ = "extractions"
    __table_args__ = (
        UniqueConstraint("cluster_id", "reviewer_identity_id", name="uq_extraction_per_reviewer"),
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
    template_base: Mapped[str] = mapped_column(String(40), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    # draft | submitted | reconciled
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class RoBAssessment(Base, TimestampMixin, SoftDeleteMixin):
    """One reviewer's risk-of-bias assessment of one cluster.

    `judgements` maps domain key -> {judgement, justification}. Domain keys
    come from the field config (custom domains) or from a built-in tool spec
    (RoB 2, ROBINS-I, SYRCLE, …).
    """

    __tablename__ = "rob_assessments"
    __table_args__ = (
        UniqueConstraint("cluster_id", "reviewer_identity_id", name="uq_rob_per_reviewer"),
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
    tool: Mapped[str] = mapped_column(String(40), nullable=False)
    judgements: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    overall: Mapped[str | None] = mapped_column(String(40), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
