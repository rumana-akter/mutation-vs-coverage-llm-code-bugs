"""Core fault-triggering / fault-detection metrics.

This module implements Definitions 1-5 from the paper:

    "How effective are traditional test criteria at detecting bugs in
    large language models generated code?" (arXiv:2609.09315)

Definition 1 (Fault Trigger):
    triggered(f, t)  <=>  output(f, t) != output(p, t)
    triggered(f, T)  <=>  exists t in T : triggered(f, t)

Definition 2 (Fault Trigger Rate):
    FTR(T) = |{f in F : triggered(f, T)}| / |F|

Definition 3 (Fault Detection):
    detected(f, t)  <=>  triggered(f, t) AND output(f, t) != oracle(t)
    detected(f, T)  <=>  exists t in T : detected(f, t)

Definition 4 (Fault Detection Rate):
    FDR(T) = |{f in F : detected(f, T)}| / |F|

Definition 5 (Fault Difficulty):
    difficulty(f, T) = 1 - |{t in T : triggered(f, {t})}| / |T|

We represent a single test execution result as an `ExecutionResult`: what
the faulty program produced, what the reference program produced, and
whether the test's own oracle (assertion) flags the faulty output as wrong.
This keeps the metrics module independent of *how* a test is executed
(synthetic function calls, subprocess, coverage.py, etc.) - callers are
responsible for producing these three values.
"""

from __future__ import annotations

import multiprocessing
import queue as _queue_module
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

import cloudpickle

# How long a single candidate/reference function call may run before it is
# considered non-terminating. Chosen to be generous relative to the actual
# runtime of every HumanEval-style function in this study (all complete in
# well under 100ms when they terminate at all - confirmed empirically during
# this project), while still keeping a genuinely hung call's cost bounded to
# a few seconds rather than forever. See EXPERIMENT_LOG.md and
# report/report.md for the incident that motivated this (a subtraction-based
# GCD candidate that infinite-loops on a zero input).
DEFAULT_CALL_TIMEOUT_SECONDS = 5.0


# Sentinel used to represent "the call raised an exception" as an output
# value, so exceptions participate in equality comparisons like any other
# output. Two different exception types are considered different outputs;
# the same exception type is considered the same output (a simplification,
# documented in PLAN.md / report.md).
class _Raised:
    __slots__ = ("exc_type_name",)

    def __init__(self, exc_type_name: str) -> None:
        self.exc_type_name = exc_type_name

    def __eq__(self, other: object) -> bool:
        return isinstance(other, _Raised) and self.exc_type_name == other.exc_type_name

    def __hash__(self) -> int:
        return hash(("Raised", self.exc_type_name))

    def __repr__(self) -> str:
        return f"Raised({self.exc_type_name})"


class _TimedOut:
    """Sentinel for "the call did not complete within the timeout" - a
    distinct execution outcome from both a normal return value and a raised
    exception.

    Comparison rule (deliberately chosen, not incidental - see
    EXPERIMENT_LOG.md for the full discussion): any two ``_TimedOut``
    instances compare EQUAL to each other, since there is only one kind of
    "did not finish in time" and no further information distinguishes them.
    A ``_TimedOut`` instance is never equal to a normal value or to a
    ``_Raised`` instance (even one wrapping the same "conceptual" failure),
    because those are observably different outcomes (a program that raises
    an exception behaves differently from one that never returns at all).

    Consequence for Definition 1 (``triggered(f,t) <=> output(f,t) !=
    output(p,t)``): if BOTH the faulty and the reference implementation
    time out on the same input, ``triggered`` is ``False`` for that test -
    there is no *observed* behavioral divergence, since neither side ever
    produced an answer to compare. If only one side times out (the other
    returns normally or raises), ``triggered`` is ``True`` - a timeout on
    one side and any other outcome on the other side is, by construction,
    a different observable outcome.
    """

    def __eq__(self, other: object) -> bool:
        return isinstance(other, _TimedOut)

    def __hash__(self) -> int:
        return hash("TimedOut")

    def __repr__(self) -> str:
        return "TimedOut()"


def _worker_loop(request_q: "multiprocessing.Queue", response_q: "multiprocessing.Queue") -> None:
    """Runs in a persistent child process, executing one cloudpickled
    ``(func, args, kwargs)`` payload at a time and posting back the result.

    If a call hangs, the parent kills this whole OS process outright (see
    ``_Worker.call``) - this loop never gets a chance to post a response in
    that case, which is fine: the parent has already given up on it and
    starts a fresh worker process for subsequent calls.
    """
    while True:
        payload = request_q.get()
        if payload is None:  # sentinel: shut down
            return
        try:
            func, args, kwargs = cloudpickle.loads(payload)
            result = func(*args, **kwargs)
            response_q.put(("ok", cloudpickle.dumps(result)))
        except Exception as exc:  # noqa: BLE001 - forward any crash to the parent
            response_q.put(("raised", type(exc).__name__))


class _Worker:
    """Lazily-started, persistent worker process used to execute candidate/
    reference function calls with a hard, enforceable timeout.

    Why a process and not a thread: Python cannot forcibly terminate a
    running thread, so a genuinely non-terminating candidate (confirmed to
    occur in practice - see EXPERIMENT_LOG.md) would hang a thread-based
    approach forever. A separate OS process CAN be forcibly terminated
    (``Process.kill()``), so that is what is used here.

    Why a single persistent worker rather than one fresh process per call:
    measured process-spawn overhead on this machine is ~100-200ms (Windows
    "spawn" start method re-runs Python interpreter startup); with call
    volumes in the hundreds-to-thousands per fault (once per test per
    candidate during classification, plus once per test per mutant during
    mutation scoring), spawning fresh per call would make the experiment
    impractically slow. Instead, one worker process is reused across calls
    (near-zero overhead in the common, no-timeout case) and is only killed
    and replaced with a fresh one when a call actually times out.

    Uses ``cloudpickle`` (not the standard ``pickle``) to serialize the
    ``(func, args, kwargs)`` payload, since the functions under test are
    dynamically compiled from LLM-generated source at runtime (via
    ``exec``), which the standard library's pickler cannot serialize.
    """

    def __init__(self) -> None:
        self._ctx = multiprocessing.get_context("spawn")
        self._process: multiprocessing.process.BaseProcess | None = None
        self._request_q: multiprocessing.Queue | None = None
        self._response_q: multiprocessing.Queue | None = None

    def _ensure_started(self) -> None:
        if self._process is None or not self._process.is_alive():
            self._request_q = self._ctx.Queue()
            self._response_q = self._ctx.Queue()
            self._process = self._ctx.Process(
                target=_worker_loop,
                args=(self._request_q, self._response_q),
                daemon=True,
            )
            self._process.start()

    def call(self, func, args: tuple, kwargs: dict, timeout: float) -> Any:
        self._ensure_started()
        payload = cloudpickle.dumps((func, args, kwargs))
        self._request_q.put(payload)
        try:
            status, value = self._response_q.get(timeout=timeout)
        except _queue_module.Empty:
            # The worker is presumably stuck on this call - kill the whole
            # process (not just the call) and start fresh next time.
            self._process.kill()
            self._process.join()
            self._process = None
            return _TimedOut()

        if status == "raised":
            return _Raised(value)
        return cloudpickle.loads(value)


_worker = _Worker()


def call_and_capture(
    func,
    args: Sequence[Any] = (),
    kwargs: dict | None = None,
    timeout: float = DEFAULT_CALL_TIMEOUT_SECONDS,
) -> Any:
    """Call ``func(*args, **kwargs)`` in a separate worker process and
    return its output, a ``_Raised`` sentinel if it raises, or a
    ``_TimedOut`` sentinel if it does not complete within ``timeout``
    seconds. This is the single place that defines what "output(program,
    test)" means operationally.
    """
    kwargs = kwargs or {}
    return _worker.call(func, tuple(args), dict(kwargs), timeout)


def normalize_for_comparison(value: Any) -> Any:
    """Canonical form for comparing two "outputs" that may have crossed a
    JSON boundary on one side but not the other.

    Background (see EXPERIMENT_LOG.md and AUDIT.md for the full incident):
    a generated test oracle's expected value is parsed from JSON, which has
    no tuple type, so a function that naturally returns a Python ``list``
    (e.g. ``count_up_to``) would have its real output compared against a
    JSON-sourced ``tuple`` unless *both* sides are put into the same
    canonical shape first. Comparing a ``list`` to a ``tuple`` in Python is
    unconditionally ``!=`` regardless of contents, which silently made the
    fault-detection oracle check vacuous for every list-returning function.

    The fix is to apply this *same* function to every value being compared
    - the faulty program's output, the reference program's output, and the
    generated oracle's expected value - never to only one side. Applying it
    asymmetrically (as the original, buggy code did) reintroduces exactly
    this bug.

    Rules:
        - ``list`` and ``tuple`` both normalize to a ``tuple``, with every
          element normalized recursively (so nested lists/tuples/dicts are
          handled too, and a list-of-tuples compares equal to a
          tuple-of-lists holding the same values).
        - ``dict`` stays a ``dict`` (JSON objects and Python dicts are
          already the same shape - there is no serialization mismatch to
          fix there), with every value normalized recursively. Keys are
          left as-is.
        - Everything else (``int``, ``float``, ``str``, ``bool``, ``None``,
          and the ``_Raised`` exception sentinel) is returned unchanged -
          scalar values keep their exact meaning, and an exception outcome
          stays distinct from any normal return value (a ``_Raised``
          instance is never a list/tuple/dict, so it always falls through
          to this branch untouched).
    """
    if isinstance(value, (list, tuple)):
        return tuple(normalize_for_comparison(v) for v in value)
    if isinstance(value, dict):
        return {k: normalize_for_comparison(v) for k, v in value.items()}
    return value


@dataclass(frozen=True)
class TestOutcome:
    """The result of running one test against one faulty implementation,
    relative to a fixed reference implementation.

    Attributes:
        test_id: identifier of the test within its pool.
        faulty_output: output(f, t) - what the faulty program produced.
        reference_output: output(p, t) - what the reference program produced.
        oracle_flags_error: whether the test's own oracle/assertion would
            flag ``faulty_output`` as incorrect (True = assertion fails on
            the faulty program, i.e. the test "would fail" if run against
            the faulty implementation).
    """

    # Not a pytest test class despite the name - stops pytest from trying
    # to collect it as one.
    __test__ = False

    test_id: str
    faulty_output: Any
    reference_output: Any
    oracle_flags_error: bool

    @property
    def triggered(self) -> bool:
        """Definition 1: triggered(f, t) <=> output(f,t) != output(p,t)."""
        return self.faulty_output != self.reference_output

    @property
    def detected(self) -> bool:
        """Definition 3: detected(f, t) <=> triggered(f,t) AND oracle flags it."""
        return self.triggered and self.oracle_flags_error

    @property
    def faulty_timed_out(self) -> bool:
        """Diagnostic/provenance field (not part of Definitions 1-4): whether
        the faulty program's execution on this test did not complete within
        the timeout. Added for the raw-output timeout tracking requested
        during the controlled scale-up - see EXPERIMENT_LOG.md Entry 12."""
        return isinstance(self.faulty_output, _TimedOut)

    @property
    def reference_timed_out(self) -> bool:
        """Diagnostic/provenance field: whether the reference program's
        execution on this test did not complete within the timeout."""
        return isinstance(self.reference_output, _TimedOut)


def is_triggered(outcomes: Iterable[TestOutcome]) -> bool:
    """triggered(f, T) <=> exists t in T : triggered(f, t)."""
    return any(o.triggered for o in outcomes)


def is_detected(outcomes: Iterable[TestOutcome]) -> bool:
    """detected(f, T) <=> exists t in T : detected(f, t)."""
    return any(o.detected for o in outcomes)


def fault_trigger_rate(per_fault_triggered: Sequence[bool]) -> float:
    """Definition 2, applied to a sequence of per-fault trigger booleans.

    ``per_fault_triggered[i]`` is ``triggered(f_i, T)`` for fault ``f_i``.
    Returns 0.0 for an empty fault set (edge case: no faults means the
    rate is vacuously undefined; we choose 0.0 and document it rather than
    raising, since an empty experiment should not crash aggregation code).
    """
    if len(per_fault_triggered) == 0:
        return 0.0
    return sum(1 for t in per_fault_triggered if t) / len(per_fault_triggered)


def fault_detection_rate(per_fault_detected: Sequence[bool]) -> float:
    """Definition 4, applied to a sequence of per-fault detection booleans."""
    if len(per_fault_detected) == 0:
        return 0.0
    return sum(1 for d in per_fault_detected if d) / len(per_fault_detected)


def fault_difficulty(outcomes_over_pool: Sequence[TestOutcome]) -> float:
    """Definition 5: difficulty(f, T) = 1 - (fraction of tests in the pool
    that individually trigger f).

    ``outcomes_over_pool`` must contain one TestOutcome per test in the full
    pool T (not a sampled subset) - difficulty is a property of the fault
    relative to the *whole* pool.

    Edge case: an empty pool has no tests to trigger anything; we define
    difficulty(f, {}) = 1.0 (maximally hard / vacuously untriggered), and
    document this rather than dividing by zero.
    """
    if len(outcomes_over_pool) == 0:
        return 1.0
    n_triggering = sum(1 for o in outcomes_over_pool if o.triggered)
    return 1.0 - (n_triggering / len(outcomes_over_pool))
