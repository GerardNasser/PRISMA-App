"""Audit log service."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from prismapi.db.models.audit import AuditLog


async def record_audit(
    session: AsyncSession,
    *,
    project_id: uuid.UUID | None,
    actor_identity_id: uuid.UUID | None,
    action: str,
    entity_type: str,
    entity_id: str | None = None,
    payload: dict | None = None,
) -> AuditLog:
    """Append one audit-log row; flushed, not committed."""
    row = AuditLog(
        project_id=project_id,
        actor_identity_id=actor_identity_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        payload=payload or {},
    )
    session.add(row)
    await session.flush()
    return row
