"""Identity onboarding RPC tests."""

from __future__ import annotations

import pytest

from prismapi.rpc.errors import RpcError


@pytest.mark.asyncio
async def test_get_returns_none_before_first_run(dispatcher):
    assert await dispatcher.call("identity.get") is None


@pytest.mark.asyncio
async def test_set_requires_one_of_orcid_or_email(dispatcher):
    with pytest.raises(RpcError) as ex:
        await dispatcher.call(
            "identity.set",
            {"last_name": "Nasser", "orcid": None, "email": None},
        )
    assert "ORCID or" in ex.value.message


@pytest.mark.asyncio
async def test_set_with_email_only(dispatcher):
    out = await dispatcher.call(
        "identity.set",
        {
            "last_name": "Nasser",
            "email": "gerard@uncc.edu",
            "institution": "UNC Charlotte",
        },
    )
    assert out["display_name"] == "Nasser (gerard@uncc.edu)"
    assert out["email"] == "gerard@uncc.edu"
    assert out["is_local"] is True


@pytest.mark.asyncio
async def test_set_with_orcid_only(dispatcher):
    out = await dispatcher.call(
        "identity.set",
        {
            "last_name": "Wood",
            "orcid": "0000-0001-2345-6789",
        },
    )
    assert "0000-0001-2345-6789" in out["display_name"]
    assert out["orcid"] == "0000-0001-2345-6789"


@pytest.mark.asyncio
async def test_set_rejects_bad_orcid(dispatcher):
    with pytest.raises(RpcError):
        await dispatcher.call(
            "identity.set", {"last_name": "X", "orcid": "0000-0001-XXXX-XXXX"}
        )


@pytest.mark.asyncio
async def test_set_prefers_institutional_email_for_display(dispatcher):
    # When both ORCID and a generic email are provided, ORCID wins (gmail is not
    # an institution).
    out = await dispatcher.call(
        "identity.set",
        {
            "last_name": "Nasser",
            "orcid": "0000-0001-2345-6789",
            "email": "gerard@gmail.com",
        },
    )
    assert "0000-0001-2345-6789" in out["display_name"]

    # When both are provided and email looks institutional, email wins.
    out2 = await dispatcher.call(
        "identity.set",
        {
            "last_name": "Nasser",
            "orcid": "0000-0001-2345-6789",
            "email": "gerard@uncc.edu",
        },
    )
    assert "gerard@uncc.edu" in out2["display_name"]


@pytest.mark.asyncio
async def test_set_is_upsert(dispatcher):
    await dispatcher.call("identity.set", {"last_name": "A", "email": "a@example.org"})
    out = await dispatcher.call("identity.set", {"last_name": "B", "email": "b@example.org"})
    assert out["last_name"] == "B"
    listed = await dispatcher.call("identity.get")
    assert listed["last_name"] == "B"
