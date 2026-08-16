"""Export one project's state to a `.prismaproj` zip.

Determinism: rows are sorted by stable keys, JSONL is written with sorted keys
and a trailing newline per line, the zip is created with a fixed mtime so
identical state hashes to the same bytes. This is what lets us verify that two
installs hold equivalent state by comparing the zip's SHA-256.
"""

from __future__ import annotations

import hashlib
import io
import json
import uuid
import zipfile
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from prismapi import __version__
from prismapi.db.models import (
    AuditLog,
    Codebook,
    CodebookRule,
    ConflictResolution,
    Extraction,
    Identity,
    JudgmentCall,
    Project,
    ProjectMember,
    Record,
    RecordCluster,
    RecordClusterMember,
    RoBAssessment,
    ScreeningDecision,
    Search,
)
from prismapi.db.models.protocol import PicoElement, Protocol
from prismapi.services.identity import get_local_identity
from prismapi.statefile.schema import (
    SCHEMA_VERSION,
    FileChecksum,
    IdentityRef,
    Manifest,
    ManifestCounts,
)

_FIXED_MTIME = (2020, 1, 1, 0, 0, 0)  # deterministic zip mtime


def _json_line(d: dict[str, Any]) -> str:
    return json.dumps(d, sort_keys=True, default=_default, separators=(",", ":")) + "\n"


def _default(v: Any) -> Any:
    if isinstance(v, uuid.UUID):
        return str(v)
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, Path):
        return str(v)
    raise TypeError(f"Cannot serialise {type(v).__name__}: {v!r}")


def _row_to_dict(row: Any, *, exclude: set[str] | None = None) -> dict[str, Any]:
    """Serialise a SQLAlchemy model instance to a JSON-able dict."""
    exclude = exclude or set()
    out: dict[str, Any] = {}
    for col in row.__table__.columns:
        if col.name in exclude:
            continue
        out[col.name] = getattr(row, col.name)
    return out


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


async def _gather_rows(session: AsyncSession, project: Project) -> dict[str, list[dict[str, Any]]]:
    """Collect every row needed for a complete project export."""

    def by_id_asc(rows: Iterable[Any]) -> list[dict[str, Any]]:
        return sorted((_row_to_dict(r) for r in rows), key=lambda d: str(d["id"]))

    proj_dict = _row_to_dict(project)

    protocols = (await session.execute(
        select(Protocol).where(Protocol.project_id == project.id).order_by(Protocol.version.asc())
    )).scalars().all()
    pico_rows = (await session.execute(
        select(PicoElement).where(PicoElement.protocol_id.in_([p.id for p in protocols]))
    )).scalars().all() if protocols else []

    codebooks = (await session.execute(
        select(Codebook).where(Codebook.project_id == project.id).order_by(Codebook.version.asc())
    )).scalars().all()
    codebook_rules = (await session.execute(
        select(CodebookRule).where(
            CodebookRule.codebook_id.in_([c.id for c in codebooks])
        )
    )).scalars().all() if codebooks else []

    searches = (await session.execute(
        select(Search).where(Search.project_id == project.id)
    )).scalars().all()
    records = (await session.execute(
        select(Record).where(Record.project_id == project.id)
    )).scalars().all()
    clusters = (await session.execute(
        select(RecordCluster).where(RecordCluster.project_id == project.id)
    )).scalars().all()
    cluster_members = (await session.execute(
        select(RecordClusterMember).where(
            RecordClusterMember.cluster_id.in_([c.id for c in clusters])
        )
    )).scalars().all() if clusters else []

    screenings = (await session.execute(
        select(ScreeningDecision).where(ScreeningDecision.project_id == project.id)
    )).scalars().all()
    conflicts = (await session.execute(
        select(ConflictResolution).where(ConflictResolution.project_id == project.id)
    )).scalars().all()

    extractions = (await session.execute(
        select(Extraction).where(Extraction.project_id == project.id)
    )).scalars().all()
    robs = (await session.execute(
        select(RoBAssessment).where(RoBAssessment.project_id == project.id)
    )).scalars().all()

    audit = (await session.execute(
        select(AuditLog).where(AuditLog.project_id == project.id)
    )).scalars().all()
    judgments = (await session.execute(
        select(JudgmentCall).where(JudgmentCall.project_id == project.id)
    )).scalars().all()
    members = (await session.execute(
        select(ProjectMember).where(ProjectMember.project_id == project.id)
    )).scalars().all()

    # Collect identities referenced anywhere (canonical export = author + every
    # reviewer who acted on the project).
    referenced_ids: set[uuid.UUID] = {project.owner_identity_id}
    for m in members:
        referenced_ids.add(m.identity_id)
    for s in screenings:
        referenced_ids.add(s.reviewer_identity_id)
    for e in extractions:
        referenced_ids.add(e.reviewer_identity_id)
    for r in robs:
        referenced_ids.add(r.reviewer_identity_id)
    for c in conflicts:
        referenced_ids.add(c.arbiter_identity_id)
    for a in audit:
        if a.actor_identity_id is not None:
            referenced_ids.add(a.actor_identity_id)
    identities = (await session.execute(
        select(Identity).where(Identity.id.in_(referenced_ids))
    )).scalars().all() if referenced_ids else []

    return {
        "project": [proj_dict],
        "protocols": by_id_asc(protocols),
        "pico_elements": by_id_asc(pico_rows),
        "codebooks": by_id_asc(codebooks),
        "codebook_rules": by_id_asc(codebook_rules),
        "searches": by_id_asc(searches),
        "records": by_id_asc(records),
        "clusters": by_id_asc(clusters),
        "cluster_members": by_id_asc(cluster_members),
        "screenings": by_id_asc(screenings),
        "conflict_resolutions": by_id_asc(conflicts),
        "extractions": by_id_asc(extractions),
        "rob": by_id_asc(robs),
        "audit": by_id_asc(audit),
        "judgments": by_id_asc(judgments),
        "members": by_id_asc(members),
        "identities": [
            # Strip is_local — that's a property of the source install, not the data.
            {**_row_to_dict(i), "is_local": False}
            for i in sorted(identities, key=lambda r: str(r.id))
        ],
    }


async def export_project(
    session: AsyncSession, *, project: Project, output_path: Path
) -> Manifest:
    """Write a .prismaproj zip to `output_path` and return the manifest."""
    rows = await _gather_rows(session, project)
    exporter = await get_local_identity(session)
    if exporter is None:
        raise RuntimeError("Local identity is required to export a state file")

    file_payloads: dict[str, bytes] = {}

    # The project itself goes as a single JSON document (not JSONL).
    project_json = json.dumps(
        rows["project"][0], sort_keys=True, default=_default, indent=2
    ).encode("utf-8")
    file_payloads["project.json"] = project_json

    # Everything else is one row per JSONL line.
    for filename, key in [
        ("protocols.jsonl", "protocols"),
        ("pico_elements.jsonl", "pico_elements"),
        ("codebooks.jsonl", "codebooks"),
        ("codebook_rules.jsonl", "codebook_rules"),
        ("searches.jsonl", "searches"),
        ("records.jsonl", "records"),
        ("clusters.jsonl", "clusters"),
        ("cluster_members.jsonl", "cluster_members"),
        ("screenings.jsonl", "screenings"),
        ("conflict_resolutions.jsonl", "conflict_resolutions"),
        ("extractions.jsonl", "extractions"),
        ("rob.jsonl", "rob"),
        ("audit.jsonl", "audit"),
        ("judgments.jsonl", "judgments"),
        ("members.jsonl", "members"),
        ("identities.jsonl", "identities"),
    ]:
        payload = "".join(_json_line(d) for d in rows[key]).encode("utf-8")
        file_payloads[filename] = payload

    counts = ManifestCounts(
        protocols=len(rows["protocols"]),
        codebooks=len(rows["codebooks"]),
        records=len(rows["records"]),
        clusters=len(rows["clusters"]),
        searches=len(rows["searches"]),
        screenings=len(rows["screenings"]),
        extractions=len(rows["extractions"]),
        rob=len(rows["rob"]),
        audit=len(rows["audit"]),
        judgments=len(rows["judgments"]),
        identities=len(rows["identities"]),
        members=len(rows["members"]),
        assets=0,  # Asset support to be wired with PDF attachments later.
    )

    manifest = Manifest(
        schema_version=SCHEMA_VERSION,
        prismapi_version=__version__,
        project_id=str(project.id),
        project_name=project.name,
        project_field_config_id=project.field_config_id,
        project_field_config_version=project.field_config_version,
        exporter=IdentityRef(
            id=str(exporter.id),
            last_name=exporter.last_name,
            orcid=exporter.orcid,
            email=exporter.email,
            display_name=exporter.display_name,
        ),
        exported_at=datetime.now(tz=timezone.utc),
        counts=counts,
        files=[
            FileChecksum(
                relative_path=name,
                sha256=_sha256_bytes(payload),
                size_bytes=len(payload),
            )
            for name, payload in sorted(file_payloads.items())
        ],
    )

    manifest_bytes = manifest.model_dump_json(indent=2).encode("utf-8")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    # Write the zip with deterministic mtime.
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        info = zipfile.ZipInfo("manifest.json", date_time=_FIXED_MTIME)
        zf.writestr(info, manifest_bytes)
        for name, payload in sorted(file_payloads.items()):
            info = zipfile.ZipInfo(name, date_time=_FIXED_MTIME)
            zf.writestr(info, payload)
    output_path.write_bytes(buf.getvalue())
    return manifest
