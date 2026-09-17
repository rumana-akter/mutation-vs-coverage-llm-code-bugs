"""Phase 4: synthetic, hand-controlled reproduction of the Table IV
protocol, on two small, hand-written faulty functions.

This is NOT LLM-generated data - it exists purely to validate that our
FTR/FDR/sampling/coverage/mutation machinery behaves correctly end-to-end
on a case small enough to verify by hand, before it is trusted on any real
benchmark. See PLAN.md Section 6/9 and report/report.md Section 4.

The two synthetic faults are constructed to exercise all four scenarios the
assignment asks for:

  1. A test that does not trigger the fault (e.g. grade(50) -> "F" on both
     the reference and the faulty implementation).
  2. A test that triggers the fault (grade(70) differs: "C" vs "F").
  3. A test that triggers the fault but has a weak/wrong oracle, so it
     fails to detect it (grade(70) again, but the generated test's own
     expected value happens to match the *faulty* output "F" rather than
     the correct output "C" - representing an LLM-generated test whose
     assertion was itself derived from buggy reasoning, mirroring the
     paper's discussion of oracle bias).
  4. A test that both triggers and detects the fault (grade(70) with the
     correct expected value "C").
"""

from __future__ import annotations

from pathlib import Path

from src.fault_runner import FaultSpec, OracleTestCase, run_fault_experiment
from src.utils import mean, write_csv

RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"

# ---------------------------------------------------------------------------
# Fault 1: boundary-condition bug in a letter-grade function.
# Bug: uses `score > 70` instead of `score >= 70`, so score == 70 is
# misclassified as "F" instead of "C". A genuinely hard-to-trigger fault:
# only inputs equal to exactly 70 reveal it.
# ---------------------------------------------------------------------------

REFERENCE_GRADE_SOURCE = """
def grade(score):
    if score >= 90:
        return "A"
    elif score >= 80:
        return "B"
    elif score >= 70:
        return "C"
    else:
        return "F"
"""

FAULTY_GRADE_SOURCE = """
def grade(score):
    if score >= 90:
        return "A"
    elif score >= 80:
        return "B"
    elif score > 70:
        return "C"
    else:
        return "F"
"""


def _reference_grade(score):
    if score >= 90:
        return "A"
    elif score >= 80:
        return "B"
    elif score >= 70:
        return "C"
    else:
        return "F"


GRADE_TESTS = [
    # 1. Does not trigger: both implementations agree.
    OracleTestCase("t_low_50", args=(50,), expected_output="F"),
    OracleTestCase("t_low_60", args=(60,), expected_output="F"),
    OracleTestCase("t_mid_c_75", args=(75,), expected_output="C"),
    OracleTestCase("t_mid_b_85", args=(85,), expected_output="B"),
    OracleTestCase("t_high_95", args=(95,), expected_output="A"),
    OracleTestCase("t_boundary_80", args=(80,), expected_output="B"),
    OracleTestCase("t_boundary_90", args=(90,), expected_output="A"),
    # 4. Triggers AND detects: correct oracle catches the boundary bug.
    OracleTestCase("t_boundary_70_correct_oracle", args=(70,), expected_output="C"),
    # 3. Triggers but does NOT detect: the oracle's expected value ("F")
    #    matches the faulty output rather than the true output ("C") -
    #    a weak/wrong assertion that fails to catch the discrepancy.
    OracleTestCase("t_boundary_70_weak_oracle", args=(70,), expected_output="F"),
]

FAULT_GRADE = FaultSpec(
    fault_id="synthetic_grade_boundary_fault",
    faulty_source=FAULTY_GRADE_SOURCE,
    function_name="grade",
    reference_func=_reference_grade,
    tests=GRADE_TESTS,
)

# ---------------------------------------------------------------------------
# Fault 2: a trivial, easy-to-trigger fault (inverted parity check), used
# as a contrasting second data point so the synthetic table aggregates
# across more than one fault, like Table IV aggregates across many faults
# per benchmark/model cell.
# ---------------------------------------------------------------------------

REFERENCE_PARITY_SOURCE = """
def is_even_positive(n):
    if n <= 0:
        return False
    return n % 2 == 0
"""

FAULTY_PARITY_SOURCE = """
def is_even_positive(n):
    if n <= 0:
        return False
    return n % 2 == 1
"""


def _reference_is_even_positive(n):
    if n <= 0:
        return False
    return n % 2 == 0


PARITY_TESTS = [
    OracleTestCase("t_neg_5", args=(-5,), expected_output=False),  # does not trigger (both False)
    OracleTestCase("t_zero", args=(0,), expected_output=False),  # does not trigger
    OracleTestCase("t_two", args=(2,), expected_output=True),  # triggers + detects (ref True, faulty False)
    OracleTestCase("t_three", args=(3,), expected_output=False),  # triggers + detects (ref False, faulty True)
    OracleTestCase("t_four_weak_oracle", args=(4,), expected_output=False),  # triggers, weak oracle matches faulty
]

FAULT_PARITY = FaultSpec(
    fault_id="synthetic_parity_inverted_fault",
    faulty_source=FAULTY_PARITY_SOURCE,
    function_name="is_even_positive",
    reference_func=_reference_is_even_positive,
    tests=PARITY_TESTS,
)


def main() -> None:
    all_rows = []
    for fault, base_seed in [(FAULT_GRADE, 1000), (FAULT_PARITY, 2000)]:
        rows = run_fault_experiment(
            fault,
            benchmark="synthetic",
            fault_model="hand-crafted",
            n_iterations=100,
            base_seed=base_seed,
        )
        all_rows.extend(rows)
        print(f"Ran {fault.fault_id}: {len(rows)} sampled-suite evaluations")

    fieldnames = list(all_rows[0].__dict__.keys())
    dict_rows = [r.__dict__ for r in all_rows]
    raw_path = RESULTS_DIR / "synthetic_raw_results.csv"
    write_csv(raw_path, dict_rows, fieldnames)
    print(f"Wrote {raw_path} ({len(dict_rows)} rows)")

    # Quick sanity summary per criterion (full build_table_iv.py does the
    # official Table-IV-shaped aggregation).
    for criterion in ("statement", "branch", "mutation"):
        crit_rows = [r for r in all_rows if r.criterion == criterion]
        ftr = mean(1.0 if r.triggered else 0.0 for r in crit_rows)
        fdr = mean(1.0 if r.detected else 0.0 for r in crit_rows)
        print(f"{criterion:>10s}: FTR={ftr:.3f}  FDR={fdr:.3f}  (n={len(crit_rows)})")


if __name__ == "__main__":
    main()
