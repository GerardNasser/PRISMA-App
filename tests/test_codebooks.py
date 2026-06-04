"""Codebook RPC tests."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_codebook_versioning(dispatcher, local_identity):
    p = await dispatcher.call(
        "projects.create",
        {
            "name": "Econ wage MA",
            "slug": "econ-wage",
            "field_config_id": "social__economics",
            "branch_choices": {},
        },
    )
    pid = p["id"]
    v1 = await dispatcher.call(
        "codebooks.save",
        {
            "project_id": pid,
            "notes": "Initial",
            "rules": [
                {"code": "INC-RCT", "direction": "include", "rationale": "Randomised only"},
                {"code": "EXC-NO-SE", "direction": "exclude", "rationale": "ES w/o SE"},
            ],
        },
    )
    assert v1["version"] == 1
    assert len(v1["rules"]) == 2

    v2 = await dispatcher.call(
        "codebooks.save",
        {"project_id": pid, "notes": "v2", "rules": [v1["rules"][0]]},
    )
    assert v2["version"] == 2
    assert len(v2["rules"]) == 1

    latest = await dispatcher.call("codebooks.latest", {"project_id": pid})
    assert latest["version"] == 2

    versions = await dispatcher.call("codebooks.versions", {"project_id": pid})
    assert [c["version"] for c in versions["versions"]] == [1, 2]
