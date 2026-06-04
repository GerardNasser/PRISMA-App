"""Members RPC tests."""

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


async def test_members_enroll_and_list(dispatcher, project_id):
    enrolled = await dispatcher.call(
        "members.enroll",
        {
            "project_id": project_id,
            "last_name": "Smith",
            "email": "smith@example.edu",
            "role": "reviewer",
        },
    )
    assert enrolled["role"] == "reviewer"
    assert enrolled["identity"]["last_name"] == "Smith"

    listed = await dispatcher.call("members.list", {"project_id": project_id})
    assert len(listed) == 1
    assert listed[0]["identity"]["email"] == "smith@example.edu"


async def test_members_enroll_orcid(dispatcher, project_id):
    enrolled = await dispatcher.call(
        "members.enroll",
        {
            "project_id": project_id,
            "last_name": "Jones",
            "orcid": "0000-0001-2345-6789",
            "role": "owner",
        },
    )
    assert enrolled["role"] == "owner"
    assert enrolled["identity"]["orcid"] == "0000-0001-2345-6789"


async def test_members_enroll_rejects_invalid_role(dispatcher, project_id):
    with pytest.raises(Exception):
        await dispatcher.call(
            "members.enroll",
            {
                "project_id": project_id,
                "last_name": "X",
                "email": "x@x.org",
                "role": "nonsense",
            },
        )


async def test_members_enroll_requires_orcid_or_email(dispatcher, project_id):
    with pytest.raises(Exception):
        await dispatcher.call(
            "members.enroll",
            {
                "project_id": project_id,
                "last_name": "X",
                "role": "reviewer",
            },
        )


async def test_members_remove(dispatcher, project_id):
    enrolled = await dispatcher.call(
        "members.enroll",
        {
            "project_id": project_id,
            "last_name": "X",
            "email": "x@x.org",
            "role": "reviewer",
        },
    )
    await dispatcher.call(
        "members.remove",
        {"project_id": project_id, "member_id": enrolled["id"]},
    )
    listed = await dispatcher.call("members.list", {"project_id": project_id})
    assert listed == []
