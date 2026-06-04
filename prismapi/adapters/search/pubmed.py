"""PubMed via NCBI E-utilities (esearch + esummary)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import httpx

from prismapi.adapters.search.base import (
    SearchAdapter,
    SearchAdapterError,
    SearchHit,
    register_adapter,
)
from prismapi.config import get_settings

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


class PubMedAdapter(SearchAdapter):
    id = "pubmed"
    label = "PubMed (NCBI E-utilities)"
    requires = ("NCBI_EMAIL",)

    async def search(
        self, query: str, *, max_results: int = 1000, filters: list[str] | None = None
    ) -> AsyncIterator[SearchHit]:
        settings = get_settings()
        if not settings.ncbi_email:
            raise SearchAdapterError("NCBI_EMAIL is required for PubMed adapter")
        params_base: dict[str, Any] = {
            "tool": "prismapi",
            "email": settings.ncbi_email,
        }
        if settings.ncbi_api_key:
            params_base["api_key"] = settings.ncbi_api_key

        # Apply auto-filters as ANDed term groups in the query.
        full_query = query
        for f in filters or []:
            full_query = f"({full_query}) AND ({f})"

        async with httpx.AsyncClient(timeout=30.0) as client:
            esearch_params = {
                **params_base,
                "db": "pubmed",
                "term": full_query,
                "retmax": str(min(max_results, 10000)),
                "retmode": "json",
                "usehistory": "y",
            }
            r = await client.get(f"{EUTILS}/esearch.fcgi", params=esearch_params)
            r.raise_for_status()
            data = r.json()
            esearchresult = data.get("esearchresult", {})
            id_list: list[str] = esearchresult.get("idlist", [])
            webenv = esearchresult.get("webenv")
            query_key = esearchresult.get("querykey")
            if not id_list:
                return

            # Batch summary fetch
            batch_size = 200
            for start in range(0, min(len(id_list), max_results), batch_size):
                params = {
                    **params_base,
                    "db": "pubmed",
                    "retmode": "json",
                    "retstart": str(start),
                    "retmax": str(batch_size),
                    "WebEnv": webenv,
                    "query_key": query_key,
                }
                resp = await client.get(f"{EUTILS}/esummary.fcgi", params=params)
                resp.raise_for_status()
                summaries = resp.json().get("result", {})
                uids = summaries.get("uids", [])
                for uid in uids:
                    item = summaries.get(uid)
                    if not isinstance(item, dict):
                        continue
                    yield _hit_from_esummary(uid, item)


def _hit_from_esummary(pmid: str, item: dict[str, Any]) -> SearchHit:
    authors_field = item.get("authors") or []
    authors = "; ".join(a.get("name", "") for a in authors_field if isinstance(a, dict))
    year: int | None = None
    pubdate = item.get("pubdate") or ""
    for token in str(pubdate).split():
        if token.isdigit() and len(token) == 4:
            year = int(token)
            break
    doi = None
    for aid in item.get("articleids") or []:
        if isinstance(aid, dict) and aid.get("idtype") == "doi":
            doi = aid.get("value")
            break
    return SearchHit(
        external_id=pmid,
        database="pubmed",
        title=item.get("title", "") or "",
        authors=authors or None,
        journal=item.get("fulljournalname") or item.get("source"),
        year=year,
        doi=doi,
        pmid=pmid,
        publication_type=(
            ", ".join(item.get("pubtype", [])) if isinstance(item.get("pubtype"), list) else None
        ),
        language=(
            ", ".join(item.get("lang", [])) if isinstance(item.get("lang"), list) else None
        ),
        url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
        raw=item,
    )


register_adapter(PubMedAdapter())
