"""OpenAlex — free, broad scholarly index. Use as fallback / cross-check."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import httpx

from prismapi.adapters.search.base import (
    SearchAdapter,
    SearchHit,
    register_adapter,
)
from prismapi.config import get_settings

BASE = "https://api.openalex.org"


class OpenAlexAdapter(SearchAdapter):
    id = "openalex"
    label = "OpenAlex"
    requires = ()

    async def search(
        self, query: str, *, max_results: int = 1000, filters: list[str] | None = None
    ) -> AsyncIterator[SearchHit]:
        settings = get_settings()
        headers = {}
        params_base: dict[str, Any] = {"per-page": 200, "search": query}
        if settings.openalex_email:
            params_base["mailto"] = settings.openalex_email
        # Fragments like "language:en" are OpenAlex filter expressions. They
        # belong in the `filter` parameter (comma = AND) — inside `search`
        # they are matched as literal text and restrict nothing.
        if filters:
            params_base["filter"] = ",".join(filters)

        cursor = "*"
        fetched = 0
        async with httpx.AsyncClient(timeout=30.0, headers=headers) as client:
            while fetched < max_results and cursor:
                params = {**params_base, "cursor": cursor}
                r = await client.get(f"{BASE}/works", params=params)
                r.raise_for_status()
                body = r.json()
                results = body.get("results", [])
                if not results:
                    break
                for work in results:
                    yield _hit_from_work(work)
                    fetched += 1
                    if fetched >= max_results:
                        return
                cursor = body.get("meta", {}).get("next_cursor")


def _hit_from_work(w: dict[str, Any]) -> SearchHit:
    title = w.get("title") or ""
    abstract = None
    inv = w.get("abstract_inverted_index")
    if isinstance(inv, dict):
        positions: dict[int, str] = {}
        for word, idxs in inv.items():
            for i in idxs:
                positions[i] = word
        abstract = " ".join(positions[i] for i in sorted(positions))
    authors = "; ".join(
        a.get("author", {}).get("display_name", "")
        for a in (w.get("authorships") or [])
        if isinstance(a, dict)
    )
    host = (w.get("primary_location") or {}).get("source") or {}
    return SearchHit(
        external_id=w.get("id", "").rsplit("/", 1)[-1],
        database="openalex",
        title=title,
        abstract=abstract,
        authors=authors or None,
        journal=host.get("display_name"),
        year=w.get("publication_year"),
        doi=(w.get("doi") or "").replace("https://doi.org/", "") or None,
        pmid=(w.get("ids") or {}).get("pmid", "").replace("https://pubmed.ncbi.nlm.nih.gov/", "") or None,
        publication_type=w.get("type"),
        language=w.get("language"),
        url=(w.get("doi") or w.get("id")) or None,
        raw=w,
    )


register_adapter(OpenAlexAdapter())
