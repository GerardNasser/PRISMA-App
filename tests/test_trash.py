"""Trash RPC tests (Layer-2 safety)."""

from __future__ import annotations

import pytest

from prismapi.rpc.errors import RpcError


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
async def test_soft_delete_via_trash_handler(dispatcher, local_identity):
    pid = await _make(dispatcher)
    out = await dispatcher.call(
        "trash.soft_delete", {"entity_type": "project", "entity_id": pid}
    )
    assert out["deleted_at"] is not None

    listed = await dispatcher.call("trash.list", {"project_id": pid})
    assert any(p["id"] == pid for p in listed["project"])


@pytest.mark.asyncio
async def test_restore(dispatcher, local_identity):
    pid = await _make(dispatcher)
    await dispatcher.call(
        "trash.soft_delete", {"entity_type": "project", "entity_id": pid}
    )
    after = await dispatcher.call(
        "trash.restore", {"entity_type": "project", "entity_id": pid}
    )
    assert after["deleted_at"] is None


@pytest.mark.asyncio
async def test_empty_requires_DELETE_confirm(dispatcher, local_identity):
    pid = await _make(dispatcher)
    await dispatcher.call(
        "trash.soft_delete", {"entity_type": "project", "entity_id": pid}
    )
    with pytest.raises(RpcError):
        await dispatcher.call("trash.empty", {"confirm": "no", "project_id": pid})
    out = await dispatcher.call(
        "trash.empty", {"confirm": "DELETE", "project_id": pid}
    )
    assert out["deleted"]["project"] == 1


@pytest.mark.asyncio
async def test_unsupported_entity_type_rejected(dispatcher, local_identity):
    with pytest.raises(RpcError):
        await dispatcher.call(
            "trash.soft_delete",
            {"entity_type": "nope", "entity_id": "00000000-0000-0000-0000-000000000000"},
        )
