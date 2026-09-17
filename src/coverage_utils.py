"""Statement and branch coverage measurement, backed by coverage.py.

Tool: `coverage.py` (https://coverage.readthedocs.io/), the standard Python
coverage measurement library. We use it rather than writing our own
statement/branch tracker, per the assignment's instruction to prefer an
established tool for coverage measurement.

Design note (documented per Phase 5): the paper's protocol needs, for a
given faulty implementation and its test pool, the coverage *contribution*
of each individual test, so that criterion-guided sampling (src/sampling.py)
can cheaply ask "what is the coverage score of this subset of tests?" many
times over. Re-running coverage.py for every candidate subset during
sampling would be correct but wasteful, since coverage is monotonic in the
tests executed. Instead we measure, once, the set of statements and the set
of branch arcs each *individual* test covers (`measure_per_test_coverage`),
and then build a `score_fn` for src/sampling.py that computes the coverage
of a subset as the size of the *union* of its tests' per-test coverage sets,
divided by the totals for the module. This is mathematically identical to
re-running coverage.py on the subset directly (coverage is a set-union
property), but is dramatically faster.

We access coverage.py's per-run executed statement/branch data via
`Coverage._analyze()`, which returns an `Analysis` object exposing
`.executed` (statement line numbers hit in the run), `.statements` (all
executable statement lines, static), `.arcs_executed_set` (branch arcs hit
in the run), and `.arc_possibilities` (all possible branch arcs, static).
This is a "protected" (underscore-prefixed) method rather than part of
coverage.py's advertised public API (which is oriented around producing
textual/HTML reports for a whole project, not raw per-run sets for a single
function call) - we verified it directly against coverage 7.16.0 before
relying on it (see EXPERIMENT_LOG.md).

Coverage instrumentation runs INSIDE the timeout-guarded worker process
(see EXPERIMENT_LOG.md Entry 13): coverage.py's `sys.settrace`-based
tracing is process-local, so `cov.start()`/`cov.stop()` must wrap the call
in the SAME process where the candidate function actually executes. Since
`src.metrics.call_and_capture` (added in Entry 12, for hang safety) now
executes every call in a separate persistent worker process, coverage
measurement is done by handing `call_and_capture` a small wrapper closure
that itself starts coverage, calls the real function, stops coverage, and
returns the executed line/arc sets alongside the outcome - all of which
happens inside the worker process, not the parent. If a test hangs during
coverage measurement, the whole wrapped call times out exactly like any
other call (returned as `_TimedOut`), and that test's coverage contribution
is treated as empty (we have no way to recover partial coverage data from a
forcibly-killed process that never reached `cov.stop()`).
"""

from __future__ import annotations

import importlib.util
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from src.metrics import _TimedOut, call_and_capture


@dataclass(frozen=True)
class TestCase:
    """A single test in a pool: fixed inputs, no assertion (coverage does
    not need an oracle - only fault triggering/detection does)."""

    test_id: str
    args: tuple = ()
    kwargs: dict | None = None

    def call_kwargs(self) -> dict:
        return self.kwargs or {}


@dataclass
class PerTestCoverage:
    """Per-test coverage contributions plus module-level totals."""

    lines_by_test: dict[str, frozenset[int]]
    arcs_by_test: dict[str, frozenset[tuple[int, int]]]
    all_statements: frozenset[int]
    all_possible_arcs: frozenset[tuple[int, int]]


def load_function_from_source(source: str, function_name: str) -> tuple[Callable, str]:
    """Write ``source`` to a uniquely-named temp .py file and import it,
    returning the requested function object and the file path (needed by
    coverage.py, which attributes execution to file paths).
    """
    tmp_dir = Path(tempfile.gettempdir()) / "table_iv_repro_modules"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    module_name = f"cand_{uuid.uuid4().hex}"
    file_path = tmp_dir / f"{module_name}.py"
    file_path.write_text(source, encoding="utf-8")

    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]

    func = getattr(module, function_name)
    return func, str(file_path)


def _make_coverage_probe(func: Callable, file_path: str) -> Callable[..., dict]:
    """Build a closure that, when called, starts coverage.py, calls
    ``func``, stops coverage.py, and returns the executed line/arc sets -
    all within whichever process actually runs it. Passed to
    ``call_and_capture`` so this entire sequence runs inside the same
    timeout-guarded worker process the function itself executes in (see
    module docstring).

    Any exception raised by ``func`` is caught HERE (inside the probe,
    before returning), not left to propagate out to ``call_and_capture``'s
    own exception handling - otherwise the exception would abort the probe
    before ``cov.stop()``/analysis ran, losing the partial coverage a
    crashing test still achieved. The caller only needs the coverage sets;
    what ``func`` actually returned or raised is irrelevant for this probe's
    purpose (fault triggering/detection, which does care, is computed
    separately via a plain, uninstrumented ``call_and_capture`` call in
    ``src.fault_runner.build_outcomes``).
    """

    def probe(*args, **kwargs):
        import coverage as _coverage  # local import: must run inside the worker process

        cov = _coverage.Coverage(branch=True, data_file=None)
        cov.start()
        try:
            func(*args, **kwargs)
        except Exception:  # noqa: BLE001 - only coverage matters here, not the outcome
            pass
        finally:
            cov.stop()

        analysis = cov._analyze(file_path)  # noqa: SLF001 - see module docstring
        return {
            "executed": frozenset(analysis.executed),
            "arcs_executed": frozenset(analysis.arcs_executed_set),
            "statements": frozenset(analysis.statements),
            "arc_possibilities": frozenset(analysis.arc_possibilities),
        }

    return probe


def measure_per_test_coverage(
    func: Callable, file_path: str, tests: list[TestCase]
) -> PerTestCoverage:
    """Run each test individually against ``func`` under coverage.py and
    record which statements/branches it covers.

    Exceptions raised by ``func`` are captured inside the coverage probe
    (see ``_make_coverage_probe``) rather than propagated, so that a test
    input which crashes the faulty implementation still contributes
    whatever partial coverage it achieved before the exception. A test
    input that causes ``func`` to hang is bounded by the same timeout as
    every other call (``src.metrics.DEFAULT_CALL_TIMEOUT_SECONDS``); if it
    times out, that test's coverage contribution is the empty set (there is
    no way to recover partial coverage from a forcibly-killed process that
    never reached ``cov.stop()``).
    """
    lines_by_test: dict[str, frozenset[int]] = {}
    arcs_by_test: dict[str, frozenset[tuple[int, int]]] = {}
    all_statements: frozenset[int] = frozenset()
    all_possible_arcs: frozenset[tuple[int, int]] = frozenset()

    probe = _make_coverage_probe(func, file_path)

    for test in tests:
        result = call_and_capture(probe, test.args, test.call_kwargs())

        if isinstance(result, _TimedOut):
            lines_by_test[test.test_id] = frozenset()
            arcs_by_test[test.test_id] = frozenset()
            continue

        lines_by_test[test.test_id] = result["executed"]
        arcs_by_test[test.test_id] = result["arcs_executed"]
        all_statements = result["statements"]
        all_possible_arcs = result["arc_possibilities"]

    return PerTestCoverage(
        lines_by_test=lines_by_test,
        arcs_by_test=arcs_by_test,
        all_statements=all_statements,
        all_possible_arcs=all_possible_arcs,
    )


def statement_score_fn(per_test: PerTestCoverage) -> Callable[[list[str]], float]:
    """Build a score_fn (for src/sampling.py) computing statement coverage
    of a subset of test ids as |union of covered lines| / |all statements|.
    """
    total = len(per_test.all_statements)

    def score_fn(selected_ids: list[str]) -> float:
        if total == 0:
            return 1.0  # no statements to cover -> vacuously fully covered
        covered: set[int] = set()
        for tid in selected_ids:
            covered |= per_test.lines_by_test[tid]
        return len(covered) / total

    return score_fn


def branch_score_fn(per_test: PerTestCoverage) -> Callable[[list[str]], float]:
    """Build a score_fn computing branch coverage of a subset of test ids
    as |union of covered arcs| / |all possible arcs|.
    """
    total = len(per_test.all_possible_arcs)

    def score_fn(selected_ids: list[str]) -> float:
        if total == 0:
            return 1.0  # no branches in this function -> vacuously full
        covered: set[tuple[int, int]] = set()
        for tid in selected_ids:
            covered |= per_test.arcs_by_test[tid]
        return len(covered) / total

    return score_fn
