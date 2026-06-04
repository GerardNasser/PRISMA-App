"""Extraction + Risk-of-Bias services.

Both render their forms from the project's field config:

- `Extraction.payload` is validated against the extraction_template fields
  declared in the field config (key, type, required, options).
- `RoBAssessment.judgements` is validated against the RoB tool spec. When the
  tool is `CUSTOM`, domains come from the field config; otherwise from a
  built-in tool definition (`builtin_rob_tools`).
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from prismapi.db.models import Extraction, Project, RoBAssessment
from prismapi.fields.loader import FieldConfig, field_registry
from prismapi.services.audit import record_audit

# --------------------------------------------------------------------------
# Built-in RoB tool specs.
# Field configs can override with `risk_of_bias.tool: CUSTOM` + domains.
# --------------------------------------------------------------------------

BUILTIN_ROB_TOOLS: dict[str, dict] = {
    "RoB_2": {
        "label": "Cochrane RoB 2 (randomised trials)",
        "domains": [
            {"key": "randomization", "label": "Bias arising from the randomization process"},
            {"key": "deviations", "label": "Bias due to deviations from intended interventions"},
            {"key": "missing_data", "label": "Bias due to missing outcome data"},
            {"key": "outcome_measurement", "label": "Bias in measurement of the outcome"},
            {"key": "selective_reporting", "label": "Bias in selection of the reported result"},
        ],
        "scale": ["low", "some_concerns", "high"],
    },
    "ROBINS_I": {
        "label": "ROBINS-I (non-randomised interventions)",
        "domains": [
            {"key": "confounding", "label": "Confounding"},
            {"key": "selection", "label": "Selection of participants"},
            {"key": "classification", "label": "Classification of interventions"},
            {"key": "deviations", "label": "Deviations from intended interventions"},
            {"key": "missing_data", "label": "Missing data"},
            {"key": "outcome_measurement", "label": "Measurement of outcomes"},
            {"key": "selective_reporting", "label": "Selection of the reported result"},
        ],
        "scale": ["low", "moderate", "serious", "critical", "no_information"],
    },
    "ROBINS_E": {
        "label": "ROBINS-E (exposure / observational)",
        "domains": [
            {"key": "confounding", "label": "Confounding"},
            {"key": "exposure_measurement", "label": "Measurement of the exposure"},
            {"key": "selection", "label": "Selection of participants into the study"},
            {"key": "deviations", "label": "Post-exposure interventions or deviations"},
            {"key": "missing_data", "label": "Missing data"},
            {"key": "outcome_measurement", "label": "Measurement of the outcome"},
            {"key": "selective_reporting", "label": "Selection of the reported result"},
        ],
        "scale": ["low", "some_concerns", "high", "very_high", "no_information"],
    },
    "QUADAS_2": {
        "label": "QUADAS-2 (diagnostic test accuracy)",
        "domains": [
            {"key": "patient_selection", "label": "Patient selection"},
            {"key": "index_test", "label": "Index test"},
            {"key": "reference_standard", "label": "Reference standard"},
            {"key": "flow_timing", "label": "Flow and timing"},
        ],
        "scale": ["low", "unclear", "high"],
    },
    "SYRCLE": {
        "label": "SYRCLE RoB tool (animal studies)",
        "domains": [
            {"key": "sequence_generation", "label": "Sequence generation"},
            {"key": "baseline_characteristics", "label": "Baseline characteristics (animal-specific)"},
            {"key": "allocation_concealment", "label": "Allocation concealment"},
            {"key": "random_housing", "label": "Random housing (animal-specific)"},
            {"key": "blinded_caregivers", "label": "Blinding of caregivers / investigators"},
            {"key": "random_outcome_assessment", "label": "Random outcome assessment (animal-specific)"},
            {"key": "blinded_outcome_assessor", "label": "Blinding of outcome assessor"},
            {"key": "incomplete_outcome_data", "label": "Incomplete outcome data"},
            {"key": "selective_reporting", "label": "Selective outcome reporting"},
            {"key": "other_bias", "label": "Other sources of bias"},
        ],
        "scale": ["yes", "no", "unclear"],
    },
    "JBI_PER_DESIGN": {
        "label": "JBI critical appraisal (routed by study design at extraction time)",
        "domains": [],
        "scale": ["yes", "no", "unclear", "not_applicable"],
    },
    "NOS_WARN": {
        "label": "Newcastle-Ottawa Scale (deprecated — known psychometric problems)",
        "domains": [
            {"key": "selection", "label": "Selection (★★★★)"},
            {"key": "comparability", "label": "Comparability (★★)"},
            {"key": "outcome", "label": "Outcome (★★★)"},
        ],
        "scale": ["star_0", "star_1", "star_2", "star_3", "star_4"],
        "warning": (
            "NOS has documented psychometric problems (low inter-rater reliability, "
            "arbitrary star thresholds). Prefer RoB 2 / ROBINS-I / JBI per-design."
        ),
    },
    "DYBA_DINGSOYR": {
        "label": "Dybå & Dingsøyr (SE 11-item quality criteria)",
        "domains": [
            {"key": "Q1", "label": "Q1: Aims clearly stated"},
            {"key": "Q2", "label": "Q2: Adequate research context"},
            {"key": "Q3", "label": "Q3: Suitable research design"},
            {"key": "Q4", "label": "Q4: Recruitment strategy appropriate"},
            {"key": "Q5", "label": "Q5: Data collection rigorous"},
            {"key": "Q6", "label": "Q6: Researcher-participant relationship"},
            {"key": "Q7", "label": "Q7: Ethical considerations"},
            {"key": "Q8", "label": "Q8: Rigorous analysis"},
            {"key": "Q9", "label": "Q9: Clear statement of findings"},
            {"key": "Q10", "label": "Q10: Value of research"},
            {"key": "Q11", "label": "Q11: Replication package available"},
        ],
        "scale": ["yes", "partial", "no"],
    },
    "NONE": {"label": "No risk of bias module", "domains": [], "scale": []},
}

# --------------------------------------------------------------------------
# Extraction payload validation.
# --------------------------------------------------------------------------


def _validate_extraction_payload(cfg: FieldConfig, payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    tmpl = cfg.data.get("extraction_template", {})
    fields = tmpl.get("fields", [])
    known_keys = {f["key"] for f in fields}
    # Unknown keys are dropped silently — schemas evolve. Required keys are enforced.
    for f in fields:
        if not f.get("required", False):
            continue
        if f["key"] not in payload or payload[f["key"]] in (None, "", []):
            errors.append(f"Missing required field: {f['key']}")
    # Validate select_one against options.
    for f in fields:
        if f["key"] not in payload:
            continue
        value = payload[f["key"]]
        if value in (None, "", []):
            continue
        ftype = f["type"]
        if ftype == "select_one":
            opts = f.get("options", [])
            if opts and value not in opts:
                errors.append(f"{f['key']}: {value!r} not in allowed options {opts}")
        elif ftype == "select_many":
            if not isinstance(value, list):
                errors.append(f"{f['key']}: expected list")
            else:
                opts = f.get("options", [])
                if opts:
                    bad = [v for v in value if v not in opts]
                    if bad:
                        errors.append(f"{f['key']}: values {bad} not in allowed options")
        elif ftype == "boolean":
            if not isinstance(value, bool):
                errors.append(f"{f['key']}: expected boolean")
        elif ftype == "integer":
            if not isinstance(value, int) or isinstance(value, bool):
                errors.append(f"{f['key']}: expected integer")
        elif ftype == "number":
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                errors.append(f"{f['key']}: expected number")
    _ = known_keys  # silence linters
    return errors


def _project_field_config(project: Project) -> FieldConfig:
    cfg = field_registry.by_id(project.field_config_id)
    if cfg is None:
        raise ValueError(f"Project's field config not loaded: {project.field_config_id}")
    return cfg


# --------------------------------------------------------------------------
# Service entrypoints
# --------------------------------------------------------------------------


def resolve_rob_spec(cfg: FieldConfig) -> dict:
    rob = cfg.data["risk_of_bias"]
    tool = rob["tool"]
    if tool == "CUSTOM":
        return {
            "tool": "CUSTOM",
            "label": "Custom (field-specific)",
            "domains": rob.get("domains", []),
            "scale": rob.get("scale", ["low", "some_concerns", "high", "no_information"]),
        }
    spec = BUILTIN_ROB_TOOLS.get(tool)
    if spec is None:
        raise ValueError(f"Unknown built-in RoB tool: {tool}")
    return {"tool": tool, **spec}


async def upsert_extraction(
    session: AsyncSession,
    *,
    project: Project,
    reviewer_id: uuid.UUID,
    cluster_id: uuid.UUID,
    payload: dict,
    status: str = "draft",
    notes: str | None = None,
) -> Extraction:
    cfg = _project_field_config(project)
    errors = _validate_extraction_payload(cfg, payload)
    if errors and status == "submitted":
        # Drafts can be incomplete; submitted must validate.
        raise ValueError("; ".join(errors))
    existing = await session.scalar(
        select(Extraction).where(
            Extraction.cluster_id == cluster_id, Extraction.reviewer_identity_id == reviewer_id
        )
    )
    if existing is None:
        existing = Extraction(
            project_id=project.id,
            cluster_id=cluster_id,
            reviewer_identity_id=reviewer_id,
            template_base=cfg.data["extraction_template"]["base"],
            payload=payload,
            status=status,
            notes=notes,
        )
        session.add(existing)
    else:
        existing.payload = payload
        existing.status = status
        existing.notes = notes
    await record_audit(
        session,
        project_id=project.id,
        actor_identity_id=reviewer_id,
        action="extraction.save",
        entity_type="cluster",
        entity_id=str(cluster_id),
        payload={"status": status, "template_base": existing.template_base, "errors": errors},
    )
    await session.commit()
    await session.refresh(existing)
    return existing


async def upsert_rob(
    session: AsyncSession,
    *,
    project: Project,
    reviewer_id: uuid.UUID,
    cluster_id: uuid.UUID,
    judgements: dict,
    overall: str | None = None,
    notes: str | None = None,
) -> RoBAssessment:
    cfg = _project_field_config(project)
    if not cfg.data.get("modules", {}).get("risk_of_bias", True):
        raise ValueError("Risk-of-bias module is disabled for this field config")
    spec = resolve_rob_spec(cfg)
    domain_keys = {d["key"] for d in spec["domains"]}
    scale = set(spec["scale"])
    # Validate each judgement
    bad: list[str] = []
    for k, v in judgements.items():
        if domain_keys and k not in domain_keys:
            bad.append(f"Unknown domain: {k}")
            continue
        if not isinstance(v, dict):
            bad.append(f"{k}: expected object {{judgement, justification}}")
            continue
        j = v.get("judgement")
        if scale and j not in scale:
            bad.append(f"{k}: judgement {j!r} not in {sorted(scale)}")
    if bad:
        raise ValueError("; ".join(bad))
    existing = await session.scalar(
        select(RoBAssessment).where(
            RoBAssessment.cluster_id == cluster_id, RoBAssessment.reviewer_identity_id == reviewer_id
        )
    )
    if existing is None:
        existing = RoBAssessment(
            project_id=project.id,
            cluster_id=cluster_id,
            reviewer_identity_id=reviewer_id,
            tool=spec["tool"],
            judgements=judgements,
            overall=overall,
            notes=notes,
        )
        session.add(existing)
    else:
        existing.judgements = judgements
        existing.overall = overall
        existing.notes = notes
    await record_audit(
        session,
        project_id=project.id,
        actor_identity_id=reviewer_id,
        action="rob.save",
        entity_type="cluster",
        entity_id=str(cluster_id),
        payload={"tool": spec["tool"], "overall": overall},
    )
    await session.commit()
    await session.refresh(existing)
    return existing
