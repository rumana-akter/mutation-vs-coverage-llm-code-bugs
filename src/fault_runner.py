"""Orchestrates one fault's full experiment: build per-criterion score
functions (statement/branch/mutation), run the paper's randomized
criterion-guided sampling protocol (Section V) for N iterations per
criterion, and evaluate fault triggering / fault detection for each
sampled suite.

This module is shared by both the synthetic example (Phase 4) and the real
HumanEval+ pilot (Phase 8) - it knows nothing about where a "fault" comes
from (hand-crafted vs LLM-generated), only how to run the protocol given a
faulty implementation's source, a reference function, and an oracle-bearing
test pool.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from src.coverage_utils import (
    TestCase,
    branch_score_fn,
    load_function_from_source,
    measure_per_test_coverage,
    statement_score_fn,
)
from src.metrics import (
    DEFAULT_CALL_TIMEOUT_SECONDS,
    TestOutcome,
    call_and_capture,
    fault_difficulty,
    normalize_for_comparison,
)
from src.mutation_utils import build_mutation_model, mutation_score_fn
from src.sampling import sample_test_suite

CRITERIA = ("statement", "branch", "mutation")


@dataclass(frozen=True)
class OracleTestCase:
    """One test in a generated pool: fixed inputs plus the value the test's
    own oracle/assertion believes is correct (``expected_output``). This is
    assumption A2' from PLAN.md: an equality-check oracle in place of
    free-form assertion code, so it can be evaluated exactly and safely.
    """

    test_id: str
    args: tuple = ()
    kwargs: dict | None = None
    expected_output: Any = None

    def as_test_case(self) -> TestCase:
        return TestCase(test_id=self.test_id, args=self.args, kwargs=self.kwargs)


@dataclass(frozen=True)
class FaultSpec:
    """A single faulty implementation to evaluate, with its reference
    implementation and its generated test pool."""

    fault_id: str
    faulty_source: str
    function_name: str
    reference_func: Callable
    tests: list[OracleTestCase]


@dataclass(frozen=True)
class RawResultRow:
    """One row of the raw per-iteration results (Phase 9 CSV schema).

    ``faulty_timed_out``/``reference_timed_out`` and ``timeout_seconds``
    are provenance/diagnostic fields added during the controlled scale-up
    (EXPERIMENT_LOG.md Entry 12/14) - they do not participate in the
    FTR/FDR definitions themselves (``triggered``/``detected`` already
    account for timeouts via ``_TimedOut``'s comparison semantics), but
    make it possible to audit, after the fact, whether a timeout occurred
    within a given sampled suite and contributed to that suite's result.
    """

    benchmark: str
    fault_model: str
    fault_id: str
    criterion: str
    iteration: int
    selected_test_count: int
    target_score: float
    achieved_score: float
    triggered: bool
    detected: bool
    seed: int
    faulty_timed_out: bool
    reference_timed_out: bool
    timeout_seconds: float


def build_outcomes(
    fault: FaultSpec,
    faulty_func: Callable,
    timeout: float = DEFAULT_CALL_TIMEOUT_SECONDS,
) -> dict[str, TestOutcome]:
    """Compute the TestOutcome (Definitions 1 & 3 inputs) for every test in
    the fault's pool, comparing the faulty implementation against the
    reference implementation on the same inputs.

    All three values that participate in any equality/inequality comparison
    here - the faulty program's output, the reference program's output, and
    the generated oracle's expected value - are put through the SAME
    ``normalize_for_comparison`` canonicalization before any comparison is
    made. This matters specifically for the oracle comparison: a generated
    test's ``expected_output`` may have crossed a JSON boundary (so a
    function that returns a native Python ``list`` would otherwise be
    compared against a JSON-sourced ``tuple``, which are never `==` in
    Python regardless of contents - see AUDIT.md for the incident this
    fixes). Normalizing every value the same way, symmetrically, avoids
    that regardless of which side of a comparison a value came from.

    ``timeout`` (seconds) bounds each individual call via
    ``call_and_capture`` - a call that does not return in time yields a
    ``_TimedOut`` sentinel rather than hanging the whole experiment (see
    EXPERIMENT_LOG.md for the incident that motivated this: a generated
    candidate whose subtraction-based GCD implementation infinite-loops on
    a zero input). Exposed as a parameter (rather than always using the
    module default) purely so tests can use a short timeout and stay fast;
    production callers rely on the default.
    """
    outcomes: dict[str, TestOutcome] = {}
    for t in fault.tests:
        faulty_output = normalize_for_comparison(
            call_and_capture(faulty_func, t.args, t.kwargs or {}, timeout=timeout)
        )
        reference_output = normalize_for_comparison(
            call_and_capture(fault.reference_func, t.args, t.kwargs or {}, timeout=timeout)
        )
        expected_output = normalize_for_comparison(t.expected_output)
        # The test's own oracle "flags an error" when the faulty output
        # does not match what the oracle believes is correct.
        oracle_flags_error = faulty_output != expected_output
        outcomes[t.test_id] = TestOutcome(
            test_id=t.test_id,
            faulty_output=faulty_output,
            reference_output=reference_output,
            oracle_flags_error=oracle_flags_error,
        )
    return outcomes


def compute_fault_difficulty(fault: FaultSpec, faulty_func: Callable) -> float:
    """Definition 5, applied to the fault's full test pool."""
    outcomes = build_outcomes(fault, faulty_func)
    return fault_difficulty(list(outcomes.values()))


def build_score_fns(fault: FaultSpec, faulty_func: Callable, file_path: str) -> dict[str, Callable]:
    """Build the statement/branch/mutation score_fn's for this fault,
    measured against the faulty implementation (the "program under test"
    in a realistic testing scenario - see PLAN.md Section 9)."""
    plain_tests = [t.as_test_case() for t in fault.tests]

    per_test_cov = measure_per_test_coverage(faulty_func, file_path, plain_tests)
    mutation_model = build_mutation_model(fault.faulty_source, fault.function_name, plain_tests)

    return {
        "statement": statement_score_fn(per_test_cov),
        "branch": branch_score_fn(per_test_cov),
        "mutation": mutation_score_fn(mutation_model),
    }


def run_fault_experiment(
    fault: FaultSpec,
    *,
    benchmark: str,
    fault_model: str,
    n_iterations: int = 100,
    base_seed: int = 0,
    criteria: tuple[str, ...] = CRITERIA,
) -> list[RawResultRow]:
    """Run the full Section V protocol for one fault across all requested
    criteria, ``n_iterations`` times each, and return raw per-iteration rows.
    """
    faulty_func, file_path = load_function_from_source(fault.faulty_source, fault.function_name)
    outcomes = build_outcomes(fault, faulty_func)
    score_fns = build_score_fns(fault, faulty_func, file_path)

    pool_ids = [t.test_id for t in fault.tests]
    rows: list[RawResultRow] = []

    for criterion in criteria:
        score_fn = score_fns[criterion]
        for iteration in range(n_iterations):
            seed = base_seed + iteration
            result = sample_test_suite(pool_ids, score_fn=score_fn, seed=seed)

            selected_outcomes = [outcomes[tid] for tid in result.selected]
            triggered = any(o.triggered for o in selected_outcomes)
            detected = any(o.detected for o in selected_outcomes)
            faulty_timed_out = any(o.faulty_timed_out for o in selected_outcomes)
            reference_timed_out = any(o.reference_timed_out for o in selected_outcomes)

            rows.append(
                RawResultRow(
                    benchmark=benchmark,
                    fault_model=fault_model,
                    fault_id=fault.fault_id,
                    criterion=criterion,
                    iteration=iteration,
                    selected_test_count=len(result.selected),
                    target_score=result.target_score,
                    achieved_score=result.achieved_score,
                    triggered=triggered,
                    detected=detected,
                    seed=seed,
                    faulty_timed_out=faulty_timed_out,
                    reference_timed_out=reference_timed_out,
                    timeout_seconds=DEFAULT_CALL_TIMEOUT_SECONDS,
                )
            )

    return rows
