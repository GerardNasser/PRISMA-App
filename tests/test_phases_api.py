"""phases.state RPC tests — sidebar gate state per phase."""

from __future__ import annotations

import uuid

import pytest

from prismapi.db.base import Base, get_engine, get_sessionmaker
from prismapi.db.models import Project


pytestmark = pytest.mark.asyncio


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


async def test_phases_state_returns_all_phases(dispatcher, project_id):
    result = await dispatcher.call("phases.state", {"project_id": project_id})
    assert isinstance(result, list)
    phases = {entry["phase"]: entry for entry in result}
    expected = {
        "setup", "protocol", "import", "codebook", "dedup",
        "title_abstract", "full_text", "extraction", "rob",
        "synthesis", "report",
    }
    assert set(phases.keys()) == expected
    for entry in result:
        assert set(entry.keys()) == {"phase", "open", "reason"}


async def test_phases_state_locks_title_abstract_until_dedup(dispatcher, project_id):
    result = await dispatcher.call("phases.state", {"project_id": project_id})
    phases = {entry["phase"]: entry for entry in result}
    assert phases["setup"]["open"] is True
    assert phases["title_abstract"]["open"] is False
    assert phases["title_abstract"]["reason"]  # non-empty
