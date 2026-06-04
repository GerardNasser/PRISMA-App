"""Audit coverage — every mutating RPC writes an audit row.

This locks down the invariant that mutating RPC methods leave an AuditLog
trail. Read-only methods are intentionally NOT exercised here.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import func, select

from prismapi.db.base import Base, get_engine, get_sessionmaker
from prismapi.db.models import AuditLog, Project


pytestmark = pytest.mark.asyncio


async def _audit_count() -> int:
    Session = get_sessionmaker()
    async with Session() as session:
        return (await session.scalar(select(func.count(AuditLog.id)))) or 0


async def _latest_actions(n: int = 5) -> list[str]:
    Session = get_sessionmaker()
    async with Session() as session:
        rows = (
            await session.execute(
                select(AuditLog.action).order_by(AuditLog.created_at.desc()).limit(n)
            )
        ).scalars().all()
        return list(rows)


@pytest.fixture
async def project_id(dispatcher, local_identity):
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = get_sessionmaker()
    async with Session() as session:
        p = Project(
            name="P",
            slug="p",
            owner_identity_id=uuid.UUID(local_identity["id"]),
            field_config_id="general__custom",
            field_config_version="1.0",
        )
        session.add(p)
        await session.commit()
        return str(p.id)


# ---- members ----------------------------------------------------------------


async def test_members_enroll_writes_audit(dispatcher, project_id):
    before = await _audit_count()
    await dispatcher.call(
        "members.enroll",
        {
            "project_id": project_id,
            "last_name": "X",
            "email": "x@x.org",
            "role": "reviewer",
        },
    )
    after = await _audit_count()
    assert after > before
    assert "members.enroll" in await _latest_actions()


async def test_members_remove_writes_audit(dispatcher, project_id):
    enrolled = await dispatcher.call(
        "members.enroll",
        {
            "project_id": project_id,
            "last_name": "X",
            "email": "x@x.org",
            "role": "reviewer",
        },
    )
    before = await _audit_count()
    await dispatcher.call(
        "members.remove",
        {"project_id": project_id, "member_id": enrolled["id"]},
    )
    after = await _audit_count()
    assert after > before
    assert "members.remove" in await _latest_actions()
