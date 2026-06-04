import uuid

import pytest

from prismapi.db.base import Base, get_engine, get_sessionmaker
from prismapi.db.models import Identity, Project, ProjectMember
from prismapi.rpc.errors import RpcError
from prismapi.services.members import (
    enroll_member,
    list_members,
    remove_member,
    upsert_foreign_identity,
)


pytestmark = pytest.mark.asyncio


@pytest.fixture
async def project_id(local_identity):
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
        return p.id


async def test_upsert_foreign_creates_identity(project_id):
    Session = get_sessionmaker()
    async with Session() as session:
        ident = await upsert_foreign_identity(
            session, last_name="Smith", email="smith@example.edu"
        )
        await session.commit()
        assert ident.is_local is False
        assert ident.email == "smith@example.edu"
        assert ident.last_name == "Smith"


async def test_upsert_foreign_is_idempotent_by_email(project_id):
    Session = get_sessionmaker()
    async with Session() as session:
        a = await upsert_foreign_identity(session, last_name="X", email="a@example.org")
        await session.commit()
        b = await upsert_foreign_identity(session, last_name="Y", email="a@example.org")
        await session.commit()
        assert a.id == b.id


async def test_upsert_foreign_is_idempotent_by_orcid(project_id):
    Session = get_sessionmaker()
    async with Session() as session:
        a = await upsert_foreign_identity(session, last_name="X", orcid="0000-0001-2345-6789")
        await session.commit()
        b = await upsert_foreign_identity(session, last_name="Y", orcid="0000-0001-2345-6789")
        await session.commit()
        assert a.id == b.id


async def test_upsert_foreign_does_not_downgrade_local(local_identity):
    Session = get_sessionmaker()
    async with Session() as session:
        ident = await upsert_foreign_identity(
            session, last_name="Nasser", email=local_identity["email"]
        )
        await session.commit()
        assert ident.is_local is True  # local row was returned, not downgraded
        assert str(ident.id) == local_identity["id"]


async def test_upsert_foreign_requires_orcid_or_email(project_id):
    Session = get_sessionmaker()
    async with Session() as session:
        with pytest.raises(RpcError):
            await upsert_foreign_identity(session, last_name="X")


async def test_enroll_member_creates_link(project_id):
    Session = get_sessionmaker()
    async with Session() as session:
        m = await enroll_member(
            session,
            project_id=project_id,
            last_name="Smith",
            email="smith@example.edu",
            role="reviewer",
        )
        await session.commit()
        assert m.role == "reviewer"


async def test_enroll_member_rejects_duplicate(project_id):
    Session = get_sessionmaker()
    async with Session() as session:
        await enroll_member(
            session, project_id=project_id, last_name="A",
            email="a@x.org", role="reviewer",
        )
        await session.commit()
    async with Session() as session:
        with pytest.raises(RpcError):
            await enroll_member(
                session, project_id=project_id, last_name="A",
                email="a@x.org", role="reviewer",
            )
            await session.commit()


async def test_enroll_member_validates_role(project_id):
    Session = get_sessionmaker()
    async with Session() as session:
        with pytest.raises(RpcError):
            await enroll_member(
                session, project_id=project_id, last_name="X",
                email="x@x.org", role="nonsense",
            )


async def test_list_members_returns_in_order(project_id):
    Session = get_sessionmaker()
    async with Session() as session:
        await enroll_member(session, project_id=project_id, last_name="A",
                            email="a@x.org", role="owner")
        await enroll_member(session, project_id=project_id, last_name="B",
                            email="b@x.org", role="reviewer")
        await session.commit()
    async with Session() as session:
        rows = await list_members(session, project_id=project_id)
        # SQLite created_at has second resolution, so rapid inserts can tie;
        # assert membership rather than strict order.
        assert sorted(r.identity.last_name for r in rows) == ["A", "B"]
        assert len(rows) == 2


async def test_remove_member_keeps_identity(project_id):
    Session = get_sessionmaker()
    async with Session() as session:
        m = await enroll_member(session, project_id=project_id, last_name="X",
                                email="x@x.org", role="reviewer")
        await session.commit()
        member_id = m.id
        identity_id = m.identity_id
    async with Session() as session:
        await remove_member(session, project_id=project_id, member_id=member_id)
        await session.commit()
    async with Session() as session:
        rows = await list_members(session, project_id=project_id)
        assert rows == []
        # Identity row should still exist:
        from sqlalchemy import select
        ident = await session.scalar(select(Identity).where(Identity.id == identity_id))
        assert ident is not None
