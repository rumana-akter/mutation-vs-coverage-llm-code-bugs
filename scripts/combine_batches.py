"""Combine batch 1 (the originally audited 20-task manifest) and batch 2
(the 20-task controlled scale-up) raw results into one combined dataset,
without overwriting either individual batch's files.

Usage: python -m scripts.combine_batches
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"


def main() -> None:
    batch1 = pd.read_csv(RESULTS_DIR / "real_experiment_raw_results.csv")
    batch2 = pd.read_csv(RESULTS_DIR / "real_experiment_batch2_raw_results.csv")

    batch1 = batch1.copy()
    batch2 = batch2.copy()
    batch1["batch"] = 1
    batch2["batch"] = 2

    combined = pd.concat([batch1, batch2], ignore_index=True)
    out_path = RESULTS_DIR / "real_experiment_combined_raw_results.csv"
    combined.to_csv(out_path, index=False)
    print(f"Wrote {out_path} ({len(combined)} rows = {len(batch1)} batch-1 + {len(batch2)} batch-2)")


if __name__ == "__main__":
    main()
