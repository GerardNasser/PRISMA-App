from __future__ import annotations

import uuid

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from prismapi.db.base import Base, TimestampMixin


class Snapshot(Base, TimestampMixin):
    """Layer-4 safety: a saved point-in-time copy of a project's DB rows.

    The underlying SQLite file is at `app_data_dir/snapshots/<project_uuid>/<id>.db`
    (or `.zst`-compressed for older snapshots). `manifest` carries the row counts
    and SHA-256 so a restore can be verified before applying.
    """

    __tablename__ = "snapshots"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    kind: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    # kind ∈ {auto_on_open, pre_import, pre_migration, manual, pre_restore}
    relative_path: Mapped[str] = mapped_column(String(400), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    manifest: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    is_pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
