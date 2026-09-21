# FINAL_STATUS.md

Status snapshot of this reproduction.

## What was completed

- Definitions 1-5 (triggered, detected, FTR, FDR, difficulty), the
  randomized criterion-guided sampling procedure, real statement/branch
  coverage (`coverage.py`), and a custom `ast`-based mutation engine —
  implemented and unit-tested (`src/`, 74 tests passing).
- A hand-crafted synthetic experiment validating the pipeline end to end.
- A real HumanEval pilot: 40 tasks attempted, 200 candidate
  implementations generated (Claude Sonnet, then Haiku 4.5, blind to the
  reference), 8 behavioral divergences automatically selected and run
  through the full 100-iteration × 3-criterion protocol.
- A post-hoc semantic audit of all 8 selected cases against the original
  task specifications (`FINAL_RESULTS_AUDIT.md`).

## Key result

Inclusive result, all 8 selected cases (`results/real_experiment_combined_table_iv.csv`):

| Criterion | FTR | FDR |
|---|---|---|
| Mutation | 0.950 | 0.700 |
| Branch | 0.633 | 0.484 |
| Statement | 0.633 | 0.484 |

The audit classified 5 of the 8 as genuine candidate faults, 1 (`encrypt`)
as uncertain, 1 (`find_zero`) as a numerical-equivalence artifact, and 1
(`valid_date`) as a benchmark/reference defect. Excluding only the
artifact and the reference defect, FTR equals FDR exactly on all three
criteria (0.933/0.933 mutation, 0.645/0.645 branch and statement). Full
reasoning: `report/report.md` and `FINAL_RESULTS_AUDIT.md`.

## What remains unreproduced

- The paper's exact Table IV values — impossible without its unavailable
  artifacts (6,066 faults, 5 models' generations, large test pools).
- MBPP, BigCodeBench, NaturalCodeBench (scoped to HumanEval only).
- Statistical significance testing (Table V) — uninformative at n=8.

## Verification commands

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pytest -q                                    # 74 passed
python -m scripts.run_synthetic_experiment
python -m scripts.run_experiment
python -m scripts.run_experiment_batch2
python -m scripts.combine_batches
python scripts\build_table_iv.py results\real_experiment_combined_raw_results.csv results\real_experiment_combined_table_iv
```

All of the above have been re-run from the committed artifacts and produce
byte-identical results to what is in `results/`.

## Where to look for more detail

`report/report.md` is the main deliverable. `EXPERIMENT_LOG.md`, `AUDIT.md`,
`FINAL_RESULTS_AUDIT.md`, and `PLAN.md` hold the full development history,
methodological decisions, and audit reasoning — supplementary, not required
reading.
