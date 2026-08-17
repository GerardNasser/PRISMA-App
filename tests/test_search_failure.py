"""A failed search run must leave a committed failed Search row behind."""

from __future__ import annotations

import pytest

import prismapi.services.search as search_service
from prismapi.rpc.errors import RpcError

pytestmark = pytest.mark.asyncio


class _ExplodingAdapter:
    database = "pubmed"

    async def search(self, query, *, max_results=1000, filters=None):
        raise RuntimeError("simulated adapter outage")
        yield  # pragma: no cover - makes this an async generator


async def test_failed_search_is_persisted(dispatcher, local_identity, monkeypatch):
    p = await dispatcher.call(
        "projects.create",
        {
            "name": "T",
            "slug": "t",
            "field_config_id": "general__custom",
            "branch_choices": {},
        },
    )
    pid = p["id"]

    monkeypatch.setattr(
        search_service, "resolve_adapter", lambda database: _ExplodingAdapter()
    )
    with pytest.raises(RpcError):
        await dispatcher.call(
            "searches.run",
            {"project_id": pid, "database": "pubmed", "query": "anything"},
        )

    searches = (await dispatcher.call("searches.list", {"project_id": pid}))["searches"]
    assert len(searches) == 1
    assert searches[0]["status"] == "failed"
    assert "simulated adapter outage" in searches[0]["error"]


async def test_failed_search_records_auto_filters(dispatcher, local_identity, monkeypatch):
    # health__intervention auto-applies the Cochrane RCT filter; the failed
    # attempt must record it (as "auto:<id>") or it cannot be reproduced.
    p = await dispatcher.call(
        "projects.create",
        {
            "name": "F",
            "slug": "f",
            "field_config_id": "health__intervention",
            "branch_choices": {},
        },
    )
    monkeypatch.setattr(
        search_service, "resolve_adapter", lambda database: _ExplodingAdapter()
    )
    with pytest.raises(RpcError):
        await dispatcher.call(
            "searches.run",
            {"project_id": p["id"], "database": "pubmed", "query": "anything"},
        )
    searches = (await dispatcher.call("searches.list", {"project_id": p["id"]}))["searches"]
    assert searches[0]["applied_filters"] == ["auto:cochrane_rct_pubmed"]


async def test_generated_script_embeds_resolved_filters(dispatcher, local_identity, tmp_path):
    p = await dispatcher.call(
        "projects.create",
        {
            "name": "G",
            "slug": "g",
            "field_config_id": "general__custom",
            "branch_choices": {},
        },
    )
    res = await dispatcher.call(
        "searches.generate_script",
        {
            "project_id": p["id"],
            "database": "pubmed",
            "query": "plants[tiab]",
            "applied_filters": ["english_language", "exclude_reviews"],
            "output_path": str(tmp_path / "script.py"),
        },
    )
    script = res["script"] if "script" in res else (tmp_path / "script.py").read_text()
    # Resolved fragments, never raw filter ids.
    assert "english[lang]" in script
    assert "review[pt]" in script
    assert "'english_language'" not in script
