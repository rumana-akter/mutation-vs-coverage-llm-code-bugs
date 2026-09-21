# Reproducing Table IV — Test Adequacy for LLM-Generated Code

## Objective

Reproduce the methodology behind **Table IV** of *"How effective are
traditional test criteria at detecting bugs in large language models
generated code?"* (arXiv:2609.09315): for LLM-generated faulty code, do
statement, branch, and mutation coverage predict fault detection? The
paper's own faults, test pools, and fault-generating models are not
publicly available (it is a very recent preprint; search documented in
`PLAN.md`). This is therefore a **reduced methodological reproduction**:
the same definitions and sampling procedure, applied to an independently
constructed, much smaller dataset.

## What I did

- Implemented the paper's Fault Trigger Rate / Fault Detection Rate
  definitions and its randomized, criterion-guided sampling procedure
  (`src/metrics.py`, `src/sampling.py`).
- Validated the pipeline on a hand-crafted synthetic example before using
  it on real code.
- Ran it on a **40-task HumanEval subset**, generating **200 candidate
  implementations** (Claude Sonnet, then Claude Haiku 4.5, blind to the
  reference solution) and their test pools.
- Measured statement coverage, branch coverage (`coverage.py`), and
  mutation testing (a custom `ast`-based engine, since the paper does not
  specify a tool) via **100 randomized sampling iterations** per selected
  case per criterion.
- Ran a post-hoc semantic audit of every selected case against the
  original task specification, not just the reference implementation.

## Main results

**Inclusive result** (all 8 automatically selected cases,
`results/real_experiment_combined_table_iv.csv`):

| Criterion | FTR | FDR |
|---|---|---|
| Mutation | 0.950 | 0.700 |
| Branch | 0.633 | 0.484 |
| Statement | 0.633 | 0.484 |

The pipeline automatically selected 8 behavioral divergences between
candidate and reference code. A semantic audit of each (full reasoning in
`FINAL_RESULTS_AUDIT.md`) found **5 clear genuine faults**, **1 uncertain
case** (`encrypt` — the spec never disambiguates uppercase-letter
handling), **1 numerical-equivalence artifact** (`find_zero` — two
independent root-finders converging to slightly different floats), and
**1 benchmark/reference defect** (`valid_date` — the real HumanEval
reference solution has an operator-precedence bug).

Excluding only the artifact and the reference defect (sensitivity
analysis, keeping the uncertain case):

| Criterion | FTR | FDR |
|---|---|---|
| Mutation | 0.933 | 0.933 |
| Branch | 0.645 | 0.645 |
| Statement | 0.645 | 0.645 |

## Main observations

- Mutation-guided suites triggered more faults than branch/statement
  suites in this sample, consistent with the paper's general direction.
- Unlike the paper, this reduced experiment did not reproduce a large
  FTR/FDR gap once the two questionable cases were excluded — FTR equaled
  FDR exactly on the remaining 6 cases.
- Benchmark/reference correctness is not guaranteed: one of HumanEval's
  own canonical solutions has a verifiable bug, which affects differential
  fault classification.
- The sample (8 cases from 40 tasks, one substitute model) is too small to
  support any quantitative conclusion about HumanEval as a benchmark.

## Reproducibility

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt

pytest -q                                    # unit tests (74 passed)
python -m scripts.run_synthetic_experiment   # hand-crafted validation

# Real experiment, from committed artifacts (no regeneration needed)
python -m scripts.run_experiment
python -m scripts.run_experiment_batch2
python -m scripts.combine_batches
python scripts\build_table_iv.py results\real_experiment_combined_raw_results.csv results\real_experiment_combined_table_iv
```

## Repository structure

- `src/` — definitions, sampling, coverage, mutation engine
- `tests/` — unit tests (74)
- `scripts/` — runnable experiments and table-building
- `data/` — HumanEval task prompts and all generated candidates/tests
- `results/` — CSV/Markdown outputs, all produced by the scripts above
- `report/report.md` — full write-up (method, results, limitations)
- `FINAL_RESULTS_AUDIT.md` — the semantic audit behind the sensitivity
  result above

Detailed development history and validation notes (every debugging
incident, methodological decision, and prior audit) are kept for
transparency in `EXPERIMENT_LOG.md`, `AUDIT.md`, `PLAN.md`, and
`FINAL_STATUS.md`. These are optional supplementary material — nothing
above depends on reading them.

## Limitations

- Small sample: 8 cases from 40 attempted tasks, no statistical power.
- One substitute fault-generating model family (Claude), not the paper's
  five.
- Custom mutation engine, not an established third-party tool.
- Test oracles are `{args, expected_output}` equality checks, not
  free-form assertions.
- HumanEval only — MBPP, BigCodeBench, and NaturalCodeBench are out of
  scope.
