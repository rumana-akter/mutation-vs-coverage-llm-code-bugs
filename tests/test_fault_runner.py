"""Regression tests for src/fault_runner.build_outcomes, specifically for
the list-vs-tuple oracle-comparison bug found and fixed via AUDIT.md.

Before the fix, a generated test oracle's ``expected_output`` was
normalized (JSON list -> Python tuple) at parse time, but the actual
``faulty_output``/``reference_output`` obtained by calling a real function
were never normalized the same way. For any function that natively returns
a Python ``list`` (as opposed to a ``tuple``), this made
``oracle_flags_error`` vacuously ``True`` for every test, since a ``list``
is never ``==`` to a ``tuple`` in Python regardless of contents - the
oracle comparison was not actually checking anything for list-returning
functions.

The fix applies ``src.metrics.normalize_for_comparison`` symmetrically to
all three values (faulty output, reference output, generated oracle) inside
``build_outcomes``, before any comparison. These tests exercise that fix
directly, using small stand-in functions (not real HumanEval code) so the
expected behavior can be verified by hand.
"""

from __future__ import annotations

from src.fault_runner import FaultSpec, OracleTestCase, build_outcomes

# Short timeout used throughout the timeout-scenario tests below, so the
# suite stays fast (production code uses the 5s default).
_SHORT_TIMEOUT = 1.0


def _spec(reference_func, faulty_func, tests, fault_id="test_fault"):
    return FaultSpec(
        fault_id=fault_id,
        faulty_source="# not used - faulty_func is passed directly to build_outcomes",
        function_name="irrelevant",
        reference_func=reference_func,
        tests=tests,
    )


def _hang_forever():
    """Module-level so it is picklable by cloudpickle across the worker
    process boundary."""
    while True:
        pass


def _returns_42():
    return 42


class TestListReturningFunctionOracleComparison:
    """The exact bug scenario: a function that returns a native list,
    compared against a JSON-shaped (list) generated oracle."""

    def test_matching_faulty_and_reference_not_triggered_not_detected(self):
        # reference returns [1, 2], oracle expects [1, 2], faulty is
        # identical (also [1, 2]) -> not triggered, therefore not detected,
        # regardless of any list/tuple representation of the oracle.
        reference_func = lambda: [1, 2]  # noqa: E731
        faulty_func = lambda: [1, 2]  # noqa: E731
        tests = [OracleTestCase(test_id="t1", args=(), expected_output=[1, 2])]

        outcomes = build_outcomes(_spec(reference_func, faulty_func, tests), faulty_func)
        o = outcomes["t1"]

        assert o.triggered is False
        assert o.detected is False

    def test_triggering_bug_with_correct_oracle_is_detected(self):
        # faulty returns [1, 3], reference returns [1, 2], oracle correctly
        # expects [1, 2] -> triggered=True, detected=True. Before the fix,
        # this WOULD have shown detected=True too, but for the wrong reason
        # (oracle_flags_error was vacuously True regardless of content) -
        # this test alone doesn't distinguish the fix from the bug; see the
        # next test, which does.
        reference_func = lambda: [1, 2]  # noqa: E731
        faulty_func = lambda: [1, 3]  # noqa: E731
        tests = [OracleTestCase(test_id="t1", args=(), expected_output=[1, 2])]

        outcomes = build_outcomes(_spec(reference_func, faulty_func, tests), faulty_func)
        o = outcomes["t1"]

        assert o.triggered is True
        assert o.detected is True

    def test_triggering_bug_with_wrong_oracle_is_not_detected(self):
        # THE critical regression test. faulty returns [1, 3], reference
        # returns [1, 2] (so the bug IS triggered), but the generated
        # oracle incorrectly expects [1, 3] - i.e. it matches the faulty
        # output, not the true reference output (a genuinely weak/wrong
        # oracle). Correct behavior: triggered=True, detected=False.
        #
        # Before the fix, `oracle_flags_error = faulty_output != t.expected_output`
        # compared a native `list` ([1, 3]) against a tuple-normalized
        # oracle value ((1, 3)), which are NEVER equal regardless of
        # content - so `oracle_flags_error` was vacuously True and this
        # test would have incorrectly reported detected=True, hiding the
        # weak oracle. The fix normalizes both sides the same way, so
        # [1, 3] and (1, 3) (from the oracle) now correctly compare equal,
        # oracle_flags_error is correctly False, and detected is False.
        reference_func = lambda: [1, 2]  # noqa: E731
        faulty_func = lambda: [1, 3]  # noqa: E731
        tests = [OracleTestCase(test_id="t1", args=(), expected_output=[1, 3])]

        outcomes = build_outcomes(_spec(reference_func, faulty_func, tests), faulty_func)
        o = outcomes["t1"]

        assert o.triggered is True
        assert o.detected is False, (
            "detected should be False: the generated oracle's expected "
            "value [1, 3] matches the faulty output, not the true "
            "reference output [1, 2] - a weak/wrong oracle that should "
            "NOT be reported as having caught the bug."
        )


class TestNestedListTupleNormalizationInOutcomes:
    def test_nested_structure_normalizes_consistently(self):
        # Reference/faulty return a list of tuples; the generated oracle
        # (JSON-sourced) represents the same structure as nested lists.
        # Both must normalize to the same canonical form for a correct
        # comparison.
        reference_func = lambda: [(1, 2), (3, 4)]  # noqa: E731
        faulty_func = lambda: [(1, 2), (3, 4)]  # noqa: E731
        tests = [
            OracleTestCase(test_id="t1", args=(), expected_output=[[1, 2], [3, 4]]),
        ]

        outcomes = build_outcomes(_spec(reference_func, faulty_func, tests), faulty_func)
        o = outcomes["t1"]

        assert o.triggered is False
        assert o.detected is False

    def test_nested_structure_triggering_bug_is_detected_with_correct_oracle(self):
        reference_func = lambda: [(1, 2), (3, 4)]  # noqa: E731
        faulty_func = lambda: [(1, 2), (9, 9)]  # noqa: E731
        tests = [
            OracleTestCase(test_id="t1", args=(), expected_output=[[1, 2], [3, 4]]),
        ]

        outcomes = build_outcomes(_spec(reference_func, faulty_func, tests), faulty_func)
        o = outcomes["t1"]

        assert o.triggered is True
        assert o.detected is True


class TestTupleReturningFunctionStillWorks:
    """Guards against regressing the already-working case (e.g.
    sum_product-style functions that natively return a tuple), now that
    normalization also applies to faulty_output/reference_output, not just
    the oracle."""

    def test_tuple_returning_function_not_triggered(self):
        reference_func = lambda n: (sum(n), 1)  # noqa: E731
        faulty_func = lambda n: (sum(n), 1)  # noqa: E731
        tests = [OracleTestCase(test_id="t1", args=([1, 2, 3],), expected_output=[6, 1])]

        outcomes = build_outcomes(_spec(reference_func, faulty_func, tests), faulty_func)
        o = outcomes["t1"]

        assert o.triggered is False
        assert o.detected is False

    def test_tuple_returning_function_triggered_and_detected(self):
        reference_func = lambda n: (sum(n), 1)  # noqa: E731
        faulty_func = lambda n: (sum(n) + 1, 1)  # noqa: E731  (off-by-one bug)
        tests = [OracleTestCase(test_id="t1", args=([1, 2, 3],), expected_output=[6, 1])]

        outcomes = build_outcomes(_spec(reference_func, faulty_func, tests), faulty_func)
        o = outcomes["t1"]

        assert o.triggered is True
        assert o.detected is True


class TestTimeoutSemantics:
    """Regression tests for the exact comparison rule when one or both
    sides of a triggered/detected comparison time out (see
    src/metrics.py's ``_TimedOut`` docstring for the rule and its
    justification, and EXPERIMENT_LOG.md for the incident that motivated
    adding a timeout at all: a generated candidate whose subtraction-based
    GCD implementation infinite-loops on a zero input).
    """

    def test_faulty_times_out_reference_returns_is_triggered(self):
        # Reference answers normally; faulty never returns - a timeout on
        # one side and a normal value on the other is a different
        # observable outcome, so this must be triggered=True. Detection
        # also follows: a value that never comes back can never equal the
        # oracle's expected value, so the oracle correctly flags it.
        tests = [OracleTestCase(test_id="t1", args=(), expected_output=42)]
        outcomes = build_outcomes(
            _spec(_returns_42, _hang_forever, tests), _hang_forever, timeout=_SHORT_TIMEOUT
        )
        o = outcomes["t1"]

        assert o.triggered is True
        assert o.detected is True

    def test_reference_times_out_faulty_returns_is_triggered(self):
        # Symmetric case: the REFERENCE hangs, the faulty candidate answers
        # normally. Still a different observable outcome -> triggered=True.
        tests = [OracleTestCase(test_id="t1", args=(), expected_output=42)]
        outcomes = build_outcomes(
            _spec(_hang_forever, _returns_42, tests), _returns_42, timeout=_SHORT_TIMEOUT
        )
        o = outcomes["t1"]

        assert o.triggered is True

    def test_both_time_out_is_not_triggered(self):
        # THE explicitly-specified rule: if both sides time out on the same
        # input, there is no observed behavioral divergence (neither side
        # ever produced an answer to compare), so this must NOT be counted
        # as triggered - two _TimedOut instances compare equal.
        tests = [OracleTestCase(test_id="t1", args=(), expected_output=42)]
        outcomes = build_outcomes(
            _spec(_hang_forever, _hang_forever, tests), _hang_forever, timeout=_SHORT_TIMEOUT
        )
        o = outcomes["t1"]

        assert o.triggered is False
        assert o.detected is False


class TestScalarBehaviorUnchanged:
    """Scalars (int/str/bool) must behave exactly as before the fix - this
    was never affected by the bug, and must not be affected by the fix."""

    def test_int_returning_function(self):
        reference_func = lambda: 3  # noqa: E731
        faulty_func = lambda: 2  # noqa: E731
        tests = [OracleTestCase(test_id="t1", args=(), expected_output=3)]

        outcomes = build_outcomes(_spec(reference_func, faulty_func, tests), faulty_func)
        o = outcomes["t1"]

        assert o.triggered is True
        assert o.detected is True

    def test_str_returning_function_not_triggered(self):
        reference_func = lambda: "abc"  # noqa: E731
        faulty_func = lambda: "abc"  # noqa: E731
        tests = [OracleTestCase(test_id="t1", args=(), expected_output="abc")]

        outcomes = build_outcomes(_spec(reference_func, faulty_func, tests), faulty_func)
        o = outcomes["t1"]

        assert o.triggered is False
        assert o.detected is False

    def test_bool_returning_function_triggered_with_weak_oracle(self):
        reference_func = lambda: True  # noqa: E731
        faulty_func = lambda: False  # noqa: E731
        # Weak oracle: expects False, matching the faulty output rather
        # than the true reference output True.
        tests = [OracleTestCase(test_id="t1", args=(), expected_output=False)]

        outcomes = build_outcomes(_spec(reference_func, faulty_func, tests), faulty_func)
        o = outcomes["t1"]

        assert o.triggered is True
        assert o.detected is False
