from __future__ import annotations

import uuid

from sqlalchemy import JSON, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from prismapi.db.base import Base, SoftDeleteMixin, TimestampMixin


class Codebook(Base, TimestampMixin, SoftDeleteMixin):
    """Versioned screening codebook per project."""

    __tablename__ = "codebooks"
    __table_args__ = (UniqueConstraint("project_id", "version", name="uq_codebook_version"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    rules: Mapped[list[CodebookRule]] = relationship(
        back_populates="codebook", cascade="all, delete-orphan", lazy="selectin"
    )


class CodebookRule(Base, TimestampMixin):
    __tablename__ = "codebook_rules"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    codebook_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("codebooks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    # short identifier shown in reviewer UI (e.g., "EXC-WASTE")
    direction: Mapped[str] = mapped_column(String(10), nullable=False)
    # direction ∈ {include, exclude, flag}
    category: Mapped[str | None] = mapped_column(String(120), nullable=True)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    examples: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    codebook: Mapped[Codebook] = relationship(back_populates="rules", lazy="selectin")
