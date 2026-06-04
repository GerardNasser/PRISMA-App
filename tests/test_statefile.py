"""End-to-end .prismaproj tests: export → preview → merge.

These exercise the row-level diff rules described in
`apps/core/src/prismapi/statefile/diff.py`.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import zipfile
from pathlib import Path

import pytest


async def _seed_project(dispatcher, field="health__omics", branch=None) -> str:
    p = await dispatcher.call(
        "projects.create",
        {
            "name": "Plant microbiome MA",
            "slug": "plant-ma",
            "field_config_id": field,
            "branch_choices": branch or {},
        },
    )
    pid = p["id"]
    ris = (
        "TY  - JOUR\nTI  - Study one\nAU  - A\nPY  - 2022\nDO  - 10.1000/abc\nER  -\n"
        "TY  - JOUR\nTI  - Study two\nAU  - B\nPY  - 2023\nDO  - 10.1000/xyz\nER  -\n"
    )
    await dispatcher.call(
        "searches.run",
        {"project_id": pid, "database": "ris_import", "query": "u", "payload": ris},
    )
    await dispatcher.call("dedup.run", {"project_id": pid})
    return pid


@pytest.mark.asyncio
async def test_export_round_trip_into_fresh_db(dispatcher, local_identity):
    """Export a populated project, then import the same bundle into a fresh
    DB and assert the project is reconstructed with no conflicts."""
    pid = await _seed_project(dispatcher)
    await dispatcher.call(
        "protocols.save",
        {"project_id": pid, "title": "v1", "pico": {"P": "Indoor"}},
    )
    await dispatcher.call(
        "codebooks.save",
        {
            "project_id": pid,
            "rules": [{"code": "INC", "direction": "include", "rationale": "in"}],
        },
    )

    clusters = (await dispatcher.call("dedup.clusters.list", {"project_id": pid}))["clusters"]
    cid = clusters[0]["id"]
    await dispatcher.call(
        "screening.decision",
        {"project_id": pid, "cluster_id": cid, "stage": "title_abstract", "decision": "include"},
    )

    out_path = Path(tempfile.mkdtemp()) / "demo.prismaproj"
    res = await dispatcher.call(
        "statefile.export", {"project_id": pid, "output_path": str(out_path)}
    )
    assert out_path.exists()
    assert res["manifest"]["project_id"] == pid

    # Verify manifest checksums match actual content bytes.
    with zipfile.ZipFile(out_path) as zf:
        manifest = json.loads(zf.read("manifest.json"))
        for fc in manifest["files"]:
            actual = hashlib.sha256(zf.read(fc["relative_path"])).hexdigest()
            assert actual == fc["sha256"], fc["relative_path"]

    # Wipe the DB (drop + recreate) and import.
    from prismapi.db.base import Base, get_engine, get_sessionmaker
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    # Re-create the local identity (which was wiped).
    from prismapi.services.identity import upsert_local_identity

    Session = get_sessionmaker()
    async with Session() as session:
        await upsert_local_identity(
            session,
            last_name="Nasser",
            orcid=None,
            email="gerard@example.edu",
            institution="Example",
        )

    preview = await dispatcher.call(
        "statefile.preview_import", {"input_path": str(out_path)}
    )
    assert preview["diff"]["project_present_locally"] is False
    assert preview["diff"]["counts_added"]["project"] == 1
    assert preview["diff"]["counts_added"]["records"] == 2
    assert preview["diff"]["counts_added"]["screenings"] == 1

    merged = await dispatcher.call(
        "statefile.merge",
        {"input_path": str(out_path), "take_pre_import_snapshot": False},
    )
    assert merged["summary"]["added"]["records"] == 2
    assert merged["summary"]["added"]["screenings"] == 1

    proj = await dispatcher.call("projects.get", {"project_id": pid})
    assert proj["name"] == "Plant microbiome MA"

    shutil.rmtree(out_path.parent)


@pytest.mark.asyncio
async def test_idempotent_reimport(dispatcher, local_identity):
    """Importing the same bundle twice should be a no-op the second time."""
    pid = await _seed_project(dispatcher)
    out_path = Path(tempfile.mkdtemp()) / "x.prismaproj"
    await dispatcher.call(
        "statefile.export", {"project_id": pid, "output_path": str(out_path)}
    )
    preview = await dispatcher.call(
        "statefile.preview_import", {"input_path": str(out_path)}
    )
    # Already present locally → nothing new.
    assert preview["diff"]["project_present_locally"] is True
    counts_added = preview["diff"]["counts_added"]
    # Records / clusters / searches were already present.
    assert counts_added.get("records", 0) == 0
    assert counts_added.get("clusters", 0) == 0
    assert not preview["diff"]["conflicts"]
    shutil.rmtree(out_path.parent)


@pytest.mark.asyncio
async def test_unsupported_schema_version_rejected(dispatcher, local_identity, tmp_path):
    """A bundle declaring a future schema_version must refuse import."""
    pid = await _seed_project(dispatcher)
    src = tmp_path / "src.prismaproj"
    await dispatcher.call(
        "statefile.export", {"project_id": pid, "output_path": str(src)}
    )

    # Repack with a bogus schema_version=999 in the manifest.
    fake = tmp_path / "bad.prismaproj"
    with zipfile.ZipFile(src, "r") as src_zf:
        manifest = json.loads(src_zf.read("manifest.json"))
        manifest["schema_version"] = 999
        with zipfile.ZipFile(fake, "w", zipfile.ZIP_DEFLATED) as dst_zf:
            for n in src_zf.namelist():
                if n == "manifest.json":
                    dst_zf.writestr("manifest.json", json.dumps(manifest))
                else:
                    dst_zf.writestr(n, src_zf.read(n))

    from prismapi.rpc.errors import RpcError

    with pytest.raises(RpcError):
        await dispatcher.call("statefile.preview_import", {"input_path": str(fake)})


@pytest.mark.asyncio
async def test_protocol_parallel_bump_surfaces_conflict(
    dispatcher, local_identity, tmp_path
):
    """Two installs both bump protocol v1 → v2 with different bodies."""
    pid = await _seed_project(dispatcher)
    await dispatcher.call(
        "protocols.save",
        {"project_id": pid, "title": "Local v1", "pico": {"P": "Local"}},
    )
    src = tmp_path / "src.prismaproj"
    await dispatcher.call(
        "statefile.export", {"project_id": pid, "output_path": str(src)}
    )

    # Inject a divergent v1 into a copy of the bundle (simulating the other side).
    fake = tmp_path / "their.prismaproj"
    with zipfile.ZipFile(src, "r") as src_zf:
        protocols = [
            json.loads(line)
            for line in src_zf.read("protocols.jsonl").decode("utf-8").splitlines()
            if line.strip()
        ]
        their_protocol = dict(protocols[0])
        their_protocol["id"] = "11111111-1111-1111-1111-111111111111"
        their_protocol["title"] = "Their v1 (different)"
        their_protocol["pico"] = {"P": "Other population"}
        out_lines = "\n".join(json.dumps(p, sort_keys=True) for p in [their_protocol]) + "\n"
        with zipfile.ZipFile(fake, "w", zipfile.ZIP_DEFLATED) as dst_zf:
            for n in src_zf.namelist():
                if n == "protocols.jsonl":
                    dst_zf.writestr(n, out_lines)
                else:
                    dst_zf.writestr(n, src_zf.read(n))

    # Validation rejects checksum mismatch; for the test we recompute manifest hashes.
    with zipfile.ZipFile(fake, "r") as zf:
        manifest = json.loads(zf.read("manifest.json"))
    for fc in manifest["files"]:
        with zipfile.ZipFile(fake, "r") as zf:
            payload = zf.read(fc["relative_path"])
        fc["sha256"] = hashlib.sha256(payload).hexdigest()
        fc["size_bytes"] = len(payload)
    repaired = tmp_path / "their_repaired.prismaproj"
    with zipfile.ZipFile(fake, "r") as src_zf:
        with zipfile.ZipFile(repaired, "w", zipfile.ZIP_DEFLATED) as dst_zf:
            for n in src_zf.namelist():
                if n == "manifest.json":
                    dst_zf.writestr("manifest.json", json.dumps(manifest))
                else:
                    dst_zf.writestr(n, src_zf.read(n))

    preview = await dispatcher.call(
        "statefile.preview_import", {"input_path": str(repaired)}
    )
    conflicts = preview["diff"]["conflicts"]
    assert any(c["kind"] == "protocol_parallel" for c in conflicts)


@pytest.mark.asyncio
async def test_merge_refuses_when_conflicts_unresolved(
    dispatcher, local_identity, tmp_path
):
    """A merge with a parallel bump must fail until the user picks a resolution."""
    pid = await _seed_project(dispatcher)
    await dispatcher.call(
        "protocols.save",
        {"project_id": pid, "title": "Local v1"},
    )
    src = tmp_path / "src.prismaproj"
    await dispatcher.call(
        "statefile.export", {"project_id": pid, "output_path": str(src)}
    )
    # Hand-build a divergent bundle the same way as above.
    fake = tmp_path / "bad.prismaproj"
    with zipfile.ZipFile(src, "r") as src_zf:
        protocols = [
            json.loads(line)
            for line in src_zf.read("protocols.jsonl").decode("utf-8").splitlines()
            if line.strip()
        ]
        their = dict(protocols[0])
        their["id"] = "22222222-2222-2222-2222-222222222222"
        their["title"] = "Diverged"
        out_lines = json.dumps(their, sort_keys=True) + "\n"
        with zipfile.ZipFile(fake, "w", zipfile.ZIP_DEFLATED) as dst_zf:
            for n in src_zf.namelist():
                if n == "protocols.jsonl":
                    dst_zf.writestr(n, out_lines)
                else:
                    dst_zf.writestr(n, src_zf.read(n))
    # Fix checksums.
    with zipfile.ZipFile(fake, "r") as zf:
        manifest = json.loads(zf.read("manifest.json"))
    for fc in manifest["files"]:
        with zipfile.ZipFile(fake, "r") as zf:
            payload = zf.read(fc["relative_path"])
        fc["sha256"] = hashlib.sha256(payload).hexdigest()
        fc["size_bytes"] = len(payload)
    repaired = tmp_path / "repaired.prismaproj"
    with zipfile.ZipFile(fake, "r") as src_zf, zipfile.ZipFile(repaired, "w", zipfile.ZIP_DEFLATED) as dst_zf:
        for n in src_zf.namelist():
            if n == "manifest.json":
                dst_zf.writestr("manifest.json", json.dumps(manifest))
            else:
                dst_zf.writestr(n, src_zf.read(n))

    from prismapi.rpc.errors import RpcError

    with pytest.raises(RpcError):
        await dispatcher.call(
            "statefile.merge",
            {
                "input_path": str(repaired),
                "resolutions": {},
                "take_pre_import_snapshot": False,
            },
        )
