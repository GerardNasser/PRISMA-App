"""Search execution service: runs a search adapter and persists results."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from prismapi.adapters.filters import get_filter
from prismapi.adapters.search import resolve_adapter
from prismapi.db.base import utcnow
from prismapi.db.models import Project, Record, Search
from prismapi.fields.loader import field_registry
from prismapi.services.audit import record_audit


async def execute_search(
    session: AsyncSession,
    *,
    project: Project,
    user_id: uuid.UUID,
    database: str,
    query: str,
    applied_filters: list[str] | None = None,
    max_results: int = 1000,
    options: dict | None = None,
    payload: str | None = None,
) -> Search:
    """Execute a search and persist hits as Records under one Search row."""
    adapter = resolve_adapter(database)
    # Captured up front: session.rollback() in the failure path expires the
    # ORM instance, and touching project.id afterwards would lazy-load sync.
    project_id = project.id
    cfg = field_registry.by_id(project.field_config_id)
    auto_filters: list[str] = []
    if cfg is not None:
        for fid in cfg.data.get("databases", {}).get("auto_filters", []):
            f = get_filter(fid)
            if f is None:
                continue
            frag = f.fragment_for(database)
            if frag:
                auto_filters.append(frag)
    user_filters = applied_filters or []
    all_filter_fragments: list[str] = []
    for fid in user_filters:
        f = get_filter(fid)
        if f is None:
            continue
        frag = f.fragment_for(database)
        if frag:
            all_filter_fragments.append(frag)
    all_filter_fragments.extend(auto_filters)

    search = Search(
        project_id=project.id,
        actor_identity_id=user_id,
        database=database,
        query_string=query,
        applied_filters=user_filters + [f"auto:{fid}" for fid in (cfg.data.get("databases", {}).get("auto_filters", []) if cfg else [])],
        options=options or {},
        status="running",
        executed_at=utcnow(),
    )
    session.add(search)
    await session.flush()

    hit_count = 0
    try:
        # `ris_import` adapter encodes its payload via the query arg.
        effective_query = payload if database == "ris_import" and payload else query
        async for hit in adapter.search(
            effective_query, max_results=max_results, filters=all_filter_fragments
        ):
            session.add(
                Record(
                    project_id=project.id,
                    search_id=search.id,
                    database=hit.database,
                    external_id=hit.external_id,
                    doi=hit.doi,
                    pmid=hit.pmid,
                    title=hit.title,
                    abstract=hit.abstract,
                    authors=hit.authors,
                    journal=hit.journal,
                    year=hit.year,
                    publication_type=hit.publication_type,
                    language=hit.language,
                    url=hit.url,
                    raw=hit.raw,
                )
            )
            hit_count += 1
            if hit_count % 500 == 0:
                await session.flush()
        search.status = "completed"
        search.hit_count = hit_count
    except Exception as exc:  # noqa: BLE001 - the attempt itself must be recorded
        # Discard partial hits, then persist the failed attempt in its own
        # transaction — PRISMA-S requires failed searches to leave a trace,
        # and re-raising alone would have the dispatcher roll everything back.
        await session.rollback()
        failed = Search(
            project_id=project_id,
            actor_identity_id=user_id,
            database=database,
            query_string=query,
            applied_filters=user_filters,
            options=options or {},
            status="failed",
            error=str(exc),
            executed_at=utcnow(),
            hit_count=0,
        )
        session.add(failed)
        await session.flush()
        await record_audit(
            session,
            project_id=project_id,
            actor_identity_id=user_id,
            action="search.fail",
            entity_type="search",
            entity_id=str(failed.id),
            payload={
                "database": database,
                "error": str(exc),
                "hits_before_failure": hit_count,
            },
        )
        await session.commit()
        raise

    await record_audit(
        session,
        project_id=project.id,
        actor_identity_id=user_id,
        action="search.complete",
        entity_type="search",
        entity_id=str(search.id),
        payload={"database": database, "hits": hit_count},
    )
    await session.commit()
    await session.refresh(search)
    return search


def pairwise_keyword_matrix(groups: list[list[str]]) -> list[list[str]]:
    """Build the pairwise AND combinations Gerard's Rmd `combn()` produces.

    Each group is OR-joined; pairs of groups are AND-joined.
    Returns a list of query strings.
    """
    or_terms = [" OR ".join(f'"{w}"' for w in g) for g in groups]
    pairs: list[list[str]] = []
    for i in range(len(or_terms)):
        for j in range(i + 1, len(or_terms)):
            pairs.append([or_terms[i], or_terms[j]])
    return pairs
