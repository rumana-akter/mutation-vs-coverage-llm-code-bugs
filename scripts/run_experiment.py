"""Phase 8/9: the real HumanEval+ pilot experiment.

Runs the full Section V protocol (100 iterations x 3 criteria) on every
real, Claude/Haiku-generated fault found during the pilot (see
EXPERIMENT_LOG.md Entries 6-9 for the full exploratory process: 3 rounds
with Claude/Sonnet-generated candidates - original and under-specified
prompts, on 6 different HumanEval tasks - produced 0/45 faults; a 4th round
using Haiku (a weaker model, mirroring the paper's inclusion of
weaker/stronger models side by side) produced a real fault on
`how_many_times`, the classic non-overlap-counting mistake).

This script is intentionally explicit about which generation batch is used
for each task, rather than silently picking "whichever worked" - the
manifest below records, for every attempted task, which artifact files were
actually used to build the final fault set, so the provenance of every
result is traceable back to EXPERIMENT_LOG.md.

IMPORTANT: this is a FOCUSED METHODOLOGICAL REPRODUCTION using
Claude-Sonnet- and Claude-Haiku-generated substitute artifacts, not the
paper's original faults/tests/models. See PLAN.md Section 9 and
report/report.md for the full set of assumptions and deviations this
implies. Results here must never be presented as reproducing the paper's
actual Table IV values.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.fault_runner import run_fault_experiment
from src.humaneval_pilot import classify_candidates, parse_candidates, parse_test_pool
from src.utils import write_csv, write_json

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"
GEN_DIR = DATA_DIR / "pilot_generation"

# Manifest: for each task actually attempted in the pilot, which candidate
# file was used to build the FINAL fault-selection decision, and which
# "fault_model" label to tag it with in the raw results. Where multiple
# generation attempts were made (see EXPERIMENT_LOG.md), we use the LAST
# attempt's candidates (the one closest to what would be used going
# forward), and record ALL attempts' null results in the classification
# report for transparency.
TASK_MANIFEST = [
    {
        "task_id": "HumanEval/0",
        "entry_point": "has_close_elements",
        "candidates_file": "has_close_elements_candidates_v3_haiku.txt",
        "fault_model": "claude-haiku-4-5",
    },
    {
        "task_id": "HumanEval/3",
        "entry_point": "below_zero",
        "candidates_file": "below_zero_candidates_v3_haiku.txt",
        "fault_model": "claude-haiku-4-5",
    },
    {
        "task_id": "HumanEval/18",
        "entry_point": "how_many_times",
        "candidates_file": "how_many_times_candidates_v3_haiku.txt",
        "fault_model": "claude-haiku-4-5",
    },
    {
        "task_id": "HumanEval/33",
        "entry_point": "sort_third",
        "candidates_file": "sort_third_candidates_v3_haiku.txt",
        "fault_model": "claude-haiku-4-5",
    },
    {
        "task_id": "HumanEval/43",
        "entry_point": "pairs_sum_to_zero",
        "candidates_file": "pairs_sum_to_zero_candidates_v3_haiku.txt",
        "fault_model": "claude-haiku-4-5",
    },
    {
        "task_id": "HumanEval/10",
        "entry_point": "make_palindrome",
        "candidates_file": "make_palindrome_candidates_v3_haiku.txt",
        "fault_model": "claude-haiku-4-5",
    },
    {
        "task_id": "HumanEval/11",
        "entry_point": "string_xor",
        "candidates_file": "string_xor_candidates_v3_haiku.txt",
        "fault_model": "claude-haiku-4-5",
    },
    {
        "task_id": "HumanEval/12",
        "entry_point": "longest",
        "candidates_file": "longest_candidates_v3_haiku.txt",
        "fault_model": "claude-haiku-4-5",
    },
    {
        "task_id": "HumanEval/26",
        "entry_point": "remove_duplicates",
        "candidates_file": "remove_duplicates_candidates_v3_haiku.txt",
        "fault_model": "claude-haiku-4-5",
    },
    {
        "task_id": "HumanEval/28",
        "entry_point": "concatenate",
        "candidates_file": "concatenate_candidates_v3_haiku.txt",
        "fault_model": "claude-haiku-4-5",
    },
    {
        "task_id": "HumanEval/40",
        "entry_point": "triples_sum_to_zero",
        "candidates_file": "triples_sum_to_zero_candidates_v3_haiku.txt",
        "fault_model": "claude-haiku-4-5",
    },
    {
        "task_id": "HumanEval/76",
        "entry_point": "is_simple_power",
        "candidates_file": "is_simple_power_candidates_v3_haiku.txt",
        "fault_model": "claude-haiku-4-5",
    },
    {
        "task_id": "HumanEval/96",
        "entry_point": "count_up_to",
        "candidates_file": "count_up_to_candidates_v3_haiku.txt",
        "fault_model": "claude-haiku-4-5",
    },
    {
        "task_id": "HumanEval/116",
        "entry_point": "sort_array",
        "candidates_file": "sort_array_candidates_v3_haiku.txt",
        "fault_model": "claude-haiku-4-5",
    },
    {
        "task_id": "HumanEval/128",
        "entry_point": "prod_signs",
        "candidates_file": "prod_signs_candidates_v3_haiku.txt",
        "fault_model": "claude-haiku-4-5",
    },
    {
        "task_id": "HumanEval/135",
        "entry_point": "can_arrange",
        "candidates_file": "can_arrange_candidates_v3_haiku.txt",
        "fault_model": "claude-haiku-4-5",
    },
    {
        "task_id": "HumanEval/154",
        "entry_point": "cycpattern_check",
        "candidates_file": "cycpattern_check_candidates_v3_haiku.txt",
        "fault_model": "claude-haiku-4-5",
    },
    {
        "task_id": "HumanEval/89",
        "entry_point": "encrypt",
        "candidates_file": "encrypt_candidates_v3_haiku.txt",
        "fault_model": "claude-haiku-4-5",
    },
    {
        "task_id": "HumanEval/109",
        "entry_point": "move_one_ball",
        "candidates_file": "move_one_ball_candidates_v3_haiku.txt",
        "fault_model": "claude-haiku-4-5",
    },
    {
        "task_id": "HumanEval/137",
        "entry_point": "compare_one",
        "candidates_file": "compare_one_candidates_v3_haiku.txt",
        "fault_model": "claude-haiku-4-5",
    },
]


def main() -> None:
    tasks = json.loads((DATA_DIR / "pilot_humaneval_tasks.json").read_text(encoding="utf-8"))

    selection_report = []
    all_rows = []
    base_seed = 5000

    for entry in TASK_MANIFEST:
        task_id = entry["task_id"]
        entry_point = entry["entry_point"]
        task = tasks[task_id]
        reference_source = task["prompt"] + task["canonical_solution"]

        candidates_text = (GEN_DIR / entry["candidates_file"]).read_text(encoding="utf-8")
        candidates = parse_candidates(candidates_text)

        tests_text = (GEN_DIR / f"{entry_point}_tests.json").read_text(encoding="utf-8")
        tests = parse_test_pool(tests_text, test_id_prefix=entry_point)

        reports = classify_candidates(task_id, entry_point, reference_source, candidates, tests)
        faulty_reports = [r for r in reports if r.is_faulty]

        record = {
            "task_id": task_id,
            "entry_point": entry_point,
            "fault_model": entry["fault_model"],
            "n_candidates": len(candidates),
            "n_faulty_candidates": len(faulty_reports),
        }

        if not faulty_reports:
            record["outcome"] = "no_fault_found"
            selection_report.append(record)
            print(f"{task_id} ({entry_point}): no faulty candidate found (0/{len(candidates)})")
            continue

        # Paper's rule: keep the single hardest (highest-difficulty) fault
        # per task. Ties are broken by candidate index (first one found),
        # documented rather than hidden.
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
            fault_model=entry["fault_model"],
            n_iterations=100,
            base_seed=base_seed,
        )
        all_rows.extend(rows)
        base_seed += 10000

    write_json(RESULTS_DIR / "real_experiment_fault_selection.json", selection_report)
    print(f"\nWrote {RESULTS_DIR / 'real_experiment_fault_selection.json'}")

    if all_rows:
        fieldnames = list(all_rows[0].__dict__.keys())
        dict_rows = [r.__dict__ for r in all_rows]
        raw_path = RESULTS_DIR / "real_experiment_raw_results.csv"
        write_csv(raw_path, dict_rows, fieldnames)
        print(f"Wrote {raw_path} ({len(dict_rows)} rows, from {len(all_rows) // 300} fault(s))")
    else:
        print("\nNo faults found in any task - no raw results to write.")
        print("This is a legitimate null result; see EXPERIMENT_LOG.md.")


if __name__ == "__main__":
    main()
