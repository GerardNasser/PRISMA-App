"""Projects + protocol + soft-delete RPC tests."""

from __future__ import annotations

import pytest

from prismapi.rpc.errors import RpcError


@pytest.mark.asyncio
async def test_create_rejects_unknown_field_config(dispatcher, local_identity):
    with pytest.raises(RpcError):
        await dispatcher.call(
            "projects.create",
            {
                "name": "Bogus",
                "slug": "bogus",
                "field_config_id": "does_not_exist",
                "branch_choices": {},
            },
        )


@pytest.mark.asyncio
async def test_create_and_versioned_protocol(dispatcher, local_identity):
    p = await dispatcher.call(
        "projects.create",
        {
            "name": "Plant microbiome MA",
            "slug": "plant-ma",
            "field_config_id": "health__omics",
            "branch_choices": {},
        },
    )
    pid = p["id"]
    assert p["field_config_version"] == "0.3.0"
    assert p["deleted_at"] is None

    pv1 = await dispatcher.call(
        "protocols.save",
        {
            "project_id": pid,
            "title": "Indoor plants and the built-environment microbiome",
            "pico": {"P": "Built env", "I": "Plants", "C": "No plants", "O": "16S diversity"},
        },
    )
    assert pv1["version"] == 1

    pv2 = await dispatcher.call(
        "protocols.save",
        {"project_id": pid, "title": "Revised", "pico": {"P": "Built env, revised"}},
    )
    assert pv2["version"] == 2

    versions = await dispatcher.call("protocols.versions", {"project_id": pid})
    assert [p["version"] for p in versions["versions"]] == [1, 2]

    latest = await dispatcher.call("protocols.latest", {"project_id": pid})
    assert latest["version"] == 2


@pytest.mark.asyncio
async def test_soft_delete_and_restore(dispatcher, local_identity):
    p = await dispatcher.call(
        "projects.create",
        {
            "name": "Doomed",
            "slug": "doomed",
            "field_config_id": "social__economics",
            "branch_choices": {},
        },
    )
    pid = p["id"]
    after = await dispatcher.call("projects.soft_delete", {"project_id": pid})
    assert after["deleted_at"] is not None

    listed = await dispatcher.call("projects.list", {"include_trash": False})
    assert all(p2["id"] != pid for p2 in listed["projects"])

    listed_trash = await dispatcher.call("projects.list", {"include_trash": True})
    assert any(p2["id"] == pid for p2 in listed_trash["projects"])

    after_restore = await dispatcher.call("projects.restore", {"project_id": pid})
    assert after_restore["deleted_at"] is None
    listed_again = await dispatcher.call("projects.list", {"include_trash": False})
    assert any(p2["id"] == pid for p2 in listed_again["projects"])
