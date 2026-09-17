# FINAL_STATUS.md

Status snapshot at the end of this reproduction session. Written for two
audiences: you (before pushing to GitHub) and future-you (before the
interview with Professor Baudry).

## What was successfully implemented

- `src/metrics.py` — Definitions 1-5 (triggered, detected, FTR, FDR,
  difficulty), exception handling via a `_Raised` sentinel, and a
  `_TimedOut` sentinel (added mid-project — see below) with an explicit,
  documented equality rule: two timeouts compare equal (no observed
  divergence); a timeout is never equal to a normal value or an exception.
  Also `normalize_for_comparison` (added mid-project — see below): a single,
  shared, recursive canonicalization applied symmetrically to every value
  compared, so JSON-sourced test data (list) and native Python return
  values (list or tuple) always compare correctly regardless of which side
  of a comparison they came from.
- `src/sampling.py` — the paper's exact randomized criterion-guided
  sampling protocol (Section V), generic over any monotonic score
  function, deterministic under seeding, with edge cases handled.
- `src/coverage_utils.py` — real statement and branch coverage via
  `coverage.py`, instrumented *inside* the timeout-guarded worker process
  (added mid-project — see below) so coverage tracing and hard execution
  timeouts coexist correctly.
- `src/mutation_utils.py` — a real, custom `ast`-based mutation engine
  (5 operator types: ROR, AOR, BOR, constant perturbation, return-value
  replacement), with a documented, verified limitation (zero mutants on
  argument-free one-liners) that was found and fixed mid-project.
- `src/fault_runner.py` — orchestrates the above into one fault's full
  100-iteration x 3-criteria experiment, with `faulty_timed_out`/
  `reference_timed_out`/`timeout_seconds` provenance fields on every row.
- `src/humaneval_pilot.py` — parses LLM-generated candidates/tests,
  classifies faults against a real reference implementation.
- 74 unit tests, all passing (`pytest -q`), covering the four required
  synthetic scenarios, sampling edge cases, the normalization fix, and the
  timeout mechanism (hang detection, worker recovery, both-sides-timeout
  semantics).

## What was successfully reproduced

- **The synthetic experiment** (fully working, hand-verifiable): a
  boundary-condition bug where mutation-adequate suites achieve FTR 1.00
  vs. statement/branch's 0.49.
- **A real (non-synthetic) Table IV result**, from **8 real faults found
  across 40 HumanEval tasks** (two batches of 20), using Claude-generated
  (Sonnet then Haiku 4.5) candidate code and tests:

  **Batch 1** (originally audited, 5 faults) — `results/real_experiment_table_iv.csv`:

  | benchmark | fault_model | mutation FTR | branch FTR | statement FTR | mutation FDR | branch FDR | statement FDR |
  |---|---|---|---|---|---|---|---|
  | HumanEval+ | claude-haiku-4-5 | 0.920 | 0.574 | 0.574 | 0.920 | 0.574 | 0.574 |

  **Batch 2** (independent scale-up, 3 faults) — `results/real_experiment_batch2_table_iv.csv`:

  | benchmark | fault_model | mutation FTR | branch FTR | statement FTR | mutation FDR | branch FDR | statement FDR |
  |---|---|---|---|---|---|---|---|
  | HumanEval+ | claude-haiku-4-5 | 1.000 | 0.730 | 0.730 | 0.333 | 0.333 | 0.333 |

  **Combined** (8 faults) — `results/real_experiment_combined_table_iv.csv`:

  | benchmark | fault_model | mutation FTR | branch FTR | statement FTR | mutation FDR | branch FDR | statement FDR |
  |---|---|---|---|---|---|---|---|
  | HumanEval+ | claude-haiku-4-5 | 0.950 | 0.633 | 0.633 | 0.700 | 0.484 | 0.484 |

  This is labelled everywhere as a **"Focused methodological reproduction
  of Table IV using Claude-generated artifacts"** — never as a
  reproduction of the paper's actual numbers.

  **Important caveat, not to be glossed over:** 2 of batch 2's 3 faults
  (`find_zero`, `valid_date`) are **not genuine candidate defects** — one
  is a floating-point exact-equality measurement artifact, the other
  traces to a real bug in HumanEval's own canonical solution. Both are
  reported transparently (see `EXPERIMENT_LOG.md` Entry 14 and
  `report/report.md` §11-13) rather than quietly folded into an
  undifferentiated "8 faults" headline number.

## What remains unreproduced

- The paper's exact Table IV values (impossible without its unavailable
  artifacts — 6,066 faults, 5 models' generations, large LLM-Plain test
  pools).
- MBPP, BigCodeBench, NaturalCodeBench (Phase 8 scoped this reproduction
  to HumanEval only).
- RQ2 (cost-efficiency curves) and RQ3 (specification-guided oracle
  repair) — out of scope; Table IV (RQ1) was the assignment's target.
- Statistical significance testing (Table V's Wilcoxon/Vargha-Delaney
  analysis) — meaningless with only 8 faults.

## Major assumptions (full list: `PLAN.md` §9, `report/report.md` §15)

1. Claude (Sonnet, then Haiku 4.5) substitutes for the paper's 5 models.
2. Test oracles are `{args, expected_output}` equality checks, not
   free-form assertion code.
3. Mutation testing uses a small custom `ast`-based engine, not an
   established third-party tool.
4. Scope reduced to HumanEval, 40 tasks across 2 batches, 5 candidates/task.
5. Under-specified prompts are our own constructions, not Larbi et al.'s.
6. Batch 2's 20 tasks were selected via a pre-registered, fixed-seed
   (`random.Random(42)`) sample of the 143 not-yet-attempted tasks —
   recorded in `data/scaleup_task_selection_record.json` before any
   generation began, so the task list was not chosen after seeing results.

## Two infrastructure defects found and fixed mid-project (not methodology bugs)

These were found *during* the scale-up, not the original batch, and both
are execution-safety/harness concerns — neither changes any FTR/FDR
definition, coverage/mutation semantics, or the sampling algorithm.

1. **No execution timeout** (`EXPERIMENT_LOG.md` Entry 12): a generated
   candidate (`greatest_common_divisor`, subtraction-based Euclidean
   algorithm) infinite-loops on a zero input. Fixed with a persistent,
   killable worker **process** (not a thread — threads can't be forcibly
   terminated in Python) and a 5-second timeout, returning a `_TimedOut`
   sentinel. Comparison rule (user-specified): two timeouts are equal (no
   divergence observed); a timeout against anything else is a divergence.
2. **The timeout fix broke coverage measurement** (Entry 13): moving
   execution into a worker process meant `coverage.py`'s process-local
   trace hooks in the parent no longer saw anything, silently zeroing out
   branch/statement FTR/FDR. Caught by re-running the already-audited batch
   as a sanity check before trusting the new infrastructure on new data.
   Fixed by instrumenting coverage *inside* the worker process instead.

Both were caught by re-verifying the already-audited batch produced
byte-identical results before proceeding — this is why that re-verification
step exists in the command list below, not just as a one-time check.

## Exact commands to run yourself before pushing to GitHub

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pytest -q
python -m scripts.run_synthetic_experiment
python scripts\build_table_iv.py results\synthetic_raw_results.csv results\synthetic_table_iv
python -m scripts.prepare_humaneval_tasks
python -m scripts.run_experiment
python scripts\build_table_iv.py results\real_experiment_raw_results.csv results\real_experiment_table_iv
python -m scripts.run_experiment_batch2
python scripts\build_table_iv.py results\real_experiment_batch2_raw_results.csv results\real_experiment_batch2_table_iv
python -m scripts.combine_batches
python scripts\build_table_iv.py results\real_experiment_combined_raw_results.csv results\real_experiment_combined_table_iv
```

All of these were run in this session immediately before finishing, and
produced byte-identical results to what's already committed in `results/`.

## Files you should inspect manually before pushing

- `report/report.md` — the main deliverable; read it end to end once.
- `EXPERIMENT_LOG.md` — the full decision trail: 3 rounds of null results
  before the Haiku switch worked, the normalization audit and fix
  (Entries 11), and the two timeout-related infrastructure defects found
  during the scale-up (Entries 12-13). Long, but it's the honest record of
  what actually happened.
- `AUDIT.md` — the independent methodological audit of the original
  5-fault batch, including the post-fix verification section.
- `data/scaleup_task_selection_record.json` — proof the batch-2 task list
  was fixed-seed and predeclared, not cherry-picked.
- `data/pilot_generation/*_candidates_v3_haiku.txt` for the 8 faulty tasks
  — worth reading the actual code for `find_zero` and `valid_date` once,
  to see for yourself why those two are not genuine bugs.
- `results/real_experiment_per_fault_table.csv` — the single table that
  shows all 8 faults' difficulty, test count, timeout count, and FTR/FDR
  side by side.
- `src/mutation_utils.py`'s module docstring — explains the mutmut
  evaluation and the return-value-mutation fix.
- `requirements.txt` — pytest, coverage, pandas, tabulate, human-eval,
  cloudpickle (added for the timeout mechanism) — no ML/API packages,
  since we never called an external LLM API directly.

## Questions Professor Baudry might ask, and short answers

**"Why didn't you use the paper's actual faults?"** No replication package
exists — documented via an 8-source search before writing any code.

**"Why Claude and not the paper's 5 models?"** No API access to the
paper's models in this environment; using Claude was the explicitly
user-approved fallback, documented before implementation.

**"Why did you switch from Sonnet to Haiku partway through?"** Three
rounds with Sonnet produced 0/45 faulty candidates — a genuine negative
result. Haiku, a weaker model, produced faults reliably, mirroring the
paper's own use of models of varying strength.

**"What does your mutation testing actually do, mechanically?"** Walks the
Python AST, generates one mutant per mutable site for 5 operator types,
compiles each mutant in-process, and precomputes which mutants each pool
test kills by comparing outputs against the original.

**"Why did you add a subprocess and a timeout partway through?"** A real
generated candidate infinite-loops on a zero input. Threads can't be
killed in Python, so a process (which can) was necessary. Caught this
*before* it could hang the scale-up, by reviewing generated code rather
than only running it.

**"Your timeout fix broke something else — what happened?"** `coverage.py`
needs to run in the same process as the code it measures. Moving execution
into a worker process broke that silently (branch/statement FTR/FDR went to
0.0). Caught by re-verifying the already-audited batch produced identical
numbers before trusting the new code on new data — it didn't, which is how
this was found, fixed, and re-verified again.

**"Is `find_zero` a real bug?"** No. The reference and the candidate are
both correct root-finders that converge to slightly different floats
(`-0.5000000000582077` vs. exactly `-0.5`). Exact equality can't tell that
apart from a real divergence. I found this by printing both values side by
side, not by assuming the classification was right.

**"Is `valid_date` a real bug in the candidates?"** No — it's a bug in
HumanEval's own reference solution (`and`/`or` operator precedence causes
it to wrongly reject December 31st and January 31st). All 5 candidates,
and the independently-generated oracle, agree with each other and
disagree with the buggy reference. This is the paper's own stated
"reference solution defects" threat to validity, encountered directly.

**"How did you select the 20 batch-2 tasks?"** `random.Random(42).sample()`
over the 143 not-yet-attempted HumanEval tasks, with the full eligible
list and resulting selection written to a JSON file *before* any candidate
was generated — so the task list could not have been chosen based on
which ones would produce interesting results.

**"Why is your FDR equal to your FTR for 6 of 8 faults, unlike the paper's
much lower FDR?"** Our test pools (7-15 tests/task, one task at a time,
careful reasoning) are far smaller than the paper's LLM-Plain pools
(thousands per benchmark) — a sample-size and generation-scale difference,
not evidence against the paper's finding.

**"Isn't 8 faults far too small a sample?"** Yes — `report/report.md`
Section 16 says so explicitly. It validates the pipeline and illustrates
qualitative phenomena, not a quantitative claim about HumanEval.

**"What was the single most interesting result?"** Two, for different
reasons: `encrypt` (5/5 independent Haiku candidates make the identical
mistake — a genuine, reproducible model blind spot) and `valid_date` (a
real bug in the *benchmark's own reference solution*, caught only because
we investigated an anomaly instead of trusting the aggregate number).

## Short explanations for each major component (for your own use)

- **`TestOutcome` / `triggered` / `detected`** (`src/metrics.py`): a
  dataclass holding what the faulty program returned, what the reference
  returned, and whether the test's own expected value would flag a
  mismatch — plus `faulty_timed_out`/`reference_timed_out` properties.
- **`normalize_for_comparison`** (`src/metrics.py`): recursively converts
  list/tuple to a canonical tuple form and recurses into dict values,
  applied identically to all three compared values (faulty output,
  reference output, oracle) so no comparison is asymmetric.
- **`_TimedOut`** (`src/metrics.py`): sentinel for a call that didn't
  finish in time; any two instances are equal to each other, never equal
  to a normal value or a `_Raised`.
- **`_Worker`** (`src/metrics.py`): a persistent, spawn-based subprocess
  that executes `(func, args, kwargs)` payloads via `cloudpickle`, reused
  across calls for speed, killed and replaced only when a call times out.
- **`sample_test_suite`** (`src/sampling.py`): shuffles a local copy of
  the test-id pool with a seeded RNG, greedily keeps only tests that
  strictly increase a given score function, stops once the running
  score matches the full pool's score.
- **`_make_coverage_probe`** (`src/coverage_utils.py`): builds a closure
  that starts coverage.py, calls the real function, stops coverage.py, and
  returns the executed line/arc sets — passed through the unchanged
  `call_and_capture`, so it runs inside the timeout-guarded worker process.
- **`generate_mutants`** (`src/mutation_utils.py`): walks the AST once per
  operator type, deep-copies the tree and swaps exactly one node per
  mutant, returns unparsed source strings.
- **`run_fault_experiment`** (`src/fault_runner.py`): ties the above
  together for one fault, all 3 criteria, `n_iterations` times each.
- **`classify_candidates`** (`src/humaneval_pilot.py`): runs every
  candidate against the real HumanEval reference over the generated test
  pool, computes each faulty candidate's difficulty score.
