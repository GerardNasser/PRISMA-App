"""The RoB instrument must follow the project's primary_design choice."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio


async def _create(dispatcher, config_id, branch_choices):
    p = await dispatcher.call(
        "projects.create",
        {
            "name": "T",
            "slug": f"t-{config_id.replace('_', '-')}-{len(branch_choices)}",
            "field_config_id": config_id,
            "branch_choices": branch_choices,
        },
    )
    return p["id"]


async def test_psychology_correlational_gets_quips(dispatcher, local_identity):
    pid = await _create(
        dispatcher, "social__psychology", {"primary_design": "correlational"}
    )
    spec = await dispatcher.call("rob.tool", {"project_id": pid})
    assert spec["tool"] == "QUIPS"
    assert any(d["key"] == "confounding" for d in spec["domains"])


async def test_intervention_quasi_experimental_gets_robins_i(dispatcher, local_identity):
    pid = await _create(
        dispatcher, "health__intervention", {"primary_design": "quasi_experimental"}
    )
    spec = await dispatcher.call("rob.tool", {"project_id": pid})
    assert spec["tool"] == "ROBINS_I"


async def test_unmapped_choice_falls_back_to_default_tool(dispatcher, local_identity):
    pid = await _create(dispatcher, "health__intervention", {})
    spec = await dispatcher.call("rob.tool", {"project_id": pid})
    assert spec["tool"] == "RoB_2"


async def test_ecology_tool_is_study_level_custom(dispatcher, local_identity):
    pid = await _create(dispatcher, "environmental__ecology", {})
    spec = await dispatcher.call("rob.tool", {"project_id": pid})
    # CEESAT (a review-level appraisal tool) was wired here before — it also
    # had no builtin spec, so this call crashed outright.
    assert spec["tool"] == "CUSTOM"
    assert {d["key"] for d in spec["domains"]} >= {"confounding", "selection", "attrition"}
