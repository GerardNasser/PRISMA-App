"""Statefile hardening: members round-trip, tamper rejection, honest merges."""

from __future__ import annotations

import json
import shutil
import zipfile

import pytest

from prismapi.rpc.errors import RpcError

pytestmark = pytest.mark.asyncio


_RIS = """\
TY  - JOUR
TI  - Indoor plants modulate microbiome
AU  - Smith, J
PY  - 2023
DO  - 10.1000/test.42
ER  -
"""


async def _seed_project(dispatcher, slug="src"):
    p = await dispatcher.call(
        "projects.create",
        {
            "name": "Source",
            "slug": slug,
            "field_config_id": "general__custom",
            "branch_choices": {},
        },
    )
    pid = p["id"]
    await dispatcher.call(
        "members.enroll",
        {
            "project_id": pid,
            "last_name": "Colleague",
            "email": "colleague@example.edu",
            "role": "reviewer",
        },
    )
    await dispatcher.call(
        "searches.run",
        {"project_id": pid, "database": "ris_import", "query": "u", "payload": _RIS},
    )
    return pid


async def test_members_travel_with_the_bundle(dispatcher, local_identity, tmp_path):
    pid = await _seed_project(dispatcher)
    out = tmp_path / "src.prismaproj"
    res = await dispatcher.call(
        "statefile.export", {"project_id": pid, "output_path": str(out)}
    )
    assert res["manifest"]["counts"]["members"] == 2

    with zipfile.ZipFile(out) as zf:
        lines = [
            json.loads(line)
            for line in zf.read("members.jsonl").decode().splitlines()
            if line
        ]
    assert len(lines) == 2
    roles = sorted(m["role"] for m in lines)
    assert roles == ["owner", "reviewer"]


async def test_tampered_bundle_extra_file_rejected(dispatcher, local_identity, tmp_path):
    pid = await _seed_project(dispatcher)
    out = tmp_path / "src.prismaproj"
    await dispatcher.call("statefile.export", {"project_id": pid, "output_path": str(out)})

    tampered = tmp_path / "tampered.prismaproj"
    shutil.copy(out, tampered)
    with zipfile.ZipFile(tampered, "a") as zf:
        zf.writestr("sneaky.jsonl", '{"x": 1}\n')

    with pytest.raises(RpcError) as exc:
        await dispatcher.call("statefile.preview_import", {"input_path": str(tampered)})
    assert "not listed in the manifest" in str(exc.value)


async def test_count_mismatch_rejected(dispatcher, local_identity, tmp_path):
    pid = await _seed_project(dispatcher)
    out = tmp_path / "src.prismaproj"
    await dispatcher.call("statefile.export", {"project_id": pid, "output_path": str(out)})

    # Rewrite the manifest with a wrong record count (re-signing the file
    # entries so only the count check can object).
    doctored = tmp_path / "doctored.prismaproj"
    with zipfile.ZipFile(out) as zin, zipfile.ZipFile(doctored, "w") as zout:
        for name in zin.namelist():
            payload = zin.read(name)
            if name == "manifest.json":
                man = json.loads(payload)
                man["counts"]["records"] = 99
                payload = json.dumps(man).encode()
            zout.writestr(name, payload)

    with pytest.raises(RpcError) as exc:
        await dispatcher.call("statefile.preview_import", {"input_path": str(doctored)})
    assert "counts do not match" in str(exc.value)


async def test_protocol_parallel_keep_incoming_lands_on_max_version(
    dispatcher, local_identity, tmp_path
):
    pid = await _seed_project(dispatcher)
    await dispatcher.call(
        "protocols.save", {"project_id": pid, "title": "Shared v1"}
    )
    out = tmp_path / "src.prismaproj"
    await dispatcher.call("statefile.export", {"project_id": pid, "output_path": str(out)})

    # Doctor the bundle into "another install's" copy: same project, but its
    # v1 protocol has a different id and body (a parallel bump), while local
    # has advanced to v3 in the meantime.
    doctored = tmp_path / "other.prismaproj"
    import hashlib
    import uuid as uuid_mod

    with zipfile.ZipFile(out) as zin:
        files = {n: zin.read(n) for n in zin.namelist()}
    protocols = [
        json.loads(line) for line in files["protocols.jsonl"].decode().splitlines() if line
    ]
    protocols[0]["id"] = str(uuid_mod.uuid4())
    protocols[0]["title"] = "Divergent v1 from the other install"
    files["protocols.jsonl"] = ("".join(
        json.dumps(p, sort_keys=True, separators=(",", ":")) + "\n" for p in protocols
    )).encode()
    man = json.loads(files["manifest.json"])
    for fc in man["files"]:
        if fc["relative_path"] == "protocols.jsonl":
            fc["sha256"] = hashlib.sha256(files["protocols.jsonl"]).hexdigest()
            fc["size_bytes"] = len(files["protocols.jsonl"])
    files["manifest.json"] = json.dumps(man).encode()
    with zipfile.ZipFile(doctored, "w") as zout:
        for name, payload in files.items():
            zout.writestr(name, payload)

    # Local advances past the conflicted version before merging.
    await dispatcher.call("protocols.save", {"project_id": pid, "title": "Local v2"})
    await dispatcher.call("protocols.save", {"project_id": pid, "title": "Local v3"})

    preview = await dispatcher.call(
        "statefile.preview_import", {"input_path": str(doctored)}
    )
    conflicts = preview["diff"]["conflicts"]
    assert any(c["kind"] == "protocol_parallel" for c in conflicts)
    key = next(
        c for c in conflicts if c["kind"] == "protocol_parallel"
    )
    ckey = "protocol_parallel:" + "|".join(
        f"{k}={v}" for k, v in sorted(key["key"].items())
    )

    # keep_incoming previously inserted at v1+1 = v2 — an IntegrityError
    # against local v2. It must land at max(local)+1 = v4.
    res = await dispatcher.call(
        "statefile.merge",
        {
            "input_path": str(doctored),
            "resolutions": {ckey: "keep_incoming"},
            "take_pre_import_snapshot": False,
        },
    )
    assert res["summary"]["conflicts_resolved"]["protocol_parallel"] == 1
    versions = await dispatcher.call("protocols.versions", {"project_id": pid})
    numbers = sorted(v["version"] for v in versions["versions"])
    assert numbers == [1, 2, 3, 4]


async def test_protocol_body_divergence_beyond_title_pico_conflicts(
    dispatcher, local_identity, tmp_path
):
    pid = await _seed_project(dispatcher)
    await dispatcher.call(
        "protocols.save",
        {"project_id": pid, "title": "Same title", "background": "local background"},
    )
    out = tmp_path / "src.prismaproj"
    await dispatcher.call("statefile.export", {"project_id": pid, "output_path": str(out)})

    import hashlib
    import uuid as uuid_mod

    with zipfile.ZipFile(out) as zin:
        files = {n: zin.read(n) for n in zin.namelist()}
    protocols = [
        json.loads(line) for line in files["protocols.jsonl"].decode().splitlines() if line
    ]
    # Same title and pico, different id and background: the old diff compared
    # only title+pico and silently discarded this divergent body.
    protocols[0]["id"] = str(uuid_mod.uuid4())
    protocols[0]["background"] = "incoming background, changed elsewhere"
    files["protocols.jsonl"] = ("".join(
        json.dumps(p, sort_keys=True, separators=(",", ":")) + "\n" for p in protocols
    )).encode()
    man = json.loads(files["manifest.json"])
    for fc in man["files"]:
        if fc["relative_path"] == "protocols.jsonl":
            fc["sha256"] = hashlib.sha256(files["protocols.jsonl"]).hexdigest()
            fc["size_bytes"] = len(files["protocols.jsonl"])
    files["manifest.json"] = json.dumps(man).encode()
    doctored = tmp_path / "other.prismaproj"
    with zipfile.ZipFile(doctored, "w") as zout:
        for name, payload in files.items():
            zout.writestr(name, payload)

    preview = await dispatcher.call(
        "statefile.preview_import", {"input_path": str(doctored)}
    )
    assert any(
        c["kind"] == "protocol_parallel" for c in preview["diff"]["conflicts"]
    )


async def test_keep_incoming_supersedes_local_version(
    dispatcher, local_identity, tmp_path
):
    import hashlib
    import uuid as uuid_mod

    from sqlalchemy import select

    from prismapi.db.base import get_sessionmaker
    from prismapi.db.models import Protocol

    pid = await _seed_project(dispatcher)
    await dispatcher.call("protocols.save", {"project_id": pid, "title": "Local v1"})
    out = tmp_path / "src.prismaproj"
    await dispatcher.call("statefile.export", {"project_id": pid, "output_path": str(out)})

    with zipfile.ZipFile(out) as zin:
        files = {n: zin.read(n) for n in zin.namelist()}
    protocols = [
        json.loads(line) for line in files["protocols.jsonl"].decode().splitlines() if line
    ]
    local_v1_id = protocols[0]["id"]
    protocols[0]["id"] = str(uuid_mod.uuid4())
    protocols[0]["title"] = "Incoming v1"
    files["protocols.jsonl"] = ("".join(
        json.dumps(p, sort_keys=True, separators=(",", ":")) + "\n" for p in protocols
    )).encode()
    man = json.loads(files["manifest.json"])
    for fc in man["files"]:
        if fc["relative_path"] == "protocols.jsonl":
            fc["sha256"] = hashlib.sha256(files["protocols.jsonl"]).hexdigest()
            fc["size_bytes"] = len(files["protocols.jsonl"])
    files["manifest.json"] = json.dumps(man).encode()
    doctored = tmp_path / "other.prismaproj"
    with zipfile.ZipFile(doctored, "w") as zout:
        for name, payload in files.items():
            zout.writestr(name, payload)

    preview = await dispatcher.call(
        "statefile.preview_import", {"input_path": str(doctored)}
    )
    conflict = next(
        c for c in preview["diff"]["conflicts"] if c["kind"] == "protocol_parallel"
    )
    ckey = "protocol_parallel:" + "|".join(
        f"{k}={v}" for k, v in sorted(conflict["key"].items())
    )
    await dispatcher.call(
        "statefile.merge",
        {
            "input_path": str(doctored),
            "resolutions": {ckey: "keep_incoming"},
            "take_pre_import_snapshot": False,
        },
    )

    # keep_incoming moves the local conflicted body to the trash; keep_both
    # would have kept it live. The incoming body lands as the new version.
    Session = get_sessionmaker()
    async with Session() as session:
        import uuid as uuid_mod2

        local_row = await session.get(Protocol, uuid_mod2.UUID(local_v1_id))
        assert local_row is not None
        assert local_row.deleted_at is not None


async def test_read_bundle_rejects_post_validation_tampering(
    dispatcher, local_identity, tmp_path
):
    from prismapi.statefile.importer import read_bundle, validate_manifest
    from prismapi.statefile.schema import UnsupportedSchemaError

    pid = await _seed_project(dispatcher)
    out = tmp_path / "src.prismaproj"
    await dispatcher.call("statefile.export", {"project_id": pid, "output_path": str(out)})

    manifest = validate_manifest(out)

    # Swap bytes after validation (the TOCTOU window the merge path had).
    with zipfile.ZipFile(out) as zin:
        files = {n: zin.read(n) for n in zin.namelist()}
    files["records.jsonl"] = b'{"doctored": true}\n'
    with zipfile.ZipFile(out, "w") as zout:
        for name, payload in files.items():
            zout.writestr(name, payload)

    with pytest.raises(UnsupportedSchemaError) as exc:
        read_bundle(out, manifest)
    assert "changed since validation" in str(exc.value)
