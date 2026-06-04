"""Read a `.prismaproj` zip, validate it, and surface a non-destructive
DiffPreview against the local DB."""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from prismapi.statefile.diff import DiffPreview, compute_diff
from prismapi.statefile.schema import SCHEMA_VERSION, Manifest, UnsupportedSchemaError


def _verify_checksums(zf: zipfile.ZipFile, manifest: Manifest) -> list[str]:
    """Return a list of files whose actual bytes don't match the manifest hash.

    An empty list means the bundle is intact.
    """
    bad: list[str] = []
    for fc in manifest.files:
        try:
            payload = zf.read(fc.relative_path)
        except KeyError:
            bad.append(fc.relative_path + " (missing)")
            continue
        actual = hashlib.sha256(payload).hexdigest()
        if actual != fc.sha256:
            bad.append(fc.relative_path)
    return bad


def validate_manifest(path: Path) -> Manifest:
    """Open a `.prismaproj`, parse + verify its manifest, return it.

    Raises `UnsupportedSchemaError` if schema_version is incompatible.
    """
    with zipfile.ZipFile(path, "r") as zf:
        try:
            manifest_raw = zf.read("manifest.json")
        except KeyError as exc:
            raise UnsupportedSchemaError("Not a .prismaproj (no manifest)") from exc
        manifest = Manifest.model_validate(json.loads(manifest_raw))
        if manifest.schema_version != SCHEMA_VERSION:
            raise UnsupportedSchemaError(
                f"schema_version={manifest.schema_version} not supported "
                f"by this app (expected {SCHEMA_VERSION})"
            )
        bad = _verify_checksums(zf, manifest)
        if bad:
            raise UnsupportedSchemaError(
                "Bundle integrity check failed for: " + ", ".join(bad)
            )
        return manifest


def _read_jsonl(zf: zipfile.ZipFile, name: str) -> list[dict[str, Any]]:
    try:
        text = zf.read(name).decode("utf-8")
    except KeyError:
        return []
    out: list[dict[str, Any]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        out.append(json.loads(line))
    return out


def _read_json(zf: zipfile.ZipFile, name: str) -> dict[str, Any]:
    return json.loads(zf.read(name))


async def preview_import(
    session: AsyncSession, *, path: Path
) -> tuple[Manifest, DiffPreview]:
    """Open the file, validate the manifest, compute a DiffPreview vs the local DB."""
    manifest = validate_manifest(path)
    incoming: dict[str, Any]
    with zipfile.ZipFile(path, "r") as zf:
        incoming = {
            "project": _read_json(zf, "project.json"),
            "protocols": _read_jsonl(zf, "protocols.jsonl"),
            "pico_elements": _read_jsonl(zf, "pico_elements.jsonl"),
            "codebooks": _read_jsonl(zf, "codebooks.jsonl"),
            "codebook_rules": _read_jsonl(zf, "codebook_rules.jsonl"),
            "searches": _read_jsonl(zf, "searches.jsonl"),
            "records": _read_jsonl(zf, "records.jsonl"),
            "clusters": _read_jsonl(zf, "clusters.jsonl"),
            "cluster_members": _read_jsonl(zf, "cluster_members.jsonl"),
            "screenings": _read_jsonl(zf, "screenings.jsonl"),
            "conflict_resolutions": _read_jsonl(zf, "conflict_resolutions.jsonl"),
            "extractions": _read_jsonl(zf, "extractions.jsonl"),
            "rob": _read_jsonl(zf, "rob.jsonl"),
            "audit": _read_jsonl(zf, "audit.jsonl"),
            "judgments": _read_jsonl(zf, "judgments.jsonl"),
            "identities": _read_jsonl(zf, "identities.jsonl"),
        }
    diff = await compute_diff(session, incoming=incoming, manifest=manifest)
    return manifest, diff
