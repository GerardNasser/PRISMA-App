"""Field registry tests — Dispatcher-driven."""

from __future__ import annotations

import pytest

from prismapi.fields.loader import FieldRegistry


def test_registry_loads_and_validates():
    reg = FieldRegistry()
    reg.load()
    configs = reg.all()
    assert len(configs) >= 6
    ids = {c.id for c in configs}
    # Spot-check the broader catalogue we ship.
    assert "health__omics" in ids
    assert "social__economics" in ids
    assert "health__intervention" in ids
    assert "general__custom" in ids


def test_health_omics_config_shape():
    reg = FieldRegistry()
    reg.load()
    cfg = reg.by_id("health__omics")
    assert cfg is not None
    assert cfg.data["modules"]["microbiome_pipeline"] is True
    assert cfg.data["extraction_template"]["base"] == "STORMS"


def test_economics_config_defaults_to_maive():
    reg = FieldRegistry()
    reg.load()
    cfg = reg.by_id("social__economics")
    assert cfg is not None
    assert cfg.data["effect_sizes"]["default"] == "pcc"
    assert "maive" in cfg.data["publication_bias"]["required_methods"]
    assert cfg.data["publication_bias"]["mandatory"] is True


@pytest.mark.asyncio
async def test_dispatcher_lists_fields(dispatcher):
    body = await dispatcher.call("fields.list", {})
    fields = {f["field"] for f in body["fields"]}
    assert {"health", "social"} <= fields


@pytest.mark.asyncio
async def test_dispatcher_unknown_config_returns_not_found(dispatcher):
    from prismapi.rpc.errors import RpcError

    with pytest.raises(RpcError):
        await dispatcher.call("fields.config.get", {"config_id": "doesnotexist"})
