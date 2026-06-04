from __future__ import annotations

import uuid

from sqlalchemy import JSON, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from prismapi.db.base import Base, TimestampMixin


class RecordCluster(Base, TimestampMixin):
    """A deduplicated cluster of records that represent the same study.

    The canonical Record is `canonical_record_id`. The cluster carries the
    cross-database identifier that screening / extraction operates on.
    """

    __tablename__ = "record_clusters"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    canonical_record_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("records.id", ondelete="RESTRICT"), nullable=False
    )
    size: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    method: Mapped[str] = mapped_column(String(40), nullable=False)
    # method ∈ {doi, pmid, title_year_norm, fuzzy_title, manual_merge}
    confidence: Mapped[float] = mapped_column(nullable=False, default=1.0)

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    merge_graph: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    members: Mapped[list["RecordClusterMember"]] = relationship(
        back_populates="cluster", cascade="all, delete-orphan", lazy="selectin"
    )


class RecordClusterMember(Base, TimestampMixin):
    __tablename__ = "record_cluster_members"
    __table_args__ = (UniqueConstraint("record_id", name="uq_cluster_member_record"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    cluster_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("record_clusters.id", ondelete="CASCADE"), nullable=False, index=True
    )
    record_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("records.id", ondelete="CASCADE"), nullable=False, index=True
    )
    match_reason: Mapped[str] = mapped_column(String(80), nullable=False)
    match_score: Mapped[float] = mapped_column(nullable=False, default=1.0)

    cluster: Mapped[RecordCluster] = relationship(back_populates="members", lazy="selectin")
