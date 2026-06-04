import pytest

from prismapi.domain.phases import Phase, PHASE_ORDER, next_phase


def test_phase_order_is_canonical():
    assert PHASE_ORDER == (
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


def test_next_phase_returns_successor():
    assert next_phase(Phase.SETUP) == Phase.PROTOCOL
    assert next_phase(Phase.TITLE_ABSTRACT) == Phase.FULL_TEXT


def test_next_phase_of_last_is_none():
    assert next_phase(Phase.REPORT) is None


def test_phase_values_are_lowercase_strings():
    for phase in Phase:
        assert phase.value == phase.value.lower()


from prismapi.domain.phases import GateState, gate_satisfied


def test_gate_setup_always_satisfied():
    state = GateState(project_exists=True, n_raters=0, has_protocol=False,
                       n_records=0, n_clusters=0, n_ta_done_raters=0,
                       n_ft_done_raters=0, has_extraction=False, has_rob=False,
                       has_synthesis=False)
    ok, _ = gate_satisfied(Phase.SETUP, state)
    assert ok


def test_gate_codebook_requires_protocol():
    state = GateState(project_exists=True, n_raters=2, has_protocol=False,
                       n_records=10, n_clusters=10, n_ta_done_raters=0,
                       n_ft_done_raters=0, has_extraction=False, has_rob=False,
                       has_synthesis=False)
    ok, reason = gate_satisfied(Phase.CODEBOOK, state)
    assert not ok
    assert "protocol" in reason.lower()


def test_gate_title_abstract_requires_dedup_and_codebook():
    state = GateState(project_exists=True, n_raters=2, has_protocol=True,
                       n_records=10, n_clusters=0, n_ta_done_raters=0,
                       n_ft_done_raters=0, has_extraction=False, has_rob=False,
                       has_synthesis=False)
    ok, reason = gate_satisfied(Phase.TITLE_ABSTRACT, state)
    assert not ok
    assert "dedup" in reason.lower() or "cluster" in reason.lower()


def test_gate_full_text_requires_all_ta_raters_done():
    state = GateState(project_exists=True, n_raters=3, has_protocol=True,
                       n_records=10, n_clusters=10, n_ta_done_raters=2,
                       n_ft_done_raters=0, has_extraction=False, has_rob=False,
                       has_synthesis=False)
    ok, _ = gate_satisfied(Phase.FULL_TEXT, state)
    assert not ok


def test_gate_full_text_open_when_all_ta_raters_done():
    state = GateState(project_exists=True, n_raters=3, has_protocol=True,
                       n_records=10, n_clusters=10, n_ta_done_raters=3,
                       n_ft_done_raters=0, has_extraction=False, has_rob=False,
                       has_synthesis=False)
    ok, _ = gate_satisfied(Phase.FULL_TEXT, state)
    assert ok
