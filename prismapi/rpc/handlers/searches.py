"""Searches RPC: adapter catalog, filter library, run, list, records."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pathlib import Path

from prismapi.adapters.filters import list_filters
from prismapi.adapters.search import list_adapters
from prismapi.db.models import Project, ProjectMember, Record, Search
from prismapi.rpc.dispatcher import rpc
from prismapi.rpc.errors import NOT_FOUND, VALIDATION, RpcError
from prismapi.services.search import execute_search, pairwise_keyword_matrix
from prismapi.services.search_scripts import (
    generate_script as _generate_script,
    import_results as _import_results,
)


async def _assert_member(
    session: AsyncSession, project_id: uuid.UUID, identity_id: uuid.UUID
) -> Project:
    project = await session.get(Project, project_id)
    if project is None:
        raise RpcError(NOT_FOUND, "Project not found")
    if project.owner_identity_id == identity_id:
        return project
    member = await session.scalar(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.identity_id == identity_id,
        )
    )
    if member is None:
        raise RpcError(NOT_FOUND, "Project not found")
    return project


@rpc("searches.adapters")
async def adapters() -> dict:
    return {
        "adapters": [
            {"id": a.id, "label": a.label, "requires": list(a.requires)}
            for a in list_adapters()
        ]
    }


@rpc("searches.filters")
async def filters() -> dict:
    return {
        "filters": [
            {
                "id": f.id,
                "label": f.label,
                "description": f.description,
                "citation": f.citation,
                "supported_adapters": sorted(f.fragments.keys()),
            }
            for f in list_filters()
        ]
    }


class PairwiseIn(BaseModel):
    groups: list[list[str]] = Field(min_length=2)


@rpc("searches.pairwise_matrix")
async def pairwise(params: PairwiseIn) -> dict:
    return {"pairs": pairwise_keyword_matrix(params.groups)}


class SearchRunIn(BaseModel):
    project_id: str
    database: str
    query: str = Field(min_length=1)
    applied_filters: list[str] = Field(default_factory=list)
    max_results: int = Field(default=1000, ge=1, le=10000)
    options: dict = Field(default_factory=dict)
    payload: str | None = None


def _search_out(s: Search) -> dict:
    return {
        "id": str(s.id),
        "project_id": str(s.project_id),
        "database": s.database,
        "query_string": s.query_string,
        "applied_filters": s.applied_filters,
        "status": s.status,
        "error": s.error,
        "hit_count": s.hit_count,
        "executed_at": s.executed_at.isoformat() if s.executed_at else None,
        "created_at": s.created_at.isoformat(),
    }


@rpc("searches.run")
async def run(
    params: SearchRunIn, session: AsyncSession, identity_id: uuid.UUID
) -> dict:
    project = await _assert_member(session, uuid.UUID(params.project_id), identity_id)
    search = await execute_search(
        session,
        project=project,
        user_id=identity_id,
        database=params.database,
        query=params.query,
        applied_filters=params.applied_filters,
        max_results=params.max_results,
        options=params.options,
        payload=params.payload,
    )
    return _search_out(search)


class SearchList(BaseModel):
    project_id: str


@rpc("searches.list")
async def list_(
    params: SearchList, session: AsyncSession, identity_id: uuid.UUID
) -> dict:
    project = await _assert_member(session, uuid.UUID(params.project_id), identity_id)
    rows = await session.execute(
        select(Search)
        .where(Search.project_id == project.id, Search.deleted_at.is_(None))
        .order_by(Search.created_at.desc())
    )
    return {"searches": [_search_out(s) for s in rows.scalars().all()]}


class RecordsList(BaseModel):
    project_id: str
    search_id: str
    limit: int = 200
    offset: int = 0


@rpc("searches.records")
async def records(
    params: RecordsList, session: AsyncSession, identity_id: uuid.UUID
) -> dict:
    project = await _assert_member(session, uuid.UUID(params.project_id), identity_id)
    rows = await session.execute(
        select(Record)
        .where(Record.search_id == uuid.UUID(params.search_id), Record.project_id == project.id)
        .order_by(Record.created_at.asc())
        .offset(params.offset)
        .limit(params.limit)
    )
    return {
        "records": [
            {
                "id": str(r.id),
                "search_id": str(r.search_id),
                "database": r.database,
                "external_id": r.external_id,
                "doi": r.doi,
                "pmid": r.pmid,
                "title": r.title,
                "abstract": r.abstract,
                "authors": r.authors,
                "journal": r.journal,
                "year": r.year,
                "publication_type": r.publication_type,
                "language": r.language,
                "url": r.url,
            }
            for r in rows.scalars().all()
        ]
    }


# ---- script generator + results importer ---------------------------------

class ScriptIn(BaseModel):
    project_id: str
    database: str
    query: str = Field(min_length=1)
    applied_filters: list[str] = Field(default_factory=list)
    max_results: int = Field(default=1000, ge=1, le=20000)
    date_from: str = ""
    date_to: str = ""
    output_path: str | None = None


@rpc("searches.generate_script")
async def generate_script(
    params: ScriptIn, session: AsyncSession, identity_id: uuid.UUID
) -> dict:
    project = await _assert_member(session, uuid.UUID(params.project_id), identity_id)
    res = _generate_script(
        database=params.database,
        project_label=project.name,
        project_slug=project.slug,
        query=params.query,
        applied_filters=params.applied_filters,
        max_results=params.max_results,
        date_from=params.date_from,
        date_to=params.date_to,
        output_path=params.output_path,
    )
    return res


class ImportIn(BaseModel):
    project_id: str
    input_path: str


@rpc("searches.import_results")
async def import_results(
    params: ImportIn, session: AsyncSession, identity_id: uuid.UUID
) -> dict:
    project = await _assert_member(session, uuid.UUID(params.project_id), identity_id)
    path = Path(params.input_path).expanduser()
    if not path.exists():
        raise RpcError(VALIDATION, f"No such file: {path}")
    try:
        return await _import_results(
            session,
            project=project,
            actor_identity_id=identity_id,
            input_path=path,
        )
    except ValueError as exc:
        raise RpcError(VALIDATION, str(exc)) from exc
