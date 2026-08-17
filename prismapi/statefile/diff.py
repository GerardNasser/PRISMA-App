"""Row-level diff rules for `.prismaproj` merges.

A `DiffPreview` is a non-destructive description of what would happen if the
caller merged the incoming bundle into the local DB. It enumerates:

- `added` rows (not present locally → will be inserted)
- `unchanged` rows (already match — no-op)
- `conflicts` (require a user decision before merge can proceed)

Conflict classes:

| key                 | when                                                              |
|---------------------|-------------------------------------------------------------------|
| project_metadata    | Project name/slug/branch_choices differ                           |
| protocol_parallel   | Both sides bumped the same protocol version with different bodies |
| codebook_parallel   | Both sides bumped the same codebook version with different bodies |
| screening_drift     | Same identity + cluster + stage, diverging decision               |
| extraction_drift    | Same identity + cluster, diverging payload                        |
| rob_drift           | Same identity + cluster, diverging judgements                     |
| arbitration_drift   | Different arbiter on the same (cluster, stage)                    |
| identity_drift      | Same identity UUID with different last_name/orcid/email           |
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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
from prismapi.statefile.schema import Manifest


@dataclass
class Conflict:
    kind: str
    entity: str
    local: dict[str, Any]
    incoming: dict[str, Any]
    key: dict[str, str]  # natural key identifying which rows clashed


@dataclass
class DiffPreview:
    project_present_locally: bool
    counts_added: dict[str, int] = field(default_factory=dict)
    counts_unchanged: dict[str, int] = field(default_factory=dict)
    conflicts: list[Conflict] = field(default_factory=list)
    # The full incoming rows, partitioned by category — kept for the merger.
    _adds: dict[str, list[dict[str, Any]]] = field(default_factory=dict, repr=False)

    def has_blocking_conflicts(self) -> bool:
        return bool(self.conflicts)

    def to_json(self) -> dict[str, Any]:
        return {
            "project_present_locally": self.project_present_locally,
            "counts_added": dict(self.counts_added),
            "counts_unchanged": dict(self.counts_unchanged),
            "conflicts": [
                {
                    "kind": c.kind,
                    "entity": c.entity,
                    "local": c.local,
                    "incoming": c.incoming,
                    "key": c.key,
                }
                for c in self.conflicts
            ],
        }


def _to_uuid(v: Any) -> uuid.UUID:
    return v if isinstance(v, uuid.UUID) else uuid.UUID(str(v))


def _normalise_keys(d: dict[str, Any]) -> dict[str, Any]:
    """Drop bookkeeping columns that shouldn't drive equality."""
    return {k: v for k, v in d.items() if k not in {"created_at", "updated_at"}}


_BODY_EXCLUDE = {"id", "project_id", "version", "created_at", "updated_at", "deleted_at"}


def _jsonish(v: Any) -> Any:
    """Normalise a local ORM value for comparison with a JSON-decoded one."""
    if isinstance(v, uuid.UUID):
        return str(v)
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return v


def _bodies_differ(incoming_row: dict[str, Any], local_row: dict[str, Any]) -> bool:
    """Compare every content field the two rows share, not a hand-picked pair.

    A parallel version bump that changed only, say, eligibility criteria must
    still surface as a conflict — silently dropping the incoming body loses
    data with no trace.
    """
    for k in incoming_row.keys() & local_row.keys():
        if k in _BODY_EXCLUDE:
            continue
        if _jsonish(incoming_row[k]) != _jsonish(local_row[k]):
            return True
    return False


def _diff_simple_by_id(
    incoming_rows: list[dict[str, Any]],
    local_rows: dict[uuid.UUID, dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """For tables keyed by id alone with no merge rules — return (adds, unchanged)."""
    adds: list[dict[str, Any]] = []
    unchanged: list[dict[str, Any]] = []
    for row in incoming_rows:
        rid = _to_uuid(row["id"])
        if rid in local_rows:
            unchanged.append(row)
        else:
            adds.append(row)
    return adds, unchanged


async def _local_index_by_id(
    session: AsyncSession, model: type, project_id: uuid.UUID, *, by_project: bool = True
) -> dict[uuid.UUID, dict[str, Any]]:
    q = select(model)
    if by_project and hasattr(model, "project_id"):
        q = q.where(model.project_id == project_id)
    rows = (await session.execute(q)).scalars().all()
    out: dict[uuid.UUID, dict[str, Any]] = {}
    for r in rows:
        d: dict[str, Any] = {}
        for col in r.__table__.columns:
            d[col.name] = getattr(r, col.name)
        out[r.id] = d
    return out


def _identity_equal(a: dict[str, Any], b: dict[str, Any]) -> bool:
    return (
        a.get("last_name") == b.get("last_name")
        and a.get("orcid") == b.get("orcid")
        and a.get("email") == b.get("email")
    )


async def compute_diff(
    session: AsyncSession,
    *,
    incoming: dict[str, Any],
    manifest: Manifest,
) -> DiffPreview:
    project_id = uuid.UUID(manifest.project_id)
    local_project = await session.get(Project, project_id)
    preview = DiffPreview(project_present_locally=local_project is not None)

    incoming_project = incoming["project"]

    if local_project is None:
        # Fresh import — every incoming row is an add.
        preview.counts_added = {
            "project": 1,
            "protocols": len(incoming["protocols"]),
            "pico_elements": len(incoming["pico_elements"]),
            "codebooks": len(incoming["codebooks"]),
            "codebook_rules": len(incoming["codebook_rules"]),
            "searches": len(incoming["searches"]),
            "records": len(incoming["records"]),
            "clusters": len(incoming["clusters"]),
            "cluster_members": len(incoming["cluster_members"]),
            "screenings": len(incoming["screenings"]),
            "conflict_resolutions": len(incoming["conflict_resolutions"]),
            "extractions": len(incoming["extractions"]),
            "rob": len(incoming["rob"]),
            "audit": len(incoming["audit"]),
            "judgments": len(incoming["judgments"]),
            "members": len(incoming.get("members", [])),
            "identities": len(incoming["identities"]),
        }
        preview._adds = {
            "project": [incoming_project],
            "protocols": incoming["protocols"],
            "pico_elements": incoming["pico_elements"],
            "codebooks": incoming["codebooks"],
            "codebook_rules": incoming["codebook_rules"],
            "searches": incoming["searches"],
            "records": incoming["records"],
            "clusters": incoming["clusters"],
            "cluster_members": incoming["cluster_members"],
            "screenings": incoming["screenings"],
            "conflict_resolutions": incoming["conflict_resolutions"],
            "extractions": incoming["extractions"],
            "rob": incoming["rob"],
            "audit": incoming["audit"],
            "judgments": incoming["judgments"],
            "members": incoming.get("members", []),
            "identities": incoming["identities"],
        }
        return preview

    # --- Project metadata conflict? ---
    fields_to_compare = ("name", "slug", "description", "field_config_id", "branch_choices")
    if any(
        _normalise_keys(incoming_project).get(f) != getattr(local_project, f)
        for f in fields_to_compare
    ):
        preview.conflicts.append(
            Conflict(
                kind="project_metadata",
                entity="project",
                local={f: getattr(local_project, f) for f in fields_to_compare},
                incoming={f: incoming_project.get(f) for f in fields_to_compare},
                key={"project_id": str(project_id)},
            )
        )

    # --- Identities ---
    local_idents = await _local_index_by_id(session, Identity, project_id, by_project=False)
    ident_adds: list[dict[str, Any]] = []
    ident_unchanged = 0
    for row in incoming["identities"]:
        rid = _to_uuid(row["id"])
        local = local_idents.get(rid)
        if local is None:
            ident_adds.append({**row, "is_local": False})
        elif not _identity_equal(local, row):
            preview.conflicts.append(
                Conflict(
                    kind="identity_drift",
                    entity="identity",
                    local={k: local.get(k) for k in ("last_name", "orcid", "email")},
                    incoming={k: row.get(k) for k in ("last_name", "orcid", "email")},
                    key={"identity_id": row["id"]},
                )
            )
        else:
            ident_unchanged += 1
    preview.counts_added["identities"] = len(ident_adds)
    preview.counts_unchanged["identities"] = ident_unchanged
    preview._adds["identities"] = ident_adds

    # --- Protocols (versioned) ---
    local_protocols = await _local_index_by_id(session, Protocol, project_id)
    by_version_local: dict[int, dict[str, Any]] = {
        p["version"]: p for p in local_protocols.values()
    }
    proto_adds: list[dict[str, Any]] = []
    proto_unchanged = 0
    for row in incoming["protocols"]:
        v = row["version"]
        rid = _to_uuid(row["id"])
        if rid in local_protocols:
            proto_unchanged += 1
            continue
        # Same version, different id → parallel bump. Full-body comparison:
        # any divergent content field makes it a conflict.
        if v in by_version_local:
            local_row = by_version_local[v]
            if _bodies_differ(row, local_row):
                preview.conflicts.append(
                    Conflict(
                        kind="protocol_parallel",
                        entity="protocol",
                        local={"id": str(local_row["id"]), "version": v},
                        incoming={"id": row["id"], "version": v},
                        key={"project_id": str(project_id), "version": str(v)},
                    )
                )
            else:
                proto_unchanged += 1
            continue
        # Higher version, no local — fast-forward add.
        proto_adds.append(row)
    preview.counts_added["protocols"] = len(proto_adds)
    preview.counts_unchanged["protocols"] = proto_unchanged
    preview._adds["protocols"] = proto_adds

    # --- Codebooks (versioned, same rule as protocols) ---
    local_codebooks = await _local_index_by_id(session, Codebook, project_id)
    by_v_cb: dict[int, dict[str, Any]] = {c["version"]: c for c in local_codebooks.values()}
    cb_adds: list[dict[str, Any]] = []
    cb_unchanged = 0
    for row in incoming["codebooks"]:
        v = row["version"]
        rid = _to_uuid(row["id"])
        if rid in local_codebooks:
            cb_unchanged += 1
            continue
        if v in by_v_cb:
            preview.conflicts.append(
                Conflict(
                    kind="codebook_parallel",
                    entity="codebook",
                    local={"id": str(by_v_cb[v]["id"]), "version": v},
                    incoming={"id": row["id"], "version": v},
                    key={"project_id": str(project_id), "version": str(v)},
                )
            )
            continue
        cb_adds.append(row)
    preview.counts_added["codebooks"] = len(cb_adds)
    preview.counts_unchanged["codebooks"] = cb_unchanged
    preview._adds["codebooks"] = cb_adds

    # Codebook rules: simple by-id union (orphans land on imported codebooks).
    local_cb_rules = await _local_index_by_id(session, CodebookRule, project_id, by_project=False)
    cb_rule_adds, cb_rule_unchanged = _diff_simple_by_id(
        incoming["codebook_rules"], local_cb_rules
    )
    preview.counts_added["codebook_rules"] = len(cb_rule_adds)
    preview.counts_unchanged["codebook_rules"] = len(cb_rule_unchanged)
    preview._adds["codebook_rules"] = cb_rule_adds

    # PICO elements: same.
    local_pico = await _local_index_by_id(session, PicoElement, project_id, by_project=False)
    pico_adds, pico_unchanged = _diff_simple_by_id(incoming["pico_elements"], local_pico)
    preview.counts_added["pico_elements"] = len(pico_adds)
    preview.counts_unchanged["pico_elements"] = len(pico_unchanged)
    preview._adds["pico_elements"] = pico_adds

    # --- Searches (union by id) ---
    local_searches = await _local_index_by_id(session, Search, project_id)
    s_adds, s_unchanged = _diff_simple_by_id(incoming["searches"], local_searches)
    preview.counts_added["searches"] = len(s_adds)
    preview.counts_unchanged["searches"] = len(s_unchanged)
    preview._adds["searches"] = s_adds

    # --- Records (union by id) ---
    local_records = await _local_index_by_id(session, Record, project_id)
    r_adds, r_unchanged = _diff_simple_by_id(incoming["records"], local_records)
    preview.counts_added["records"] = len(r_adds)
    preview.counts_unchanged["records"] = len(r_unchanged)
    preview._adds["records"] = r_adds

    # --- Clusters + members ---
    local_clusters = await _local_index_by_id(session, RecordCluster, project_id)
    cl_adds, cl_unchanged = _diff_simple_by_id(incoming["clusters"], local_clusters)
    preview.counts_added["clusters"] = len(cl_adds)
    preview.counts_unchanged["clusters"] = len(cl_unchanged)
    preview._adds["clusters"] = cl_adds
    local_cl_mem = await _local_index_by_id(
        session, RecordClusterMember, project_id, by_project=False
    )
    cm_adds, cm_unchanged = _diff_simple_by_id(incoming["cluster_members"], local_cl_mem)
    preview.counts_added["cluster_members"] = len(cm_adds)
    preview.counts_unchanged["cluster_members"] = len(cm_unchanged)
    preview._adds["cluster_members"] = cm_adds

    # --- Screenings (per-reviewer-per-cluster-per-stage) ---
    local_screenings = await _local_index_by_id(session, ScreeningDecision, project_id)
    by_key_local: dict[tuple[uuid.UUID, uuid.UUID, str], dict[str, Any]] = {
        (s["cluster_id"], s["reviewer_identity_id"], s["stage"]): s
        for s in local_screenings.values()
    }
    sc_adds: list[dict[str, Any]] = []
    sc_unchanged = 0
    for row in incoming["screenings"]:
        key = (
            _to_uuid(row["cluster_id"]),
            _to_uuid(row["reviewer_identity_id"]),
            row["stage"],
        )
        if key in by_key_local:
            local_row = by_key_local[key]
            if local_row.get("decision") == row.get("decision"):
                sc_unchanged += 1
            else:
                preview.conflicts.append(
                    Conflict(
                        kind="screening_drift",
                        entity="screening",
                        local={"decision": local_row.get("decision")},
                        incoming={"decision": row.get("decision")},
                        key={
                            "cluster_id": str(key[0]),
                            "reviewer_identity_id": str(key[1]),
                            "stage": key[2],
                        },
                    )
                )
            continue
        sc_adds.append(row)
    preview.counts_added["screenings"] = len(sc_adds)
    preview.counts_unchanged["screenings"] = sc_unchanged
    preview._adds["screenings"] = sc_adds

    # --- Conflict resolutions (per cluster+stage) ---
    local_arb = await _local_index_by_id(session, ConflictResolution, project_id)
    by_arb_key: dict[tuple[uuid.UUID, str], dict[str, Any]] = {
        (a["cluster_id"], a["stage"]): a for a in local_arb.values()
    }
    arb_adds: list[dict[str, Any]] = []
    arb_unchanged = 0
    for row in incoming["conflict_resolutions"]:
        key = (_to_uuid(row["cluster_id"]), row["stage"])
        if key in by_arb_key:
            local_row = by_arb_key[key]
            if (
                local_row.get("arbiter_identity_id") == _to_uuid(row["arbiter_identity_id"])
                and local_row.get("final_decision") == row.get("final_decision")
            ):
                arb_unchanged += 1
            else:
                preview.conflicts.append(
                    Conflict(
                        kind="arbitration_drift",
                        entity="conflict_resolution",
                        local={
                            "arbiter_identity_id": str(local_row.get("arbiter_identity_id")),
                            "final_decision": local_row.get("final_decision"),
                        },
                        incoming={
                            "arbiter_identity_id": row.get("arbiter_identity_id"),
                            "final_decision": row.get("final_decision"),
                        },
                        key={"cluster_id": str(key[0]), "stage": key[1]},
                    )
                )
            continue
        arb_adds.append(row)
    preview.counts_added["conflict_resolutions"] = len(arb_adds)
    preview.counts_unchanged["conflict_resolutions"] = arb_unchanged
    preview._adds["conflict_resolutions"] = arb_adds

    # --- Extractions (per-reviewer-per-cluster) ---
    local_ex = await _local_index_by_id(session, Extraction, project_id)
    by_ex_key: dict[tuple[uuid.UUID, uuid.UUID], dict[str, Any]] = {
        (e["cluster_id"], e["reviewer_identity_id"]): e for e in local_ex.values()
    }
    ex_adds: list[dict[str, Any]] = []
    ex_unchanged = 0
    for row in incoming["extractions"]:
        key = (_to_uuid(row["cluster_id"]), _to_uuid(row["reviewer_identity_id"]))
        if key in by_ex_key:
            local_row = by_ex_key[key]
            if local_row.get("payload") == row.get("payload"):
                ex_unchanged += 1
            else:
                preview.conflicts.append(
                    Conflict(
                        kind="extraction_drift",
                        entity="extraction",
                        local={"payload_keys": sorted((local_row.get("payload") or {}).keys())},
                        incoming={"payload_keys": sorted((row.get("payload") or {}).keys())},
                        key={
                            "cluster_id": str(key[0]),
                            "reviewer_identity_id": str(key[1]),
                        },
                    )
                )
            continue
        ex_adds.append(row)
    preview.counts_added["extractions"] = len(ex_adds)
    preview.counts_unchanged["extractions"] = ex_unchanged
    preview._adds["extractions"] = ex_adds

    # --- RoB (per-reviewer-per-cluster) ---
    local_rob = await _local_index_by_id(session, RoBAssessment, project_id)
    by_rob_key: dict[tuple[uuid.UUID, uuid.UUID], dict[str, Any]] = {
        (r["cluster_id"], r["reviewer_identity_id"]): r for r in local_rob.values()
    }
    rob_adds: list[dict[str, Any]] = []
    rob_unchanged = 0
    for row in incoming["rob"]:
        key = (_to_uuid(row["cluster_id"]), _to_uuid(row["reviewer_identity_id"]))
        if key in by_rob_key:
            local_row = by_rob_key[key]
            if local_row.get("judgements") == row.get("judgements"):
                rob_unchanged += 1
            else:
                preview.conflicts.append(
                    Conflict(
                        kind="rob_drift",
                        entity="rob",
                        local={"judgement_keys": sorted((local_row.get("judgements") or {}).keys())},
                        incoming={"judgement_keys": sorted((row.get("judgements") or {}).keys())},
                        key={
                            "cluster_id": str(key[0]),
                            "reviewer_identity_id": str(key[1]),
                        },
                    )
                )
            continue
        rob_adds.append(row)
    preview.counts_added["rob"] = len(rob_adds)
    preview.counts_unchanged["rob"] = rob_unchanged
    preview._adds["rob"] = rob_adds

    # --- Audit + judgments (append-only union by id) ---
    local_audit = await _local_index_by_id(session, AuditLog, project_id)
    aud_adds, aud_unchanged = _diff_simple_by_id(incoming["audit"], local_audit)
    preview.counts_added["audit"] = len(aud_adds)
    preview.counts_unchanged["audit"] = len(aud_unchanged)
    preview._adds["audit"] = aud_adds

    local_judgments = await _local_index_by_id(session, JudgmentCall, project_id)
    j_adds, j_unchanged = _diff_simple_by_id(incoming["judgments"], local_judgments)
    preview.counts_added["judgments"] = len(j_adds)
    preview.counts_unchanged["judgments"] = len(j_unchanged)
    preview._adds["judgments"] = j_adds

    # --- Members (union by project + identity; local roles win) ---
    local_members = await _local_index_by_id(session, ProjectMember, project_id)
    local_member_identities = {m["identity_id"] for m in local_members.values()}
    m_adds: list[dict[str, Any]] = []
    m_unchanged = 0
    for row in incoming.get("members", []):
        if _to_uuid(row["identity_id"]) in local_member_identities:
            m_unchanged += 1
        else:
            m_adds.append(row)
    preview.counts_added["members"] = len(m_adds)
    preview.counts_unchanged["members"] = m_unchanged
    preview._adds["members"] = m_adds

    return preview
