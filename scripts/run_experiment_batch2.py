"""Controlled scale-up batch 2: 20 additional HumanEval+ tasks, selected via
a predeclared, fixed-seed random rule (see data/scaleup_task_selection_record.json),
under the SAME frozen methodology as the originally audited 20-task batch
(scripts/run_experiment.py): same FTR/FDR definitions, same normalization,
same oracle representation, same coverage/mutation/difficulty/sampling
implementation, same fault-selection rule, same Claude Haiku 4.5
candidate-generation setup (5 candidates/task, blind, original prompts).

The only infrastructure difference from the original batch is the timeout
hardening added in EXPERIMENT_LOG.md Entries 12-13 (a persistent worker
process per candidate/reference call, with coverage instrumentation run
inside that same process) - required because it was discovered mid-project
that a real generated candidate (greatest_common_divisor) could hang the
harness indefinitely. That hardening does not change any FTR/FDR
definition, coverage/mutation semantics, or the sampling algorithm; see
EXPERIMENT_LOG.md for the full account.

Results are written to batch2-prefixed files, kept separate from the
original batch's results (results/real_experiment_raw_results.csv etc.) -
see scripts/combine_batches.py for how the two are merged into a combined
dataset without overwriting either.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.fault_runner import run_fault_experiment
from src.humaneval_pilot import classify_candidates, parse_candidates, parse_test_pool
from src.metrics import DEFAULT_CALL_TIMEOUT_SECONDS
from src.utils import write_csv, write_json

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"
GEN_DIR = DATA_DIR / "pilot_generation"

# Batch 2 manifest: the 20 tasks selected in
# data/scaleup_task_selection_record.json (random.Random(42).sample of the
# 143 HumanEval tasks not attempted in batch 1). Same generation setup as
# the batch that produced 4 of batch 1's 5 faults: Claude Haiku 4.5, blind,
# 5 candidates/task, ORIGINAL (not under-specified) prompts.
TASK_MANIFEST = [
    {"task_id": "HumanEval/38", "entry_point": "decode_cyclic"},
    {"task_id": "HumanEval/9", "entry_point": "rolling_max"},
    {"task_id": "HumanEval/83", "entry_point": "starts_one_ends"},
    {"task_id": "HumanEval/74", "entry_point": "total_match"},
    {"task_id": "HumanEval/69", "entry_point": "search"},
    {"task_id": "HumanEval/47", "entry_point": "median"},
    {"task_id": "HumanEval/36", "entry_point": "fizz_buzz"},
    {"task_id": "HumanEval/160", "entry_point": "do_algebra"},
    {"task_id": "HumanEval/31", "entry_point": "is_prime"},
    {"task_id": "HumanEval/125", "entry_point": "split_words"},
    {"task_id": "HumanEval/14", "entry_point": "all_prefixes"},
    {"task_id": "HumanEval/13", "entry_point": "greatest_common_divisor"},
    {"task_id": "HumanEval/32", "entry_point": "find_zero"},
    {"task_id": "HumanEval/67", "entry_point": "fruit_distribution"},
    {"task_id": "HumanEval/71", "entry_point": "triangle_area"},
    {"task_id": "HumanEval/149", "entry_point": "sorted_list_sum"},
    {"task_id": "HumanEval/62", "entry_point": "derivative"},
    {"task_id": "HumanEval/124", "entry_point": "valid_date"},
    {"task_id": "HumanEval/68", "entry_point": "pluck"},
    {"task_id": "HumanEval/132", "entry_point": "is_nested"},
]
FAULT_MODEL = "claude-haiku-4-5"


def main() -> None:
    tasks = json.loads((DATA_DIR / "pilot_humaneval_tasks.json").read_text(encoding="utf-8"))

    selection_report = []
    all_rows = []
    base_seed = 100_000  # distinct seed range from batch 1 (base_seed started at 5000)
    total_candidates = 0
    total_tests_generated = 0

    for entry in TASK_MANIFEST:
        task_id = entry["task_id"]
        entry_point = entry["entry_point"]
        task = tasks[task_id]
        reference_source = task["prompt"] + task["canonical_solution"]

        candidates_text = (GEN_DIR / f"{entry_point}_candidates_v3_haiku.txt").read_text(encoding="utf-8")
        candidates = parse_candidates(candidates_text)
        total_candidates += len(candidates)

        tests_text = (GEN_DIR / f"{entry_point}_tests.json").read_text(encoding="utf-8")
        tests = parse_test_pool(tests_text, test_id_prefix=entry_point)
        total_tests_generated += len(tests)

        reports = classify_candidates(task_id, entry_point, reference_source, candidates, tests)
        faulty_reports = [r for r in reports if r.is_faulty]

        record = {
            "task_id": task_id,
            "entry_point": entry_point,
            "fault_model": FAULT_MODEL,
            "n_candidates": len(candidates),
            "n_faulty_candidates": len(faulty_reports),
            "n_tests": len(tests),
        }

        if not faulty_reports:
            record["outcome"] = "no_fault_found"
            selection_report.append(record)
            print(f"{task_id} ({entry_point}): no faulty candidate found (0/{len(candidates)})")
            continue

        best = max(faulty_reports, key=lambda r: r.difficulty)
        record["outcome"] = "fault_selected"
        record["selected_candidate_index"] = best.candidate_index
        record["difficulty"] = best.difficulty
        record["meets_paper_threshold_0.75"] = best.difficulty >= 0.75
        selection_report.append(record)

        print(
            f"{task_id} ({entry_point}): {len(faulty_reports)}/{len(candidates)} candidates faulty, "
            f"selected candidate {best.candidate_index} (difficulty={best.difficulty:.3f}, "
            f"meets paper's 0.75 threshold={best.difficulty >= 0.75})"
        )

        from src.fault_runner import FaultSpec
        from src.humaneval_pilot import load_callable

        reference_func = load_callable(reference_source, entry_point)
        fault_spec = FaultSpec(
            fault_id=f"{task_id.replace('/', '_')}_candidate_{best.candidate_index}",
            faulty_source=best.source,
            function_name=entry_point,
            reference_func=reference_func,
            tests=tests,
        )

        rows = run_fault_experiment(
            fault_spec,
            benchmark="HumanEval+",
            fault_model=FAULT_MODEL,
            n_iterations=100,
            base_seed=base_seed,
        )
        all_rows.extend(rows)
        base_seed += 10000

    write_json(RESULTS_DIR / "real_experiment_batch2_fault_selection.json", selection_report)
    print(f"\nWrote {RESULTS_DIR / 'real_experiment_batch2_fault_selection.json'}")

    if all_rows:
        fieldnames = list(all_rows[0].__dict__.keys())
        dict_rows = [r.__dict__ for r in all_rows]
        raw_path = RESULTS_DIR / "real_experiment_batch2_raw_results.csv"
        write_csv(raw_path, dict_rows, fieldnames)
        print(f"Wrote {raw_path} ({len(dict_rows)} rows)")

    # Run metadata: the configuration check requested before this run -
    # one consistent timeout value, recorded alongside the results.
    run_metadata = {
        "batch": 2,
        "n_tasks_attempted": len(TASK_MANIFEST),
        "n_candidates_generated": total_candidates,
        "n_tests_generated": total_tests_generated,
        "n_tasks_with_fault": sum(1 for r in selection_report if r["outcome"] == "fault_selected"),
        "n_iterations_per_criterion": 100,
        "criteria": ["statement", "branch", "mutation"],
        "fault_model": FAULT_MODEL,
        "call_timeout_seconds": DEFAULT_CALL_TIMEOUT_SECONDS,
        "timeout_applied_uniformly_to": [
            "build_outcomes (trigger/detect computation)",
            "measure_per_test_coverage (statement/branch)",
            "build_mutation_model (mutation scoring)",
        ],
        "task_selection_record": "data/scaleup_task_selection_record.json",
    }
    write_json(RESULTS_DIR / "real_experiment_batch2_run_metadata.json", run_metadata)
    print(f"Wrote {RESULTS_DIR / 'real_experiment_batch2_run_metadata.json'}")


if __name__ == "__main__":
    main()
