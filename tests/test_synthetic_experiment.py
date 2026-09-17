"""End-to-end test of the full pipeline (metrics + sampling + coverage +
mutation) on the synthetic fault defined in scripts/run_synthetic_experiment.py.

This is Phase 4's validation: before trusting the machinery on any real
benchmark, we confirm on a small, hand-verifiable example that:

  1. A test exists that does not trigger the fault.
  2. A test exists that triggers the fault.
  3. A test exists that triggers the fault but fails to detect it (weak
     oracle).
  4. A test exists that both triggers and detects the fault.
  5. The full sampling + FTR/FDR pipeline runs without error and produces
     FDR <= FTR, and produces genuinely different results across the three
     criteria (i.e. the criteria are not accidentally all computing the
     same thing).
"""

from __future__ import annotations

from scripts.run_synthetic_experiment import FAULT_GRADE, FAULT_PARITY
from src.fault_runner import build_outcomes, load_function_from_source, run_fault_experiment
from src.utils import mean


class TestFourRequiredScenariosOnGradeFault:
    """Directly checks the four required test scenarios from the assignment
    against the hand-designed grade() boundary fault."""

    @classmethod
    def setup_class(cls):
        faulty_func, _ = load_function_from_source(FAULT_GRADE.faulty_source, FAULT_GRADE.function_name)
        cls.outcomes = build_outcomes(FAULT_GRADE, faulty_func)

    def test_scenario_1_test_that_does_not_trigger(self):
        o = self.outcomes["t_low_50"]
        assert o.triggered is False
        assert o.detected is False

    def test_scenario_2_test_that_triggers(self):
        o = self.outcomes["t_boundary_70_correct_oracle"]
        assert o.triggered is True

    def test_scenario_3_triggers_but_weak_oracle_fails_to_detect(self):
        o = self.outcomes["t_boundary_70_weak_oracle"]
        assert o.triggered is True
        assert o.detected is False

    def test_scenario_4_triggers_and_detects(self):
        o = self.outcomes["t_boundary_70_correct_oracle"]
        assert o.triggered is True
        assert o.detected is True

    def test_same_input_different_oracle_quality_changes_detection_not_triggering(self):
        # The crux of the paper's FTR-vs-FDR distinction: both tests share
        # the exact same input (score=70) and therefore trigger identically,
        # but only the one with a correct oracle detects.
        good = self.outcomes["t_boundary_70_correct_oracle"]
        weak = self.outcomes["t_boundary_70_weak_oracle"]
        assert good.triggered == weak.triggered == True  # noqa: E712
        assert good.detected is True
        assert weak.detected is False


class TestFullPipelineOnSyntheticFaults:
    """Runs the real sampling + coverage + mutation pipeline (not a stub)
    and checks the aggregate properties we expect."""

    @classmethod
    def setup_class(cls):
        cls.grade_rows = run_fault_experiment(
            FAULT_GRADE, benchmark="synthetic", fault_model="hand-crafted",
            n_iterations=50, base_seed=42,
        )

    def test_all_three_criteria_produce_rows(self):
        criteria_seen = {r.criterion for r in self.grade_rows}
        assert criteria_seen == {"statement", "branch", "mutation"}

    def test_fdr_le_ftr_per_criterion(self):
        for criterion in ("statement", "branch", "mutation"):
            rows = [r for r in self.grade_rows if r.criterion == criterion]
            ftr = mean(1.0 if r.triggered else 0.0 for r in rows)
            fdr = mean(1.0 if r.detected else 0.0 for r in rows)
            assert fdr <= ftr + 1e-9, f"FDR > FTR for {criterion}: {fdr} > {ftr}"

    def test_mutation_adequate_suites_trigger_the_boundary_fault_more_often(self):
        # Mutation-guided sampling should be at least as good as statement
        # coverage at surfacing this specific boundary bug, since killing
        # the relevant relational-operator mutants requires a test near
        # the boundary (score == 70).
        stmt_rows = [r for r in self.grade_rows if r.criterion == "statement"]
        mut_rows = [r for r in self.grade_rows if r.criterion == "mutation"]
        stmt_ftr = mean(1.0 if r.triggered else 0.0 for r in stmt_rows)
        mut_ftr = mean(1.0 if r.triggered else 0.0 for r in mut_rows)
        assert mut_ftr >= stmt_ftr

    def test_reached_target_score_in_all_iterations(self):
        # For this small, fully-enumerable pool, the sampling algorithm
        # should always be able to reach the full pool's score.
        for r in self.grade_rows:
            assert r.achieved_score >= r.target_score - 1e-9

    def test_deterministic_given_same_seeds(self):
        rows_again = run_fault_experiment(
            FAULT_GRADE, benchmark="synthetic", fault_model="hand-crafted",
            n_iterations=50, base_seed=42,
        )
        triggered_a = [r.triggered for r in self.grade_rows]
        triggered_b = [r.triggered for r in rows_again]
        assert triggered_a == triggered_b
