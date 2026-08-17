"""Canonical PRISMA-2020 phase order and successor logic for PrismAPI.

The phase model drives sidebar lock state and the per-phase "Mark as done"
gate. Pure logic — no I/O. The database-backed gate predicates live in
prismapi/services/phase_completion.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Phase(StrEnum):
    SETUP = "setup"
    PROTOCOL = "protocol"
    IMPORT = "import"
    CODEBOOK = "codebook"
    DEDUP = "dedup"
    TITLE_ABSTRACT = "title_abstract"
    FULL_TEXT = "full_text"
    EXTRACTION = "extraction"
    ROB = "rob"
    SYNTHESIS = "synthesis"
    REPORT = "report"


PHASE_ORDER: tuple[Phase, ...] = (
    Phase.SETUP,
    Phase.PROTOCOL,
    Phase.IMPORT,
    Phase.CODEBOOK,
    Phase.DEDUP,
    Phase.TITLE_ABSTRACT,
    Phase.FULL_TEXT,
    Phase.EXTRACTION,
    Phase.ROB,
    Phase.SYNTHESIS,
    Phase.REPORT,
)


def next_phase(phase: Phase) -> Phase | None:
    """Return the phase that follows `phase`, or None if `phase` is the last."""
    idx = PHASE_ORDER.index(phase)
    if idx + 1 >= len(PHASE_ORDER):
        return None
    return PHASE_ORDER[idx + 1]


@dataclass(frozen=True, slots=True)
class GateState:
    """Snapshot of the project state used to evaluate phase gates.

    Every field is a literal fact about the database — never a value
    pre-cooked to make a gate pass. `n_ft_pool` is the number of clusters
    that advanced to full text; `n_conflicts_pending` counts title/abstract
    disagreements with no arbitration yet, which block the pool from being
    considered final.
    """
    project_exists: bool
    n_raters: int
    has_protocol: bool
    n_records: int
    n_clusters: int
    n_ta_done_raters: int
    n_ft_done_raters: int
    n_ft_pool: int
    n_conflicts_pending: int
    has_extraction: bool
    has_rob: bool
    has_synthesis: bool


def gate_satisfied(phase: Phase, state: GateState) -> tuple[bool, str]:
    """Return (open, reason). When `open` is False, `reason` explains why."""
    if phase == Phase.SETUP:
        return True, ""
    if phase == Phase.PROTOCOL:
        if not state.project_exists:
            return False, "Project must exist."
        return True, ""
    if phase == Phase.IMPORT:
        if not state.has_protocol:
            return False, "Save a protocol first."
        return True, ""
    if phase == Phase.CODEBOOK:
        if not state.has_protocol:
            return False, "Save a protocol first."
        return True, ""
    if phase == Phase.DEDUP:
        if state.n_records == 0:
            return False, "Import at least one record first."
        return True, ""
    if phase == Phase.TITLE_ABSTRACT:
        if state.n_clusters == 0:
            return False, "Run deduplication first."
        return True, ""
    if phase == Phase.FULL_TEXT:
        if state.n_raters == 0:
            return False, "Enroll at least one rater first."
        if state.n_ta_done_raters < state.n_raters:
            return False, (
                f"Title/abstract screening incomplete: "
                f"{state.n_ta_done_raters}/{state.n_raters} raters marked done."
            )
        return True, ""
    if phase == Phase.EXTRACTION:
        if state.n_raters == 0:
            return False, "Enroll at least one rater first."
        if state.n_ta_done_raters < state.n_raters:
            return False, (
                f"Title/abstract screening incomplete: "
                f"{state.n_ta_done_raters}/{state.n_raters} raters marked done."
            )
        if state.n_conflicts_pending > 0:
            return False, (
                f"{state.n_conflicts_pending} title/abstract conflict(s) need "
                "arbitration before the included set is final."
            )
        if state.n_ft_pool > 0 and state.n_ft_done_raters < state.n_raters:
            return False, (
                f"Full-text screening incomplete: "
                f"{state.n_ft_done_raters}/{state.n_raters} raters marked done."
            )
        return True, ""
    if phase == Phase.ROB:
        if not state.has_extraction:
            return False, "Complete extraction first."
        return True, ""
    if phase == Phase.SYNTHESIS:
        if not state.has_rob:
            return False, "Complete risk-of-bias assessment first."
        return True, ""
    if phase == Phase.REPORT:
        if not state.has_synthesis:
            return False, "Run synthesis first."
        return True, ""
    return False, "Unknown phase."
