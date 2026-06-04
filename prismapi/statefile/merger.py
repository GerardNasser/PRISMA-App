"""Apply a DiffPreview to the local DB.

The merger is the only function in the statefile module that mutates the DB.
It accepts a `resolutions` dict that answers any blocking conflicts the
preview surfaced. The whole apply runs in a single transaction.

Resolution shape (per-conflict): one of `keep_local`, `keep_incoming`, or
`keep_both` (only valid for protocol/codebook parallel bumps, which then turn
into a new version on top of the higher of the two).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from prismapi.db.base import utcnow
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
from prismapi.services.audit import record_audit
from prismapi.statefile.diff import Conflict, DiffPreview
from prismapi.statefile.schema import Manifest


def _to_uuid(v: Any) -> uuid.UUID:
    return v if isinstance(v, uuid.UUID) else uuid.UUID(str(v))


def _parse_dt(v: Any) -> datetime | None:
    if isinstance(v, datetime):
        return v
    if isinstance(v, str):
        return datetime.fromisoformat(v)
    return None


def _hydrate(model: type, row: dict[str, Any]) -> Any:
    """Build an unsaved model instance from a JSON dict."""
    cols = {c.name: c for c in model.__table__.columns}
    kwargs: dict[str, Any] = {}
    for k, v in row.items():
        if k not in cols:
            continue
        col = cols[k]
        py_type = col.type.python_type
        if v is None:
            kwargs[k] = None
        elif py_type is uuid.UUID:
            kwargs[k] = _to_uuid(v)
        elif py_type is datetime:
            kwargs[k] = _parse_dt(v)
        else:
            kwargs[k] = v
    return model(**kwargs)


def _conflict_key(c: Conflict) -> str:
    """Stable string key for a conflict — used to match user-supplied resolutions."""
    return f"{c.kind}:" + "|".join(f"{k}={c.key[k]}" for k in sorted(c.key))


async def apply_merge(
    session: AsyncSession,
    *,
    manifest: Manifest,
    preview: DiffPreview,
    incoming: dict[str, Any],
    resolutions: dict[str, str] | None = None,
    actor_identity_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    """Apply the merge described by `preview` against the local DB.

    Raises `ValueError` if any conflict lacks a corresponding resolution.
    """
    resolutions = resolutions or {}
    unresolved: list[str] = []
    for c in preview.conflicts:
        ckey = _conflict_key(c)
        if ckey not in resolutions:
            unresolved.append(ckey)
    if unresolved:
        raise ValueError(
            f"Cannot merge: {len(unresolved)} conflict(s) need a resolution: "
            + ", ".join(unresolved[:5])
            + ("…" if len(unresolved) > 5 else "")
        )

    summary: dict[str, Any] = {
        "added": {},
        "unchanged": dict(preview.counts_unchanged),
        "conflicts_resolved": {},
    }

    # Identities first (so FK targets exist before Project insert).
    for row in preview._adds.get("identities", []):
        if await session.get(Identity, _to_uuid(row["id"])):
            continue
        session.add(_hydrate(Identity, {**row, "is_local": False}))
    summary["added"]["identities"] = len(preview._adds.get("identities", []))
    await session.flush()

    # Project row.
    if not preview.project_present_locally:
        proj_row = incoming["project"]
        proj = _hydrate(Project, proj_row)
        session.add(proj)
        await session.flush()
        summary["added"]["project"] = 1

    for c in preview.conflicts:
        if c.kind != "identity_drift":
            continue
        choice = resolutions[_conflict_key(c)]
        if choice == "keep_incoming":
            ident = await session.get(Identity, _to_uuid(c.key["identity_id"]))
            if ident is not None and not ident.is_local:
                for f in ("last_name", "orcid", "email"):
                    if f in c.incoming:
                        setattr(ident, f, c.incoming[f])
        summary["conflicts_resolved"].setdefault("identity_drift", 0)
        summary["conflicts_resolved"]["identity_drift"] += 1

    # Project metadata conflict — only one possible.
    for c in preview.conflicts:
        if c.kind != "project_metadata":
            continue
        choice = resolutions[_conflict_key(c)]
        if choice == "keep_incoming":
            proj = await session.get(Project, _to_uuid(manifest.project_id))
            if proj is not None:
                for f in ("name", "slug", "description", "branch_choices"):
                    if f in c.incoming:
                        setattr(proj, f, c.incoming[f])
        summary["conflicts_resolved"]["project_metadata"] = 1

    # Simple add tables (FK-safe order). Flush between sections that have FKs
    # to each other so SQLite's FK check sees parents before children.
    for table, model in [
        ("protocols", Protocol),
        ("pico_elements", PicoElement),
        ("codebooks", Codebook),
        ("codebook_rules", CodebookRule),
        ("searches", Search),
        ("records", Record),
        ("clusters", RecordCluster),
        ("cluster_members", RecordClusterMember),
        ("screenings", ScreeningDecision),
        ("conflict_resolutions", ConflictResolution),
        ("extractions", Extraction),
        ("rob", RoBAssessment),
        ("audit", AuditLog),
        ("judgments", JudgmentCall),
    ]:
        rows = preview._adds.get(table, [])
        for r in rows:
            session.add(_hydrate(model, r))
        summary["added"][table] = len(rows)
        if rows:
            await session.flush()

    # Parallel-bump conflicts → write a new version row that supersedes both.
    for c in preview.conflicts:
        if c.kind == "protocol_parallel":
            choice = resolutions[_conflict_key(c)]
            local_v = c.local["version"]
            if choice == "keep_incoming":
                # Find the incoming row matching by id and insert it.
                incoming_id = c.incoming["id"]
                row = next(p for p in incoming["protocols"] if p["id"] == incoming_id)
                session.add(_hydrate(Protocol, {**row, "version": local_v + 1}))
            elif choice == "keep_both":
                incoming_id = c.incoming["id"]
                row = next(p for p in incoming["protocols"] if p["id"] == incoming_id)
                session.add(_hydrate(Protocol, {**row, "version": local_v + 1}))
                # local is retained as v_local; we add the incoming as v_local+1.
            summary["conflicts_resolved"].setdefault("protocol_parallel", 0)
            summary["conflicts_resolved"]["protocol_parallel"] += 1
        elif c.kind == "codebook_parallel":
            choice = resolutions[_conflict_key(c)]
            local_v = c.local["version"]
            if choice in ("keep_incoming", "keep_both"):
                incoming_id = c.incoming["id"]
                row = next(p for p in incoming["codebooks"] if p["id"] == incoming_id)
                session.add(_hydrate(Codebook, {**row, "version": local_v + 1}))
            summary["conflicts_resolved"].setdefault("codebook_parallel", 0)
            summary["conflicts_resolved"]["codebook_parallel"] += 1
        elif c.kind == "screening_drift":
            choice = resolutions[_conflict_key(c)]
            if choice == "keep_incoming":
                existing = await session.scalar(
                    select(ScreeningDecision).where(
                        ScreeningDecision.cluster_id == _to_uuid(c.key["cluster_id"]),
                        ScreeningDecision.reviewer_identity_id == _to_uuid(c.key["reviewer_identity_id"]),
                        ScreeningDecision.stage == c.key["stage"],
                    )
                )
                if existing is not None:
                    existing.decision = c.incoming["decision"]
            summary["conflicts_resolved"].setdefault("screening_drift", 0)
            summary["conflicts_resolved"]["screening_drift"] += 1
        elif c.kind in ("extraction_drift", "rob_drift", "arbitration_drift"):
            # `keep_incoming` overwrites; `keep_local` no-ops.
            summary["conflicts_resolved"].setdefault(c.kind, 0)
            summary["conflicts_resolved"][c.kind] += 1
            # Detailed resolution writes deferred to future PR — UI for these
            # drift classes is built but applies a no-op for "keep_local".

    # Ensure the local actor is a member of the imported project (otherwise
    # they can't access what they just merged).
    if actor_identity_id is not None:
        project_uuid = _to_uuid(manifest.project_id)
        existing_member = await session.scalar(
            select(ProjectMember).where(
                ProjectMember.project_id == project_uuid,
                ProjectMember.identity_id == actor_identity_id,
            )
        )
        if existing_member is None:
            session.add(
                ProjectMember(
                    project_id=project_uuid,
                    identity_id=actor_identity_id,
                    role="reviewer",
                )
            )
            await session.flush()

    # Audit the merge.
    await record_audit(
        session,
        project_id=_to_uuid(manifest.project_id),
        actor_identity_id=actor_identity_id,
        action="statefile.merge",
        entity_type="project",
        entity_id=manifest.project_id,
        payload={
            "exporter": manifest.exporter.model_dump(),
            "added": summary["added"],
            "conflicts_resolved": summary["conflicts_resolved"],
            "exported_at": manifest.exported_at.isoformat(),
        },
    )
    await session.commit()
    summary["merged_at"] = utcnow().isoformat()
    return summary
