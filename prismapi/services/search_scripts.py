"""Generate self-contained Python search scripts and import their results.

The user runs the generated script outside the app — typically in a terminal
or notebook where their API keys are configured. The script produces a JSON
file in the `prismapi-search/1` envelope, which the app re-imports as a
Search + a batch of Records.

This keeps PrismAPI free of network-side complexity: no key vault, no rate
limiter, no retry loop — every database becomes a transparent script the
user can inspect, modify, and re-run.
"""

from __future__ import annotations

import json
import textwrap
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from prismapi.db.models import Project, Record, Search
from prismapi.services.audit import record_audit

OUTPUT_ENVELOPE_VERSION = "prismapi-search/1"


# --------------------------------------------------------------------------
# Script templates per adapter.
# Each template is plain Python that:
#   * declares its query + parameters at the top so the user can edit
#   * uses only stdlib + (where unavoidable) one well-known dependency
#   * writes a JSON file in the prismapi-search/1 envelope
# --------------------------------------------------------------------------


def _safe_repr(value: Any) -> str:
    """Render a value as a Python literal that's safe to inline."""
    return repr(value)


def _common_envelope(query: str, database: str, applied_filters: list[str]) -> str:
    return textwrap.dedent(
        f"""\
        ENVELOPE_VERSION = {_safe_repr(OUTPUT_ENVELOPE_VERSION)}
        DATABASE = {_safe_repr(database)}
        QUERY = {_safe_repr(query)}
        APPLIED_FILTERS = {_safe_repr(applied_filters)}
        """
    )


PUBMED_TEMPLATE = '''\
#!/usr/bin/env python3
"""PrismAPI search script — PubMed (NCBI E-utilities)

Generated for project: {project_label}
Created:              {created_at}

USAGE
-----
1. Set your NCBI credentials (API key is optional but bumps your rate limit):

       export NCBI_EMAIL="you@institution.edu"
       export NCBI_API_KEY="your-api-key"      # optional

2. Run:

       python {script_name}

3. The script writes a JSON file matching the prismapi-search/1 envelope.

4. In the PrismAPI app, open this project's Search tab and click
   "Import results". Pick the JSON file the script just wrote.

Run it on a different machine, in a notebook, or with a modified query —
it never touches the app directly.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

# -- editable parameters --------------------------------------------------
{envelope}
MAX_RESULTS = {max_results}
DATE_FROM = {date_from!r}      # YYYY/MM/DD or "" for no lower bound
DATE_TO   = {date_to!r}        # YYYY/MM/DD or "" for no upper bound
OUTPUT = {output!r}            # where to write results

# -- internals (no API key in source code) --------------------------------
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


def _params(extra: dict) -> str:
    base = {{"tool": "prismapi", "email": os.environ.get("NCBI_EMAIL", "")}}
    if os.environ.get("NCBI_API_KEY"):
        base["api_key"] = os.environ["NCBI_API_KEY"]
    base.update(extra)
    return urllib.parse.urlencode(base)


def _get_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def main() -> int:
    if not os.environ.get("NCBI_EMAIL"):
        print("ERROR: set NCBI_EMAIL in the environment (NCBI requires it).", file=sys.stderr)
        return 1

    term = QUERY
    if DATE_FROM or DATE_TO:
        a = DATE_FROM or "1900/01/01"
        b = DATE_TO or datetime.utcnow().strftime("%Y/%m/%d")
        term = f"({{term}}) AND ({{a}}:{{b}}[dp])"
    for f in APPLIED_FILTERS:
        # PubMed's NOT is binary — "NOT ..." fragments must not be wrapped
        # in an AND clause.
        if f.upper().startswith("NOT "):
            term = f"({{term}}) NOT ({{f[4:]}})"
        else:
            term = f"({{term}}) AND ({{f}})"

    print(f"esearch: {{term[:120]}}...")
    es_url = f"{{EUTILS}}/esearch.fcgi?{{_params({{'db':'pubmed','term':term,'retmax':min(MAX_RESULTS,10000),'usehistory':'y','retmode':'json'}})}}"
    es = _get_json(es_url).get("esearchresult", {{}})
    count = int(es.get("count", 0))
    webenv = es.get("webenv")
    qkey = es.get("querykey")
    print(f"  → {{count}} hits")

    records: list[dict] = []
    batch = 200
    fetched = 0
    while fetched < min(count, MAX_RESULTS):
        sum_url = f"{{EUTILS}}/esummary.fcgi?{{_params({{'db':'pubmed','retmode':'json','retstart':fetched,'retmax':batch,'WebEnv':webenv,'query_key':qkey}})}}"
        s = _get_json(sum_url).get("result", {{}})
        uids = s.get("uids", []) or []
        for uid in uids:
            if len(records) >= MAX_RESULTS:
                break
            item = s.get(uid)
            if not isinstance(item, dict):
                continue
            authors = "; ".join(a.get("name", "") for a in item.get("authors", []) if isinstance(a, dict))
            year = None
            for tok in str(item.get("pubdate", "")).split():
                if tok.isdigit() and len(tok) == 4:
                    year = int(tok)
                    break
            doi = None
            for aid in item.get("articleids", []) or []:
                if isinstance(aid, dict) and aid.get("idtype") == "doi":
                    doi = aid.get("value")
                    break
            records.append({{
                "external_id": uid,
                "database": "pubmed",
                "title": item.get("title", "") or "",
                "abstract": None,    # esummary doesn't include abstract; use efetch if you need it
                "authors": authors or None,
                "journal": item.get("fulljournalname") or item.get("source"),
                "year": year,
                "doi": doi,
                "pmid": uid,
                "publication_type": ", ".join(item.get("pubtype", [])) if isinstance(item.get("pubtype"), list) else None,
                "language": (item.get("lang") or [None])[0] if isinstance(item.get("lang"), list) else item.get("lang"),
                "url": f"https://pubmed.ncbi.nlm.nih.gov/{{uid}}/",
                "raw": item,
            }})
        # Advance by the request window, not the reply size: an empty or
        # short reply must never re-fetch (infinite loop) or skip a window.
        fetched += batch
        time.sleep(0.34)  # NCBI rate limit (3/sec without key)

    out = {{
        "format": ENVELOPE_VERSION,
        "database": DATABASE,
        "query": QUERY,
        "applied_filters": APPLIED_FILTERS,
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "hit_count": len(records),
        "records": records,
    }}
    with open(OUTPUT, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2)
    print(f"wrote {{len(records)}} records → {{OUTPUT}}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''


OPENALEX_TEMPLATE = '''\
#!/usr/bin/env python3
"""PrismAPI search script — OpenAlex

Generated for project: {project_label}
Created:              {created_at}

USAGE
-----
1. (Optional but polite) set:

       export OPENALEX_EMAIL="you@institution.edu"

2. Run:

       python {script_name}

3. Import the resulting JSON into the PrismAPI app from the Search tab.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone

{envelope}
MAX_RESULTS = {max_results}
OUTPUT = {output!r}

BASE = "https://api.openalex.org/works"


def _hit_from_work(w: dict) -> dict:
    inv = w.get("abstract_inverted_index")
    abstract = None
    if isinstance(inv, dict):
        pos: dict[int, str] = {{}}
        for word, idxs in inv.items():
            for i in idxs:
                pos[i] = word
        abstract = " ".join(pos[i] for i in sorted(pos))
    authors = "; ".join(a.get("author", {{}}).get("display_name", "") for a in (w.get("authorships") or []))
    host = (w.get("primary_location") or {{}}).get("source") or {{}}
    return {{
        "external_id": (w.get("id") or "").rsplit("/", 1)[-1],
        "database": "openalex",
        "title": w.get("title") or "",
        "abstract": abstract,
        "authors": authors or None,
        "journal": host.get("display_name"),
        "year": w.get("publication_year"),
        "doi": (w.get("doi") or "").replace("https://doi.org/", "") or None,
        "pmid": (w.get("ids") or {{}}).get("pmid", "").replace("https://pubmed.ncbi.nlm.nih.gov/", "") or None,
        "publication_type": w.get("type"),
        "language": w.get("language"),
        "url": w.get("doi") or w.get("id"),
        "raw": w,
    }}


def main() -> int:
    headers = {{}}
    params = {{"per-page": 200, "search": QUERY}}
    if os.environ.get("OPENALEX_EMAIL"):
        params["mailto"] = os.environ["OPENALEX_EMAIL"]
    if APPLIED_FILTERS:
        # OpenAlex filter expressions (language:en, type:!review) go in the
        # `filter` parameter; inside `search` they match as literal text.
        params["filter"] = ",".join(APPLIED_FILTERS)

    cursor = "*"
    records: list[dict] = []
    while cursor and len(records) < MAX_RESULTS:
        url = f"{{BASE}}?{{urllib.parse.urlencode({{**params, 'cursor': cursor}})}}"
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=60) as r:
            body = json.loads(r.read().decode("utf-8"))
        for w in body.get("results", []):
            records.append(_hit_from_work(w))
            if len(records) >= MAX_RESULTS:
                break
        cursor = body.get("meta", {{}}).get("next_cursor")
        if not body.get("results"):
            break

    out = {{
        "format": ENVELOPE_VERSION,
        "database": DATABASE,
        "query": QUERY,
        "applied_filters": APPLIED_FILTERS,
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "hit_count": len(records),
        "records": records,
    }}
    with open(OUTPUT, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2)
    print(f"wrote {{len(records)}} records → {{OUTPUT}}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''


CROSSREF_TEMPLATE = '''\
#!/usr/bin/env python3
"""PrismAPI search script — CrossRef

Generated for project: {project_label}
Created:              {created_at}

USAGE
-----
1. (Optional) set:

       export OPENALEX_EMAIL="you@institution.edu"   # used in the polite-pool User-Agent

2. Run:

       python {script_name}

3. Import the resulting JSON into the PrismAPI app.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone

{envelope}
MAX_RESULTS = {max_results}
OUTPUT = {output!r}

BASE = "https://api.crossref.org/works"


def main() -> int:
    ua = "prismapi/0.7"
    if os.environ.get("OPENALEX_EMAIL"):
        ua += f" (mailto:{{os.environ['OPENALEX_EMAIL']}})"

    records: list[dict] = []
    cursor = "*"
    per = 200
    while cursor and len(records) < MAX_RESULTS:
        params = {{"query": QUERY, "rows": per, "cursor": cursor}}
        if APPLIED_FILTERS:
            params["filter"] = ",".join(APPLIED_FILTERS)
        url = f"{{BASE}}?{{urllib.parse.urlencode(params)}}"
        req = urllib.request.Request(url, headers={{"User-Agent": ua}})
        with urllib.request.urlopen(req, timeout=60) as r:
            body = json.loads(r.read().decode("utf-8"))
        msg = body.get("message", {{}})
        items = msg.get("items", [])
        if not items:
            break
        for item in items:
            title = " ".join(item.get("title") or [])
            authors = "; ".join(
                f"{{a.get('family', '')}} {{a.get('given', '')}}".strip()
                for a in (item.get("author") or [])
            )
            issued = (item.get("issued") or {{}}).get("date-parts") or [[None]]
            year = issued[0][0] if issued and issued[0] else None
            records.append({{
                "external_id": item.get("DOI", ""),
                "database": "crossref",
                "title": title,
                "abstract": item.get("abstract"),
                "authors": authors or None,
                "journal": (item.get("container-title") or [None])[0],
                "year": year,
                "doi": item.get("DOI"),
                "pmid": None,
                "publication_type": item.get("type"),
                "language": item.get("language"),
                "url": item.get("URL"),
                "raw": item,
            }})
            if len(records) >= MAX_RESULTS:
                break
        cursor = msg.get("next-cursor")

    out = {{
        "format": ENVELOPE_VERSION,
        "database": DATABASE,
        "query": QUERY,
        "applied_filters": APPLIED_FILTERS,
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "hit_count": len(records),
        "records": records,
    }}
    with open(OUTPUT, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2)
    print(f"wrote {{len(records)}} records → {{OUTPUT}}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''


GENERIC_TEMPLATE = '''\
#!/usr/bin/env python3
"""PrismAPI search script — {database}

Generated for project: {project_label}
Created:              {created_at}

This is a stub for a database PrismAPI doesn't ship a built-in fetcher for.

WHAT TO DO
----------
1. Replace the `fetch_records()` function below with whatever API / vendor
   client retrieves results from {database}. Append each record to the
   `records` list using the schema shown.
2. Run the script.
3. Import the resulting JSON file back into PrismAPI.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone

{envelope}
MAX_RESULTS = {max_results}
OUTPUT = {output!r}


def fetch_records() -> list[dict]:
    """Implement this. Each record must match the schema below.

    Required keys:  external_id, database, title
    Recommended:    authors, year, journal, doi, pmid, url, abstract
    """
    raise NotImplementedError(
        "Edit this script to fetch records from {database} and return them as a list."
    )


def main() -> int:
    try:
        records = fetch_records()
    except NotImplementedError as exc:
        print(f"ERROR: {{exc}}", file=sys.stderr)
        return 1
    out = {{
        "format": ENVELOPE_VERSION,
        "database": DATABASE,
        "query": QUERY,
        "applied_filters": APPLIED_FILTERS,
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "hit_count": len(records),
        "records": records,
    }}
    with open(OUTPUT, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2)
    print(f"wrote {{len(records)}} records → {{OUTPUT}}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''


_TEMPLATES = {
    "pubmed": PUBMED_TEMPLATE,
    "openalex": OPENALEX_TEMPLATE,
    "crossref": CROSSREF_TEMPLATE,
}


def generate_script(
    *,
    database: str,
    project_label: str,
    project_slug: str,
    query: str,
    applied_filters: list[str] | None = None,
    max_results: int = 1000,
    date_from: str = "",
    date_to: str = "",
    output_path: str | None = None,
) -> dict[str, str]:
    """Return {script: str, suggested_filename: str, suggested_output: str}."""
    applied_filters = applied_filters or []
    timestamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    script_name = f"{project_slug}_{database}_{timestamp}.py"
    output = output_path or f"{project_slug}_{database}_{timestamp}.json"
    tpl = _TEMPLATES.get(database, GENERIC_TEMPLATE)
    envelope = _common_envelope(query, database, applied_filters)
    body = tpl.format(
        project_label=project_label,
        project_slug=project_slug,
        database=database,
        script_name=script_name,
        envelope=envelope,
        max_results=max_results,
        date_from=date_from,
        date_to=date_to,
        output=output,
        created_at=datetime.now(tz=UTC).isoformat(),
    )
    return {
        "script": body,
        "suggested_filename": script_name,
        "suggested_output": output,
    }


# --------------------------------------------------------------------------
# Importer
# --------------------------------------------------------------------------


_REQUIRED_RECORD_FIELDS = {"external_id", "title"}


async def import_results(
    session: AsyncSession,
    *,
    project: Project,
    actor_identity_id: uuid.UUID | None,
    input_path: Path,
) -> dict[str, Any]:
    """Read a `prismapi-search/1` JSON file and persist Search + Records."""
    raw = json.loads(input_path.read_text(encoding="utf-8"))
    fmt = raw.get("format")
    if fmt != OUTPUT_ENVELOPE_VERSION:
        raise ValueError(f"Unrecognised file format: {fmt!r}")
    database = raw.get("database") or "external"
    query = raw.get("query") or ""
    applied_filters = raw.get("applied_filters") or []
    records = raw.get("records") or []

    search = Search(
        project_id=project.id,
        actor_identity_id=actor_identity_id,
        database=database,
        query_string=query,
        applied_filters=applied_filters,
        options={"imported_from": str(input_path), "envelope": fmt},
        status="completed",
        executed_at=datetime.now(tz=UTC),
        hit_count=0,
    )
    session.add(search)
    await session.flush()

    seen_ids: set[str] = set()
    inserted = 0
    skipped = 0
    for r in records:
        if not isinstance(r, dict):
            skipped += 1
            continue
        missing = _REQUIRED_RECORD_FIELDS - r.keys()
        if missing:
            skipped += 1
            continue
        external_id = str(r["external_id"])
        if external_id in seen_ids:
            continue
        seen_ids.add(external_id)
        session.add(
            Record(
                project_id=project.id,
                search_id=search.id,
                database=r.get("database") or database,
                external_id=external_id,
                doi=r.get("doi") or None,
                pmid=r.get("pmid") or None,
                title=str(r["title"])[:32000],
                abstract=r.get("abstract"),
                authors=r.get("authors"),
                journal=r.get("journal"),
                year=r.get("year") if isinstance(r.get("year"), int) else None,
                publication_type=r.get("publication_type"),
                language=r.get("language"),
                url=r.get("url"),
                raw=r.get("raw") or {},
            )
        )
        inserted += 1
    search.hit_count = inserted

    await record_audit(
        session,
        project_id=project.id,
        actor_identity_id=actor_identity_id,
        action="search.import_results",
        entity_type="search",
        entity_id=str(search.id),
        payload={
            "database": database,
            "envelope": fmt,
            "inserted": inserted,
            "skipped": skipped,
            "input_path": str(input_path),
        },
    )
    await session.commit()
    await session.refresh(search)
    return {
        "search_id": str(search.id),
        "database": database,
        "inserted": inserted,
        "skipped": skipped,
        "hit_count": inserted,
    }
