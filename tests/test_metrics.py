"""Unit tests for src/metrics.py - FTR, FDR, triggering, detection, difficulty."""

import pytest

from src.metrics import (
    TestOutcome,
    _Raised,
    _TimedOut,
    call_and_capture,
    fault_detection_rate,
    fault_difficulty,
    fault_trigger_rate,
    is_detected,
    is_triggered,
    normalize_for_comparison,
)


def _hang_forever():
    """Module-level (not a lambda/closure) so it is trivially picklable by
    cloudpickle across the worker-process boundary in every test below."""
    while True:
        pass


def outcome(test_id, faulty, reference, oracle_flags_error):
    return TestOutcome(test_id, faulty, reference, oracle_flags_error)


class TestCallAndCapture:
    def test_normal_return_value(self):
        assert call_and_capture(lambda x: x + 1, (1,)) == 2

    def test_exception_is_captured_not_raised(self):
        def boom():
            raise ValueError("bad")

        result = call_and_capture(boom)
        # Should not raise; should be an equality-comparable sentinel.
        assert result == call_and_capture(boom)

    def test_different_exceptions_are_different_outputs(self):
        def raises_value_error():
            raise ValueError("x")

        def raises_type_error():
            raise TypeError("x")

        assert call_and_capture(raises_value_error) != call_and_capture(raises_type_error)

    def test_kwargs_supported(self):
        assert call_and_capture(lambda a, b=0: a + b, (1,), {"b": 5}) == 6


class TestTestOutcomeTriggeredDetected:
    def test_not_triggered_when_outputs_equal(self):
        o = outcome("t1", faulty=4, reference=4, oracle_flags_error=False)
        assert o.triggered is False
        assert o.detected is False

    def test_triggered_and_detected_with_correct_oracle(self):
        # Faulty output differs from reference, and the oracle correctly
        # flags the faulty output as wrong.
        o = outcome("t1", faulty=5, reference=4, oracle_flags_error=True)
        assert o.triggered is True
        assert o.detected is True

    def test_triggered_but_not_detected_with_weak_oracle(self):
        # Faulty output differs from reference, but the test's own oracle
        # does not flag it (e.g. oracle only checks type, not value).
        o = outcome("t1", faulty=5, reference=4, oracle_flags_error=False)
        assert o.triggered is True
        assert o.detected is False

    def test_cannot_detect_without_triggering(self):
        # oracle_flags_error=True but outputs are equal => not triggered,
        # and detection requires triggering, so detected must be False.
        o = outcome("t1", faulty=4, reference=4, oracle_flags_error=True)
        assert o.triggered is False
        assert o.detected is False


class TestSuiteLevelAggregation:
    def test_is_triggered_true_if_any_test_triggers(self):
        outcomes = [
            outcome("t1", 4, 4, False),  # no trigger
            outcome("t2", 5, 4, False),  # triggers, not detected
        ]
        assert is_triggered(outcomes) is True
        assert is_detected(outcomes) is False

    def test_is_detected_true_if_any_test_detects(self):
        outcomes = [
            outcome("t1", 4, 4, False),
            outcome("t2", 5, 4, True),  # triggers AND detects
        ]
        assert is_triggered(outcomes) is True
        assert is_detected(outcomes) is True

    def test_empty_suite_triggers_and_detects_nothing(self):
        assert is_triggered([]) is False
        assert is_detected([]) is False


class TestFaultTriggerRate:
    def test_all_triggered(self):
        assert fault_trigger_rate([True, True, True]) == 1.0

    def test_none_triggered(self):
        assert fault_trigger_rate([False, False]) == 0.0

    def test_mixed(self):
        assert fault_trigger_rate([True, False, True, False]) == 0.5

    def test_empty_fault_set_returns_zero(self):
        # Documented edge case: no faults -> rate defined as 0.0, not NaN.
        assert fault_trigger_rate([]) == 0.0


class TestFaultDetectionRate:
    def test_all_detected(self):
        assert fault_detection_rate([True, True]) == 1.0

    def test_none_detected(self):
        assert fault_detection_rate([False, False, False]) == 0.0

    def test_mixed(self):
        assert fault_detection_rate([True, False, False, False]) == 0.25

    def test_empty_fault_set_returns_zero(self):
        assert fault_detection_rate([]) == 0.0

    def test_fdr_le_ftr_property_on_matching_data(self):
        # Sanity-check the paper's stated property FDR(T) <= FTR(T) holds
        # when detection booleans are derived from the same outcomes as
        # triggering booleans (detection implies triggering by construction).
        outcomes_per_fault = [
            [outcome("t1", 5, 4, True)],  # triggered + detected
            [outcome("t1", 5, 4, False)],  # triggered, not detected
            [outcome("t1", 4, 4, False)],  # not triggered
        ]
        triggered_flags = [is_triggered(o) for o in outcomes_per_fault]
        detected_flags = [is_detected(o) for o in outcomes_per_fault]
        assert fault_detection_rate(detected_flags) <= fault_trigger_rate(triggered_flags)


class TestCallAndCaptureTimeout:
    """Regression tests for the timeout sentinel added after discovering a
    real infinite-loop bug in a generated candidate (a subtraction-based
    GCD implementation hanging on a zero input - see EXPERIMENT_LOG.md).
    Uses a short timeout throughout to keep the suite fast.
    """

    def test_normal_return_still_works(self):
        assert call_and_capture(lambda x: x + 1, (1,), timeout=3) == 2

    def test_raised_exception_still_works(self):
        def boom():
            raise ValueError("bad")

        result = call_and_capture(boom, timeout=3)
        assert result == _Raised("ValueError")

    def test_hanging_call_returns_timed_out_sentinel(self):
        result = call_and_capture(_hang_forever, timeout=1)
        assert isinstance(result, _TimedOut)

    def test_worker_recovers_and_serves_normal_calls_after_a_timeout(self):
        call_and_capture(_hang_forever, timeout=1)  # kills the worker process
        # The next call must still work correctly (a fresh worker is spawned).
        assert call_and_capture(lambda: 42, timeout=3) == 42


class TestTimedOutComparisonSemantics:
    """_TimedOut's equality rule, exactly as specified: any two timeouts
    compare equal (no observed divergence when neither side answers), but a
    timeout is never equal to a normal value or to a _Raised instance (an
    exception and a hang are different observable outcomes)."""

    def test_two_timeouts_are_equal(self):
        assert _TimedOut() == _TimedOut()

    def test_timeout_not_equal_to_normal_value(self):
        assert _TimedOut() != 42
        assert _TimedOut() != "abc"
        assert _TimedOut() != None  # noqa: E711
        assert _TimedOut() != []

    def test_timeout_not_equal_to_raised(self):
        assert _TimedOut() != _Raised("ValueError")
        assert _Raised("ValueError") != _TimedOut()


class TestNormalizeForComparison:
    """Regression tests for the AUDIT.md list-vs-tuple bug fix: a single
    shared normalization function must be applied to BOTH sides of any
    comparison (faulty output, reference output, and the generated oracle's
    expected value), never to only one side.
    """

    def test_list_converted_to_tuple(self):
        assert normalize_for_comparison([1, 2, 3]) == (1, 2, 3)

    def test_tuple_stays_a_tuple(self):
        assert normalize_for_comparison((1, 2, 3)) == (1, 2, 3)

    def test_list_and_tuple_with_same_elements_normalize_equal(self):
        assert normalize_for_comparison([1, 2]) == normalize_for_comparison((1, 2))

    def test_nested_list_of_lists_normalizes_recursively(self):
        assert normalize_for_comparison([[1, 2], [3, 4]]) == ((1, 2), (3, 4))

    def test_nested_tuple_containing_list_normalizes_recursively(self):
        assert normalize_for_comparison((1, [2, 3])) == (1, (2, 3))

    def test_mixed_list_of_tuples_and_tuple_of_lists_normalize_equal(self):
        a = [(1, 2), [3, 4]]
        b = ([1, 2], (3, 4))
        assert normalize_for_comparison(a) == normalize_for_comparison(b)

    def test_dict_values_normalized_recursively_dict_stays_dict(self):
        result = normalize_for_comparison({"a": [1, 2], "b": 3})
        assert result == {"a": (1, 2), "b": 3}
        assert isinstance(result, dict)

    def test_dict_nested_inside_list_normalizes_recursively(self):
        result = normalize_for_comparison([{"x": [1, 2]}])
        assert result == ({"x": (1, 2)},)

    def test_scalars_unchanged(self):
        assert normalize_for_comparison(5) == 5
        assert normalize_for_comparison(5.5) == 5.5
        assert normalize_for_comparison("hello") == "hello"
        assert normalize_for_comparison(True) is True
        assert normalize_for_comparison(None) is None

    def test_raised_sentinel_passes_through_unchanged(self):
        # An exception outcome must stay distinct from any normal return
        # value, not be coerced by normalization.
        r = _Raised("ValueError")
        assert normalize_for_comparison(r) is r
        assert normalize_for_comparison(r) == _Raised("ValueError")
        assert normalize_for_comparison(r) != _Raised("TypeError")

    def test_empty_list_and_empty_tuple_normalize_equal(self):
        assert normalize_for_comparison([]) == normalize_for_comparison(())
        assert normalize_for_comparison([]) == ()


class TestFaultDifficulty:
    def test_trivial_fault_every_test_triggers(self):
        pool = [outcome(f"t{i}", 5, 4, False) for i in range(4)]
        assert fault_difficulty(pool) == 0.0

    def test_hard_fault_no_test_triggers(self):
        pool = [outcome(f"t{i}", 4, 4, False) for i in range(4)]
        assert fault_difficulty(pool) == 1.0

    def test_partial_difficulty(self):
        pool = [
            outcome("t1", 5, 4, False),  # triggers
            outcome("t2", 4, 4, False),  # does not trigger
            outcome("t3", 4, 4, False),  # does not trigger
            outcome("t4", 4, 4, False),  # does not trigger
        ]
        # 1 of 4 tests triggers -> difficulty = 1 - 1/4 = 0.75
        assert fault_difficulty(pool) == pytest.approx(0.75)

    def test_empty_pool_is_maximally_difficult_by_definition(self):
        assert fault_difficulty([]) == 1.0
