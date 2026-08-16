"""Project-member enrollment service.

Wraps Identity + ProjectMember to support the lead-pre-enrolls-raters flow.
Foreign identities (is_local=False) are created idempotently by orcid/email
so the same person enrolled across multiple projects shares one Identity row.
"""

from __future__ import annotations

import re
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from prismapi.db.models.identity import ORCID_PATTERN, Identity, render_display_name
from prismapi.db.models.project import ProjectMember
from prismapi.rpc.errors import VALIDATION, RpcError

_VALID_ROLES = {"owner", "reviewer", "read_only"}
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _normalise_orcid(s: str | None) -> str | None:
    if not s:
        return None
    s = s.strip().replace(" ", "").upper()
    if not re.match(ORCID_PATTERN, s):
        raise RpcError(
            VALIDATION, "ORCID must look like 0000-0001-2345-6789", {"field": "orcid"}
        )
    return s


def _normalise_email(s: str | None) -> str | None:
    if not s:
        return None
    s = s.strip()
    if not _EMAIL_RE.match(s):
        raise RpcError(VALIDATION, "Email looks malformed", {"field": "email"})
    return s


async def upsert_foreign_identity(
    session: AsyncSession,
    *,
    last_name: str,
    orcid: str | None = None,
    email: str | None = None,
    institution: str | None = None,
) -> Identity:
    """Find an identity by normalised ORCID/email, or create a foreign one."""
    last_name = last_name.strip()
    if not last_name:
        raise RpcError(VALIDATION, "Last name is required", {"field": "last_name"})
    orcid = _normalise_orcid(orcid)
    email = _normalise_email(email)
    if not orcid and not email:
        raise RpcError(
            VALIDATION,
            "Provide an ORCID or an affiliate email",
            {"fields": ["orcid", "email"]},
        )
    existing = None
    if orcid:
        existing = await session.scalar(
            select(Identity).where(Identity.orcid == orcid)
        )
    if existing is None and email:
        existing = await session.scalar(
            select(Identity).where(Identity.email == email)
        )
    if existing is not None:
        return existing
    identity = Identity(
        last_name=last_name,
        orcid=orcid,
        email=email,
        institution=institution,
        display_name=render_display_name(last_name, orcid, email, institution),
        is_local=False,
    )
    session.add(identity)
    await session.flush()
    return identity


async def enroll_member(
    session: AsyncSession,
    *,
    project_id: uuid.UUID,
    last_name: str,
    orcid: str | None = None,
    email: str | None = None,
    institution: str | None = None,
    role: str,
) -> ProjectMember:
    """Add an identity to a project's roster; rejects duplicates and bad roles."""
    if role not in _VALID_ROLES:
        raise RpcError(
            VALIDATION,
            f"role must be one of {sorted(_VALID_ROLES)}",
            {"field": "role"},
        )
    identity = await upsert_foreign_identity(
        session,
        last_name=last_name,
        orcid=orcid,
        email=email,
        institution=institution,
    )
    existing = await session.scalar(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.identity_id == identity.id,
        )
    )
    if existing is not None:
        raise RpcError(
            VALIDATION,
            "Identity already enrolled in this project",
            {"project_id": str(project_id), "identity_id": str(identity.id)},
        )
    member = ProjectMember(
        project_id=project_id, identity_id=identity.id, role=role,
    )
    session.add(member)
    await session.flush()
    return member


async def list_members(
    session: AsyncSession, *, project_id: uuid.UUID,
) -> list[ProjectMember]:
    """All membership rows for a project, identity attached."""
    rows = await session.scalars(
        select(ProjectMember)
        .where(ProjectMember.project_id == project_id)
        .order_by(ProjectMember.created_at)
    )
    return list(rows)


async def remove_member(
    session: AsyncSession, *, project_id: uuid.UUID, member_id: uuid.UUID,
) -> None:
    """Delete one membership row by member id."""
    member = await session.scalar(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.id == member_id,
        )
    )
    if member is None:
        return
    await session.delete(member)
