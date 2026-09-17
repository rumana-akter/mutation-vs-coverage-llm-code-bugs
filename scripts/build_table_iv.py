"""Aggregate raw per-iteration sampling results into a Table-IV-shaped
summary table.

Usage:
    python scripts/build_table_iv.py <raw_results.csv> <output_prefix>

Reads a raw results CSV with (at least) the columns produced by
``src.fault_runner.RawResultRow`` (benchmark, fault_model, fault_id,
criterion, iteration, triggered, detected, ...) and writes:

    <output_prefix>.csv  - machine-readable summary
    <output_prefix>.md   - Markdown table for the report

The aggregation mirrors the paper's own two-level averaging (Section V):
for each fault, average FTR/FDR (i.e. the fraction of the 100 sampled
suites that trigger/detect it) across iterations; then average those
per-fault rates across all faults in a (benchmark, fault_model) cell. This
is NOT the same as flattening all iterations across all faults into one
big average (which would silently overweight faults that happen to have
more, or fewer, valid sampling iterations) - it reproduces the paper's
described protocol exactly.

This script never hardcodes any numbers; every value comes from the raw
CSV passed in.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd


def aggregate(raw_df: pd.DataFrame) -> pd.DataFrame:
    """Two-level mean: per-fault rate across iterations, then mean across
    faults, grouped by (benchmark, fault_model, criterion)."""

    per_fault = (
        raw_df.groupby(["benchmark", "fault_model", "criterion", "fault_id"])
        .agg(FTR=("triggered", "mean"), FDR=("detected", "mean"))
        .reset_index()
    )

    summary = (
        per_fault.groupby(["benchmark", "fault_model", "criterion"])
        .agg(FTR=("FTR", "mean"), FDR=("FDR", "mean"), n_faults=("fault_id", "nunique"))
        .reset_index()
    )

    return summary


def pivot_table_iv_shape(summary: pd.DataFrame) -> pd.DataFrame:
    """Reshape the long summary into Table IV's wide shape: one row per
    (benchmark, fault_model), one FTR/FDR column pair per criterion."""
    wide = summary.pivot_table(
        index=["benchmark", "fault_model"],
        columns="criterion",
        values=["FTR", "FDR"],
    )
    # Order columns as Mutation, Branch, Statement x (FTR, FDR), matching
    # the paper's Table IV column order, when those criteria are present.
    ordered_criteria = [c for c in ("mutation", "branch", "statement") if c in summary["criterion"].unique()]
    wide = wide.reindex(
        columns=pd.MultiIndex.from_product([["FTR", "FDR"], ordered_criteria]),
    )
    wide.columns = [f"{crit}_{metric}" for metric, crit in wide.columns]
    return wide.reset_index()


# Caption prepended to the generated .md file so it can never be mistaken
# for the paper's original Table IV, per the assignment's labeling
# requirement (Phase 10). Chosen by matching the input filename rather
# than a CLI flag, since this script must stay a pure "raw CSV in, table
# out" tool with no hardcoded result values.
_LABELS = {
    "synthetic_raw_results.csv": (
        "Synthetic validation example (hand-crafted faults) — "
        "NOT a benchmark reproduction, see report/report.md Section 6."
    ),
    "real_experiment_raw_results.csv": (
        "Focused methodological reproduction of Table IV — HumanEval+ subset "
        "using Claude-generated artifacts. NOT the paper's original Table IV "
        "values — see report/report.md Sections 4 and 12."
    ),
}


def main() -> None:
    if len(sys.argv) != 3:
        print("Usage: python scripts/build_table_iv.py <raw_results.csv> <output_prefix>")
        sys.exit(1)

    raw_path = Path(sys.argv[1])
    out_prefix = Path(sys.argv[2])
    out_prefix.parent.mkdir(parents=True, exist_ok=True)

    raw_df = pd.read_csv(raw_path)
    summary = aggregate(raw_df)
    wide = pivot_table_iv_shape(summary)

    label = _LABELS.get(raw_path.name)

    wide.to_csv(out_prefix.with_suffix(".csv"), index=False)
    with open(out_prefix.with_suffix(".md"), "w", encoding="utf-8") as f:
        if label:
            f.write(f"**{label}**\n\n")
        f.write(wide.to_markdown(index=False, floatfmt=".3f"))
        f.write("\n")

    print(wide.to_string(index=False))
    print(f"\nWrote {out_prefix.with_suffix('.csv')} and {out_prefix.with_suffix('.md')}")


if __name__ == "__main__":
    main()
