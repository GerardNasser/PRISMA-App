"""Local identity service.

The local install has exactly one Identity with `is_local=True`. Created
once at first run via `identity.set`. All actor attributions reference it.
"""

from __future__ import annotations

import re
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from prismapi.db.base import get_sessionmaker
from prismapi.db.models.identity import ORCID_PATTERN, Identity, render_display_name
from prismapi.rpc.errors import IDENTITY_NEEDED, VALIDATION, RpcError


async def get_local_identity(session: AsyncSession) -> Identity | None:
    """Return the install's local identity row, or None before onboarding."""
    return await session.scalar(
        select(Identity).where(Identity.is_local.is_(True)).order_by(Identity.created_at.asc())
    )


async def current_identity_id() -> uuid.UUID:
    """Resolve the current actor for handler-injection. Raises if no identity
    has been configured (first-run UI is responsible for prompting)."""
    Session = get_sessionmaker()
    async with Session() as session:
        identity = await get_local_identity(session)
    if identity is None:
        raise RpcError(IDENTITY_NEEDED, "Run identity.set first")
    return identity.id


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _normalise_orcid(s: str | None) -> str | None:
    if not s:
        return None
    s = s.strip().replace(" ", "").upper()
    if not re.match(ORCID_PATTERN, s):
        raise RpcError(VALIDATION, "ORCID must look like 0000-0001-2345-6789", {"field": "orcid"})
    return s


def _normalise_email(s: str | None) -> str | None:
    if not s:
        return None
    s = s.strip()
    if not _EMAIL_RE.match(s):
        raise RpcError(VALIDATION, "Email looks malformed", {"field": "email"})
    return s


async def upsert_local_identity(
    session: AsyncSession,
    *,
    last_name: str,
    orcid: str | None,
    email: str | None,
    institution: str | None,
) -> Identity:
    """Create or update the local identity; requires ORCID or email."""
    last_name = last_name.strip()
    if not last_name:
        raise RpcError(VALIDATION, "Last name is required", {"field": "last_name"})
    orcid = _normalise_orcid(orcid)
    email = _normalise_email(email)
    if not orcid and not email:
        raise RpcError(
            VALIDATION,
            "Provide an ORCID or an affiliate email (university/work email recommended)",
            {"fields": ["orcid", "email"]},
        )
    display = render_display_name(last_name, orcid, email, institution)
    existing = await get_local_identity(session)
    if existing is None:
        identity = Identity(
            last_name=last_name,
            orcid=orcid,
            email=email,
            institution=institution,
            display_name=display,
            is_local=True,
        )
        session.add(identity)
        await session.flush()
    else:
        existing.last_name = last_name
        existing.orcid = orcid
        existing.email = email
        existing.institution = institution
        existing.display_name = display
        identity = existing
    await session.commit()
    return identity
