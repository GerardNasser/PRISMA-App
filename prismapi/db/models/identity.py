from __future__ import annotations

import uuid

from sqlalchemy import Boolean, CheckConstraint, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from prismapi.db.base import Base, TimestampMixin


class Identity(Base, TimestampMixin):
    """Reviewer identity.

    The local install has exactly one `is_local=True` identity (the user). Foreign
    identities (collaborators encountered via imported .prismaproj files) are also
    stored here with `is_local=False` so their decisions/extractions can be attributed.

    Per the project's identity model: last_name is required, and at least one of
    {orcid, email} must be set. The DB enforces this with a CHECK constraint.
    """

    __tablename__ = "identities"
    __table_args__ = (
        CheckConstraint(
            "(orcid IS NOT NULL AND length(orcid) > 0) OR (email IS NOT NULL AND length(email) > 0)",
            name="identity_needs_orcid_or_email",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    last_name: Mapped[str] = mapped_column(String(200), nullable=False)
    orcid: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True, index=True)
    display_name: Mapped[str] = mapped_column(String(400), nullable=False)
    institution: Mapped[str | None] = mapped_column(String(300), nullable=True)
    is_local: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)


ORCID_PATTERN = r"^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$"


def render_display_name(
    last_name: str, orcid: str | None, email: str | None, institution: str | None = None
) -> str:
    """Compose the public-facing display name: `Nasser (gerard@uncc.edu)`.

    Preference order when both ORCID and email are present:
      1. Email if it looks institutional (i.e., not gmail/yahoo/outlook/icloud).
      2. ORCID otherwise.
    Tweakable later via institution heuristics.
    """
    bare_last = last_name.strip()
    if email and orcid:
        domain = email.split("@", 1)[-1].lower() if "@" in email else ""
        if domain and not any(domain.endswith(p) for p in (
            "gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "icloud.com",
            "live.com", "me.com", "aol.com", "proton.me", "protonmail.com",
        )):
            return f"{bare_last} ({email})"
        return f"{bare_last} ({orcid})"
    if email:
        return f"{bare_last} ({email})"
    if orcid:
        return f"{bare_last} ({orcid})"
    return bare_last
