"""Unit tests for src/sampling.py - randomized criterion-guided selection."""

from src.sampling import sample_test_suite


def coverage_by_set_membership(covers: dict) -> callable:
    """Build a score_fn where each test 'covers' some set of items, and the
    score is the fraction of a fixed universe covered by the union of the
    selected tests' coverage sets. This lets tests express realistic
    "this test increases coverage" / "this test is redundant" scenarios
    without depending on coverage.py.
    """
    universe = set()
    for s in covers.values():
        universe |= s

    def score_fn(selected):
        if not universe:
            return 1.0
        covered = set()
        for t in selected:
            covered |= covers[t]
        return len(covered) / len(universe)

    return score_fn


class TestEmptyPool:
    def test_empty_pool_returns_immediately(self):
        result = sample_test_suite([], score_fn=lambda sel: 0.0, seed=1)
        assert result.selected == []
        assert result.reached_target is True
        assert result.n_tests_examined == 0


class TestSingleTest:
    def test_single_test_that_is_needed(self):
        covers = {"t1": {"line1"}}
        score_fn = coverage_by_set_membership(covers)
        result = sample_test_suite(["t1"], score_fn=score_fn, seed=0)
        assert result.selected == ["t1"]
        assert result.reached_target is True
        assert result.achieved_score == 1.0


class TestRedundantTests:
    def test_redundant_tests_are_discarded(self):
        # t1 and t2 cover the same line; t3 covers a different line.
        # A minimal suite achieving full coverage needs at most one of
        # {t1, t2} plus t3.
        covers = {"t1": {"lineA"}, "t2": {"lineA"}, "t3": {"lineB"}}
        score_fn = coverage_by_set_membership(covers)
        result = sample_test_suite(["t1", "t2", "t3"], score_fn=score_fn, seed=42)
        assert result.reached_target is True
        assert result.achieved_score == 1.0
        # Never both t1 and t2 selected, since the second one adds nothing.
        assert not ({"t1", "t2"} <= set(result.selected))
        assert "t3" in result.selected


class TestCoverageIncreasingTests:
    def test_only_score_increasing_tests_are_kept(self):
        covers = {"t1": {"a"}, "t2": {"a", "b"}, "t3": {"a", "b", "c"}}
        score_fn = coverage_by_set_membership(covers)
        result = sample_test_suite(["t1", "t2", "t3"], score_fn=score_fn, seed=7)
        assert result.reached_target is True
        # t3 alone reaches full coverage, so depending on draw order the
        # selected suite might just be {"t3"}, or a combination - either
        # way every selected test must have contributed a strict increase,
        # which we verify by replaying the selection.
        seen = []
        prev_score = 0.0
        for t in result.selected:
            seen.append(t)
            new_score = score_fn(seen)
            assert new_score > prev_score
            prev_score = new_score


class TestDeterminism:
    def test_same_seed_same_selection(self):
        covers = {f"t{i}": {f"l{i}", f"l{i+1}"} for i in range(10)}
        score_fn = coverage_by_set_membership(covers)
        pool = list(covers.keys())
        r1 = sample_test_suite(pool, score_fn=score_fn, seed=123)
        r2 = sample_test_suite(pool, score_fn=score_fn, seed=123)
        assert r1.selected == r2.selected
        assert r1.log == r2.log

    def test_different_seeds_can_differ(self):
        covers = {f"t{i}": {f"l{i}"} for i in range(20)}
        score_fn = coverage_by_set_membership(covers)
        pool = list(covers.keys())
        results = {
            tuple(sample_test_suite(pool, score_fn=score_fn, seed=s).selected)
            for s in range(10)
        }
        # With 20 independent single-purpose tests, different seeds should
        # explore different orderings/selections at least some of the time.
        assert len(results) > 1


class TestOriginalPoolNotMutated:
    def test_pool_list_is_unchanged_after_sampling(self):
        covers = {"t1": {"a"}, "t2": {"b"}}
        score_fn = coverage_by_set_membership(covers)
        pool = ["t1", "t2"]
        pool_copy = list(pool)
        sample_test_suite(pool, score_fn=score_fn, seed=5)
        assert pool == pool_copy


class TestExhaustedPool:
    def test_unreachable_target_terminates_safely(self):
        # score_fn caps out below the "full pool" score reported for a
        # different-length input would suggest, simulating a pool that can
        # never truly reach the nominal target (e.g. flaky/noisy score).
        def score_fn(selected):
            # Score never exceeds 0.5 no matter what is selected, but the
            # "full pool" evaluation (also computed via score_fn on the
            # entire pool) will likewise be 0.5, so target IS reachable.
            # To simulate a genuinely unreachable target we special-case
            # the full pool to report an inflated number directly is not
            # possible through score_fn's contract, so instead we test
            # that the loop terminates (doesn't hang) even when no
            # candidate ever increases the score above the initial value.
            return 0.0 if selected else 0.0

        result = sample_test_suite(["t1", "t2", "t3"], score_fn=score_fn, seed=1)
        # Target score (0.0) is already met by the empty selection, so the
        # loop terminates immediately without needing to draw candidates -
        # this is the correct, safe behaviour (no infinite loop, no
        # unnecessary work).
        assert result.n_tests_examined == 0
        assert result.selected == []
        assert result.reached_target is True  # achieved (0.0) == target (0.0)

    def test_target_never_reachable_incrementally_still_terminates(self):
        # Pathological score_fn: only jumps to 1.0 once ALL three tests are
        # selected together; any proper subset scores 0.0. Since the
        # algorithm only keeps a test when it strictly increases the score
        # of the *current* selection, no single test is ever kept, the
        # pool is exhausted, and the loop must terminate rather than hang.
        def score_fn(selected):
            return 1.0 if len(selected) == 3 else 0.0

        result = sample_test_suite(["t1", "t2", "t3"], score_fn=score_fn, seed=2)
        assert result.n_tests_examined == 3  # every candidate was tried once
        assert result.selected == []
        assert result.reached_target is False  # achieved (0.0) != target (1.0)
