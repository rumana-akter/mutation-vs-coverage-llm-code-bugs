# Reproducing Table IV — Test Adequacy for LLM-Generated Code

**Assignment:** Reproduce Table IV of arXiv:2609.09315 (Hamidi, Konstantinou,
Degiovanni, Papadakis), for Professor Benoit Baudry.

This report summarizes a **focused methodological reproduction**, not a
numeric one. The paper's own faulty implementations, test pools, and five
fault-generating models are not publicly available (a systematic search is
documented in `PLAN.md`), so the real-benchmark portion of this work uses
substitute artifacts generated during this project. Every number reported
here was produced by running the code in this repository; exact
reproduction commands are in `README.md`. Detailed
development history, incident-by-incident debugging notes, and the full
semantic audit behind the results below live in `EXPERIMENT_LOG.md`,
`AUDIT.md`, and `FINAL_RESULTS_AUDIT.md` — supplementary material, not
required to follow this report.

## 1. Objective

Reproduce Table IV specifically: for each (benchmark, fault-generating
model) pair, the mean Fault Trigger Rate (FTR) and Fault Detection Rate
(FDR) achieved by test suites selected to be adequate under statement
coverage, branch coverage, and mutation testing, averaged over 100
randomized selection runs per fault (paper Section V, Definitions 1-5).

## 2. Experimental Setup

The paper uses four benchmarks, five fault-generating LLMs, and 6,066
faults in total. None of its artifacts are public. This reproduction
instead:

- Uses **HumanEval only** (public, self-contained reference solutions).
- Uses **Claude** (Sonnet, then Haiku 4.5) as a single substitute
  fault-generating model, generating candidate implementations blind to
  the reference, plus a separately generated test pool per candidate.
- Attempts **40 HumanEval tasks** across two batches (20 + 20, the second
  selected via a pre-registered fixed-seed random sample of the remaining
  tasks), generating **200 candidate implementations** total.
- Classifies candidates as faulty by differential testing against the real
  HumanEval reference, keeps the hardest fault per task (paper's
  difficulty ≥ 0.75 preferred, per Definition 5), and generates a test
  pool for each.
- Measures statement and branch coverage via `coverage.py`, and mutation
  testing via a small custom `ast`-based engine (ROR/AOR/BOR/constant/RVR
  operators) — the paper does not specify a mutation tool.
- Runs the paper's randomized criterion-guided sampling procedure
  (Section V) for real: 100 iterations per fault per criterion.

## 3. Method

The repository separates the *definitions* (`src/metrics.py`), *sampling
algorithm* (`src/sampling.py`), *coverage measurement*
(`src/coverage_utils.py`), *mutation engine* (`src/mutation_utils.py`),
and *orchestration* (`src/fault_runner.py`) into independent, unit-tested
modules, used identically by a synthetic validation experiment and the
real HumanEval pilot.

A test's oracle is represented as `{args, expected_output}` equality
(assumption A2', `PLAN.md`), rather than free-form assertion code. A test
*triggers* a fault if the candidate's output differs from the reference's
(Definition 1); it *detects* the fault only if it also triggers and its
recorded `expected_output` correctly flags the difference (Definition 3).
Exceptions are captured as a comparable sentinel rather than propagated.
Non-terminating candidates are handled by executing every candidate/
reference call in a killable worker process with a 5-second timeout,
returning a distinct `TimedOut` sentinel (added after a generated
subtraction-based GCD implementation was found to loop forever on a zero
input; full incident in `EXPERIMENT_LOG.md`).

Per Definition 7's denominator (killed + surviving mutants, excluding
equivalent ones), no automatic equivalent-mutant detection is attempted.
Both the full-pool target and every sampled suite are scored against the
same generated mutant set, so equivalent mutants do not affect which
sampled subset matches the full-pool score — but the reported mutation
score should still be read as an operational score over the generated
mutants, not an equivalent-mutant-corrected one.

The synthetic experiment (`scripts/run_synthetic_experiment.py`) validates
this machinery on a hand-crafted boundary bug before it is trusted on real
code: mutation-adequate suites reach FTR 1.00 vs. statement/branch's 0.49,
because killing the relevant relational-operator mutant forces a test at
exactly the boundary.

## 4. Results

### 4.1 Inclusive result (all 8 automatically selected cases)

`results/real_experiment_combined_table_iv.csv`, aggregated from 2,400
sampled-suite evaluations (100 iterations × 3 criteria × 8 cases):

| Criterion | FTR | FDR |
|---|---|---|
| Mutation | 0.950 | 0.700 |
| Branch | 0.633 | 0.484 |
| Statement | 0.633 | 0.484 |

Per-fault detail: `results/real_experiment_per_fault_table.csv`.

### 4.2 Semantic-validity sensitivity analysis

A post-hoc audit (`FINAL_RESULTS_AUDIT.md`) inspected all 8 selected cases
against their original task specification, not just the reference
implementation. It classified 5 as clear genuine candidate faults
(`how_many_times`, `concatenate`, `count_up_to`, `move_one_ball`,
`starts_one_ends`), and 3 as more complicated:

- **`find_zero`**: candidate and reference are independent root-finding
  algorithms converging to the same root within a ~5.8e-11 tolerance —
  within the task's own docstring rounding convention. Classified as a
  **numerical-equivalence artifact**, not a fault.
- **`valid_date`**: the real HumanEval reference solution has a verifiable
  Python operator-precedence bug that rejects valid end-of-month dates
  (e.g. December 31); all 5 independently generated candidates and the
  generated oracle agree with the specification, not the reference.
  Classified as a **benchmark/reference defect**.
- **`encrypt`**: all 5 candidates rotate uppercase letters, while the
  reference silently only rotates lowercase; the specification never
  states or exemplifies case handling. Classified as **uncertain**
  (kept in every result at face value).

Excluding only the artifact and the reference defect:

| Criterion | FTR | FDR |
|---|---|---|
| Mutation | 0.933 | 0.933 |
| Branch | 0.645 | 0.645 |
| Statement | 0.645 | 0.645 |

FTR equals FDR exactly on all three criteria once these two cases are
removed — the trigger/detection gap in the inclusive result is fully
attributable to them.

### 4.3 Comparison with the original paper

The paper reports, across its five HumanEval fault models, moderate FTR
(14-45%) and very low FDR (0-3%), with no criterion consistently
dominating. This reproduction's numbers are substantially higher on both
FTR and FDR, and the sensitivity result shows no FTR/FDR gap at all in the
6 unambiguous cases. **This does not confirm or contradict the paper's
finding** — the two experiments differ in scale (8 cases vs. 6,066 faults),
fault-generating model (one Claude model vs. five commercial/OSS models),
test-pool size (7-15 tests/task vs. thousands/benchmark), and mutation
tooling (custom vs. unspecified). The paper's own low-FDR finding is
attributed to LLM-generated tests writing weak assertions at scale; this
sample, being small and manually inspectable, happened not to contain an
instance of that specific phenomenon once its two ground-truth-affected
cases were set aside.

## 5. Key Observations

- Mutation-guided suites achieve FTR 1.00 on 7 of 8 cases, noticeably
  higher than branch/statement on cases where the faulty behavior is not
  forced by coverage alone (e.g. `count_up_to`: mutation 1.00 vs. branch/
  statement 0.13).
- The FDR<FTR gap, where it appears, traces to two specific, individually
  verified cases rather than a general "weak oracle" pattern — the
  opposite of what a naive reading of the inclusive result alone would
  suggest.
- A benchmark's own reference solution is not guaranteed correct; treating
  it as ground truth (as Definition 1 does) can misclassify a case, as it
  does for `valid_date`.
- Exact-equality comparison is unsuited to numerically iterative tasks
  (`find_zero`): two correct algorithms can legitimately disagree at the
  15th decimal place.
- A weaker model (Haiku) produced usable faults where a stronger one
  (Sonnet, 0/45 candidates faulty) did not, supporting the paper's
  decision to pool multiple models of varying strength.

## 6. Threats to Validity / Limitations

- **Sample size.** 8 selected cases from 40 attempted tasks is too small
  for any quantitative claim about HumanEval; it validates the pipeline
  and illustrates qualitative phenomena only.
- **Single fault-generating model family.** Claude Sonnet/Haiku, not the
  paper's five-model, five-vendor pool.
- **Custom mutation tool.** A small 5-operator `ast`-based engine, not an
  established third-party library (the paper does not specify one).
- **Simplified oracle representation.** Structured equality checks rather
  than free-form assertions.
- **Reference-solution correctness assumed.** Found not to always hold
  (`valid_date`); Definition 1 has no mechanism to distinguish a wrong
  candidate from a wrong reference.
- **Scope.** HumanEval only; MBPP, BigCodeBench, NaturalCodeBench are out
  of scope. No statistical significance testing is reported (uninformative
  at n=8).

## 7. Conclusion

This project reproduces the experimental methodology behind Table IV — the
FTR/FDR definitions, the randomized criterion-guided sampling procedure,
real coverage, and real mutation testing — on a reduced, independently
generated 40-task HumanEval dataset. It does not recover the paper's
numbers, and does not claim to: the artifacts required (6,066 faults, five
models' generations, large test pools) are unavailable. The inclusive
8-case result and the semantic-validity sensitivity analysis are reported
side by side rather than selecting whichever is more favorable, since two
of the eight automatically selected cases turned out, on inspection, to
reflect measurement artifacts or a benchmark defect rather than genuine
candidate faults.
