"""Identity RPC: first-run setup and later-edit support."""

from __future__ import annotations

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from prismapi.db.models.identity import Identity
from prismapi.rpc.dispatcher import rpc
from prismapi.services.identity import get_local_identity, upsert_local_identity


class IdentityIn(BaseModel):
    last_name: str
    orcid: str | None = None
    email: str | None = None
    institution: str | None = None


def _serialise(identity: Identity) -> dict:
    return {
        "id": str(identity.id),
        "last_name": identity.last_name,
        "orcid": identity.orcid,
        "email": identity.email,
        "institution": identity.institution,
        "display_name": identity.display_name,
        "is_local": identity.is_local,
    }


@rpc("identity.get")
async def get(session: AsyncSession) -> dict | None:
    identity = await get_local_identity(session)
    return _serialise(identity) if identity else None


@rpc("identity.set")
async def set_(params: IdentityIn, session: AsyncSession) -> dict:
    identity = await upsert_local_identity(
        session,
        last_name=params.last_name,
        orcid=params.orcid,
        email=params.email,
        institution=params.institution,
    )
    return _serialise(identity)
