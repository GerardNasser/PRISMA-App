"""CrossRef — DOI-grounded metadata. Excellent dedup anchor."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import httpx

from prismapi.adapters.search.base import SearchAdapter, SearchHit, register_adapter
from prismapi.config import get_settings

BASE = "https://api.crossref.org/works"


class CrossRefAdapter(SearchAdapter):
    id = "crossref"
    label = "CrossRef"
    requires = ()

    async def search(
        self, query: str, *, max_results: int = 1000, filters: list[str] | None = None
    ) -> AsyncIterator[SearchHit]:
        settings = get_settings()
        headers = {}
        ua = "prismapi/0.1"
        if settings.openalex_email:
            ua += f" (mailto:{settings.openalex_email})"
        headers["User-Agent"] = ua

        per_page = 200
        cursor = "*"
        fetched = 0
        async with httpx.AsyncClient(timeout=30.0, headers=headers) as client:
            while fetched < max_results and cursor:
                params: dict[str, Any] = {
                    "query": query,
                    "rows": per_page,
                    "cursor": cursor,
                }
                for f in filters or []:
                    params["filter"] = (
                        (params.get("filter") + "," if params.get("filter") else "") + f
                    )
                r = await client.get(BASE, params=params)
                r.raise_for_status()
                body = r.json().get("message", {})
                items = body.get("items", [])
                if not items:
                    break
                for item in items:
                    yield _hit_from_item(item)
                    fetched += 1
                    if fetched >= max_results:
                        return
                cursor = body.get("next-cursor")


def _hit_from_item(item: dict[str, Any]) -> SearchHit:
    title = " ".join(item.get("title", []))
    authors = "; ".join(
        f"{a.get('family', '')} {a.get('given', '')}".strip()
        for a in (item.get("author") or [])
        if isinstance(a, dict)
    )
    issued = item.get("issued", {}).get("date-parts") or [[None]]
    year = issued[0][0] if issued and issued[0] else None
    return SearchHit(
        external_id=item.get("DOI", ""),
        database="crossref",
        title=title,
        abstract=item.get("abstract"),
        authors=authors or None,
        journal=(item.get("container-title") or [None])[0],
        year=year,
        doi=item.get("DOI"),
        pmid=None,
        publication_type=item.get("type"),
        language=item.get("language"),
        url=item.get("URL"),
        raw=item,
    )


register_adapter(CrossRefAdapter())
