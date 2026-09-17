"""Phase 8 data preparation: extract the 20 pilot task prompts and
reference (canonical) solutions from the `human-eval` package's bundled
HumanEval.jsonl.gz into data/pilot_humaneval_tasks.json.

This is the script that originally produced data/pilot_humaneval_tasks.json
during this reproduction (see EXPERIMENT_LOG.md Entries 6-10 for how the
task list grew from 3 to 20 tasks across several rounds). It is safe to
re-run - it always regenerates the same 20-task file from the same source
package, and is provided so the data preparation step is itself
reproducible rather than a one-off interactive action.

Note on HumanEval vs HumanEval+: we use plain HumanEval's canonical
solutions as ground truth. These are identical to HumanEval+'s reference
implementations for every task (HumanEval+ only strengthens the
benchmark-provided *test suite*, which we don't use - we generate our own
test pool per the paper's own protocol). See report/report.md Section 4.
"""

from __future__ import annotations

import json
from pathlib import Path

from human_eval.data import read_problems

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# The 20 HumanEval task IDs used in the pilot, in the order they were
# attempted (see EXPERIMENT_LOG.md for why each batch was added).
PILOT_TASK_IDS = [
    "HumanEval/0",  # has_close_elements
    "HumanEval/3",  # below_zero
    "HumanEval/8",  # sum_product (Sonnet-only rounds; no fault found, not in the final 20-task Haiku manifest)
    "HumanEval/18",  # how_many_times
    "HumanEval/33",  # sort_third
    "HumanEval/43",  # pairs_sum_to_zero
    "HumanEval/10",  # make_palindrome
    "HumanEval/11",  # string_xor
    "HumanEval/12",  # longest
    "HumanEval/26",  # remove_duplicates
    "HumanEval/28",  # concatenate
    "HumanEval/40",  # triples_sum_to_zero
    "HumanEval/76",  # is_simple_power
    "HumanEval/96",  # count_up_to
    "HumanEval/116",  # sort_array
    "HumanEval/128",  # prod_signs
    "HumanEval/135",  # can_arrange
    "HumanEval/154",  # cycpattern_check
    "HumanEval/89",  # encrypt
    "HumanEval/109",  # move_one_ball
    "HumanEval/137",  # compare_one
]


def main() -> None:
    problems = read_problems()
    out = {}
    for task_id in PILOT_TASK_IDS:
        p = problems[task_id]
        out[task_id] = {
            "task_id": task_id,
            "entry_point": p["entry_point"],
            "prompt": p["prompt"],
            "canonical_solution": p["canonical_solution"],
        }

    out_path = DATA_DIR / "pilot_humaneval_tasks.json"
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"Wrote {out_path} ({len(out)} tasks)")


if __name__ == "__main__":
    main()
