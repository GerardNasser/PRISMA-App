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
