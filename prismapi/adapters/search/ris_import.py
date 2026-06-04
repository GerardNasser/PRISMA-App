"""Universal RIS / .nbib / BibTeX-ish import.

For databases where API access is gated (Embase, CINAHL, PsycINFO, Scopus on
some plans). Reviewer exports from the vendor UI and uploads the file.
Provenance on each record reads `imported_ris` instead of `api_fetched`.

Minimal RIS parser — handles the common subset.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator, Iterable

from prismapi.adapters.search.base import SearchAdapter, SearchHit, register_adapter

_TAG_RE = re.compile(r"^([A-Z][A-Z0-9])\s{1,3}-\s?(.*)$")


class RISImportAdapter(SearchAdapter):
    id = "ris_import"
    label = "RIS / .nbib import (any database)"
    requires = ()

    async def search(
        self, query: str, *, max_results: int = 1000, filters: list[str] | None = None
    ) -> AsyncIterator[SearchHit]:
        # The "query" carries the raw RIS payload for this adapter — the
        # API endpoint passes the uploaded file content through.
        for hit in parse_ris(query.splitlines()):
            yield hit


def parse_ris(lines: Iterable[str]) -> list[SearchHit]:
    """Parse a RIS stream into SearchHits. Tolerant of vendor quirks."""
    hits: list[SearchHit] = []
    current: dict[str, list[str]] = {}

    def flush() -> None:
        if not current:
            return
        title = " ".join(current.get("TI") or current.get("T1") or [])
        abstract = " ".join(current.get("AB") or [])
        authors = "; ".join(current.get("AU", []) + current.get("A1", []))
        journal = next(
            iter(current.get("JO") or current.get("JF") or current.get("T2") or []), None
        )
        year = None
        for k in ("PY", "Y1", "DA"):
            for v in current.get(k, []):
                token = v.split("/")[0] if "/" in v else v
                token = token.strip()
                if token.isdigit() and len(token) == 4:
                    year = int(token)
                    break
            if year:
                break
        doi = next(iter(current.get("DO") or current.get("DI") or []), None)
        pmid = None
        for v in current.get("AN", []) + current.get("ID", []):
            if v.isdigit() and 5 <= len(v) <= 9:
                pmid = v
                break
        url = next(iter(current.get("UR") or current.get("L1") or []), None)
        ext = (
            doi
            or pmid
            or next(iter(current.get("ID") or []), None)
            or (title[:80] if title else "ris-unknown")
        )
        hits.append(
            SearchHit(
                external_id=ext,
                database="ris_import",
                title=title,
                abstract=abstract or None,
                authors=authors or None,
                journal=journal,
                year=year,
                doi=doi,
                pmid=pmid,
                publication_type=next(iter(current.get("TY") or []), None),
                language=next(iter(current.get("LA") or []), None),
                url=url,
                raw={k: v for k, v in current.items()},
            )
        )
        current.clear()

    for raw_line in lines:
        line = raw_line.rstrip("\r\n")
        if not line.strip():
            continue
        m = _TAG_RE.match(line)
        if m:
            tag = m.group(1)
            value = m.group(2).strip()
            if tag == "ER":
                flush()
            elif value:
                current.setdefault(tag, []).append(value)
        else:
            # Continuation of last value, append.
            if current:
                last_tag = next(reversed(current))
                current[last_tag][-1] += " " + line.strip()
    flush()
    return hits


register_adapter(RISImportAdapter())
