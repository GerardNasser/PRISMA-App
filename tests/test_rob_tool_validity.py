"""Every RoB tool a shipped config can select must resolve to a real spec."""

from __future__ import annotations

import pytest

from prismapi.fields.loader import field_registry
from prismapi.fields.validate import check_rob_tools
from prismapi.services.extraction import BUILTIN_ROB_TOOLS, resolve_rob_spec

def test_every_shipped_tool_resolves():
    field_registry.load()
    for cfg in field_registry.all():
        rob = cfg.data["risk_of_bias"]
        choices_under_test = [{}]
        by_choice = rob.get("tool_by_choice") or {}
        for value in by_choice.get("map", {}):
            choices_under_test.append({by_choice["choice_key"]: value})
        for branch_choices in choices_under_test:
            spec = resolve_rob_spec(cfg, branch_choices)
            assert spec["domains"] or spec["tool"] == "NONE", (
                f"{cfg.id} with {branch_choices} resolved to a domainless tool"
            )


def _doctored(cfg, rob: dict):
    return type(cfg).from_dict({**cfg.data, "risk_of_bias": rob})


def test_validator_flags_unimplemented_tool():
    field_registry.load()
    cfg = field_registry.by_id("qualitative__synthesis")
    errors = check_rob_tools([_doctored(cfg, {"tool": "WWC_5"})])
    assert any("no builtin spec" in e for e in errors)


def test_validator_flags_dead_map_keys():
    field_registry.load()
    cfg = field_registry.by_id("health__intervention")
    rob = {
        **cfg.data["risk_of_bias"],
        "tool_by_choice": {
            "choice_key": "primary_design",
            "map": {"typo_design": "RoB_2"},
        },
    }
    errors = check_rob_tools([_doctored(cfg, rob)])
    assert any("not values of branch choice" in e for e in errors)


@pytest.mark.asyncio
async def test_qualitative_synthesis_rob_tool_resolves(dispatcher, local_identity):
    # CASP_QUAL had no builtin spec, so this call crashed with
    # "Unknown built-in RoB tool" while CI validation stayed green.
    p = await dispatcher.call(
        "projects.create",
        {
            "name": "Q",
            "slug": "q",
            "field_config_id": "qualitative__synthesis",
            "branch_choices": {},
        },
    )
    spec = await dispatcher.call("rob.tool", {"project_id": p["id"]})
    assert spec["tool"] == "CASP_QUAL"
    assert len(spec["domains"]) == 10
