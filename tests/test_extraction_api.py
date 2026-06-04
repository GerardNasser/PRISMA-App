"""Extraction template + RoB tool RPC tests."""

from __future__ import annotations

import pytest

from prismapi.rpc.errors import RpcError


async def _project_with_cluster(dispatcher, fid: str, branch: dict | None = None) -> tuple[str, str]:
    p = await dispatcher.call(
        "projects.create",
        {"name": "X", "slug": "x", "field_config_id": fid, "branch_choices": branch or {}},
    )
    pid = p["id"]
    ris = "TY  - JOUR\nTI  - Study one\nAU  - A\nPY  - 2022\nDO  - 10.1000/abc\nER  -\n"
    await dispatcher.call(
        "searches.run",
        {"project_id": pid, "database": "ris_import", "query": "x", "payload": ris},
    )
    await dispatcher.call("dedup.run", {"project_id": pid})
    clusters = (await dispatcher.call("dedup.clusters.list", {"project_id": pid}))["clusters"]
    return pid, clusters[0]["id"]


@pytest.mark.asyncio
async def test_omics_template_uses_storms(dispatcher, local_identity):
    pid, _cid = await _project_with_cluster(dispatcher, "health__omics")
    body = await dispatcher.call("extraction.template", {"project_id": pid})
    assert body["base"] == "STORMS"
    keys = {f["key"] for f in body["fields"]}
    # STORMS-flavoured extras
    assert {"primer_or_region", "pipeline", "contamination_controlled"} <= keys


@pytest.mark.asyncio
async def test_economics_template_uses_maer_net(dispatcher, local_identity):
    pid, _cid = await _project_with_cluster(dispatcher, "social__economics")
    body = await dispatcher.call("extraction.template", {"project_id": pid})
    assert body["base"] == "MAER_NET"
    keys = {f["key"] for f in body["fields"]}
    assert {"identification_strategy", "effect_size", "standard_error"} <= keys


@pytest.mark.asyncio
async def test_extraction_draft_save_roundtrip(dispatcher, local_identity):
    pid, cid = await _project_with_cluster(dispatcher, "health__omics")
    out = await dispatcher.call(
        "extraction.save",
        {
            "project_id": pid,
            "cluster_id": cid,
            "status": "draft",
            "payload": {"study_id": "S1"},
        },
    )
    assert out["status"] == "draft"


@pytest.mark.asyncio
async def test_rob_tool_routing_economics_custom(dispatcher, local_identity):
    pid, cid = await _project_with_cluster(dispatcher, "social__economics")
    spec = await dispatcher.call("rob.tool", {"project_id": pid})
    assert spec["tool"] == "CUSTOM"
    keys = {d["key"] for d in spec["domains"]}
    assert "identification" in keys

    out = await dispatcher.call(
        "rob.save",
        {
            "project_id": pid,
            "cluster_id": cid,
            "judgements": {
                "identification": {"judgement": "some_concerns", "justification": "DID"},
                "spec_searching": {"judgement": "low"},
            },
            "overall": "some_concerns",
        },
    )
    assert out["tool"] == "CUSTOM"

    with pytest.raises(RpcError):
        await dispatcher.call(
            "rob.save",
            {
                "project_id": pid,
                "cluster_id": cid,
                "judgements": {"made_up_domain": {"judgement": "low"}},
            },
        )
