"""Snapshot RPC tests (Layer-4 safety)."""

from __future__ import annotations

import pytest


async def _make(dispatcher) -> str:
    p = await dispatcher.call(
        "projects.create",
        {
            "name": "T",
            "slug": "t",
            "field_config_id": "social__economics",
            "branch_choices": {},
        },
    )
    return p["id"]


@pytest.mark.asyncio
async def test_create_and_list(dispatcher, local_identity):
    pid = await _make(dispatcher)
    s = await dispatcher.call(
        "snapshots.create", {"project_id": pid, "label": "Before edits"}
    )
    assert s["kind"] == "manual"
    listed = await dispatcher.call("snapshots.list", {"project_id": pid})
    assert len(listed["snapshots"]) == 1


@pytest.mark.asyncio
async def test_auto_cap_evicts_old(dispatcher, local_identity, monkeypatch):
    """Auto-kind snapshots beyond the cap are pruned; manual ones survive."""
    from prismapi import config

    cfg = config.get_settings()
    monkeypatch.setattr(cfg, "snapshot_auto_cap", 2)

    pid = await _make(dispatcher)
    for i in range(4):
        await dispatcher.call(
            "snapshots.create",
            {"project_id": pid, "label": f"auto {i}", "kind": "auto_on_open"},
        )
    await dispatcher.call(
        "snapshots.create",
        {"project_id": pid, "label": "manual one", "kind": "manual"},
    )

    listed = (await dispatcher.call("snapshots.list", {"project_id": pid}))["snapshots"]
    auto_count = sum(1 for s in listed if s["kind"] == "auto_on_open")
    manual_count = sum(1 for s in listed if s["kind"] == "manual")
    assert auto_count == 2
    assert manual_count == 1
