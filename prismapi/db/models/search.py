from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from prismapi.db.base import Base, SoftDeleteMixin, TimestampMixin


class Search(Base, TimestampMixin, SoftDeleteMixin):
    """A captured search execution.

    Records: which database, exact query string, applied filters, timestamp,
    hit count. Mandatory PRISMA-S item.
    """

    __tablename__ = "searches"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    actor_identity_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("identities.id", ondelete="SET NULL"), nullable=True
    )

    database: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    # adapter id: pubmed | openalex | crossref | wos | arxiv | semantic_scholar | ris_import | csv_import …
    query_string: Mapped[str] = mapped_column(Text, nullable=False)
    applied_filters: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    options: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="completed")
    # queued | running | completed | failed
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    hit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    records: Mapped[list[Record]] = relationship(
        back_populates="search", cascade="all, delete-orphan", lazy="noload"
    )


class Record(Base, TimestampMixin):
    """A bibliographic record retrieved from a search adapter.

    `external_id` + `database` uniquely identify the record at the source.
    A given study can appear as multiple records (one per database); dedup
    in Phase 3 maps them to a canonical RecordCluster.
    """

    __tablename__ = "records"
    __table_args__ = (
        UniqueConstraint("search_id", "external_id", name="uq_record_search_external"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    search_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("searches.id", ondelete="CASCADE"), nullable=False, index=True
    )

    database: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    external_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    # PMID for pubmed, OpenAlex W-id, DOI for crossref, WoS UID, arXiv id …

    doi: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    pmid: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)

    title: Mapped[str] = mapped_column(Text, nullable=False)
    abstract: Mapped[str | None] = mapped_column(Text, nullable=True)
    authors: Mapped[str | None] = mapped_column(Text, nullable=True)
    journal: Mapped[str | None] = mapped_column(Text, nullable=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    publication_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    language: Mapped[str | None] = mapped_column(String(20), nullable=True)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)

    raw: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    search: Mapped[Search] = relationship(back_populates="records", lazy="noload")
