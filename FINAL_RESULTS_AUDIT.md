# Final Results Validity Audit

**Purpose:** a semantic, spec-level re-inspection of all 8 selected faults in
the combined HumanEval+ experiment, performed *after* data collection was
frozen (per the scale-up protocol) and *before* submission. This is not a
re-run of the experiment — no candidates, tests, or sampled suites were
regenerated. Every number in `results/real_experiment_combined_*` is
preserved exactly as the "inclusive reduced-experiment result" (View A
below). This document adds interpretation on top of that unchanged data.

All numbers below were recomputed directly from the committed artifacts
(`results/real_experiment_per_fault_table.csv`, the per-task
`data/pilot_generation/*_tests.json` pools, and the candidate/canonical
source recorded in `data/pilot_humaneval_tasks.json`), using ad-hoc
verification scripts run in this session (not saved as permanent
repository files, since they are one-off inspection tools, not part of the
pipeline).

---

## 1. Classification of all 8 selected faults

Categories: **A** = genuine semantic candidate fault, **B** = questionable
numerical-equivalence case, **C** = apparent benchmark/reference defect,
**D** = uncertain.

| Task | Category | One-line reason |
|---|---|---|
| `how_many_times` | **A** | Candidate uses `str.count()`, which does not count overlapping matches; spec explicitly says "Count overlapping cases." |
| `concatenate` | **A** | Candidate uses `sum(strings, "")`, which raises `TypeError` on any list of strings — a crash, not a subtle semantic difference. |
| `count_up_to` | **A** | Candidate unconditionally seeds `primes = [2]` before checking whether 2 is `< n`; for `n=2` it wrongly returns `[2]` instead of `[]`, contradicting the spec's own worked example style (`count_up_to` values must be "less than n"). |
| `encrypt` | **D** | See detailed discussion below — the reference itself only rotates lowercase letters and passes uppercase through unchanged; the spec text never states or exemplifies case behavior; all 5 independently-generated candidates chose to rotate both cases. This is a genuine divergence, but whether the *reference* or the *candidates* represent "correct" behavior is not settled by the spec text alone. |
| `move_one_ball` | **A** | Candidate's break-counting logic misclassifies an already-sorted (or single-rotation-away) array as unsortable; e.g. `[1,2,3,4,5]` and `[1,2]` both wrongly return `False`. Verifiable directly against the spec ("if it is possible... then return True"). |
| `starts_one_ends` | **A** | Candidate returns `9` for `n=1` instead of `1` — it computes "all 1-digit numbers" instead of "1-digit numbers starting or ending with 1"; the correct answer for `n=1` is exactly 1 (only the number "1" itself). |
| `find_zero` | **B** | Candidate and reference are two different, independently-converging root-finding algorithms; their outputs differ by ~5.8e-11, which is exact-float-equality noise, not a behavioral difference. Detailed below. |
| `valid_date` | **C** | The real HumanEval reference solution has a demonstrable Python operator-precedence bug that causes it to reject valid end-of-month dates (e.g. `12-31-2020`, `01-31-2020`). Verified against the natural-language spec, not just the reference code. Detailed below. |

**Do not read this table as "6 real bugs, 2 artifacts."** `encrypt` (Category
D) is a genuine behavioral divergence with an outcome that depends on how
one resolves spec silence about uppercase letters — it is included at face
value in every view below (View A and View C both), consistent with the
instruction not to exclude a case just because its classification is
inconvenient or complicated.

### `find_zero` — detailed reasoning

The task pool has 8 tests. Reference (bisection, `1e-10` interval-width
stopping rule) vs. the selected faulty candidate (Newton's method, `1e-10`
step-size stopping rule):

| `xs` | oracle (LLM-generated) | reference | candidate | `|ref-cand|` |
|---|---|---|---|---|
| `[1, 2]` | -0.5 | -0.5000000000582077 | -0.5 | 5.82e-11 |
| `[-6, 11, -6, 1]` | 1.0 | 0.9999999999417923 | 1.0 | 5.82e-11 |
| `[2, 4]` | -0.5 | -0.5000000000582077 | -0.5 | 5.82e-11 |
| `[-4, 2]` | 2.0 | 1.9999999999417923 | 2.0 | 5.82e-11 |
| `[3, -6]` | 0.5 | 0.49999999994179234 | 0.5 | 5.82e-11 |
| `[7, -2]` | 3.5 | 3.4999999999417923 | 3.5 | 5.82e-11 |
| `[-9, 3]` | 3.0 | 2.9999999999417923 | 3.0 | 5.82e-11 |
| `[1, -4]` | 0.25 | 0.24999999994179234 | 0.25 | 5.82e-11 |

All 8 tests "trigger" under exact-equality comparison (Definition 1 read
literally), for all 8 inputs, with an identical residual of `5.82e-11` —
the fingerprint of a fixed-iteration-count tolerance difference between two
converging numerical methods, not a semantically different result. The
candidate's value is, if anything, closer to the true mathematical root in
every case (it matches the oracle's clean value exactly; the reference
carries the residual). **This is not a meaningful violation of the task
specification — it is floating-point/tolerance noise.**

### `valid_date` — detailed reasoning

The task's natural-language spec (from the prompt docstring, not the code)
states rule 2 unambiguously:

> "The number of days is not less than 1 or higher than 31 days for months
> 1,3,5,7,8,10,12."

The real HumanEval/HumanEval+ reference solution is:

```python
if month in [1,3,5,7,8,10,12] and day < 1 or day > 31:
    return False
if month in [4,6,9,11] and day < 1 or day > 30:
    return False
if month == 2 and day < 1 or day > 29:
    return False
```

Because Python's `and` binds tighter than `or`, each line actually parses as
`(month in [...] and day < 1) or (day > 31)` — the `or day > 31` clause is
**unconditional**, not scoped to the month list on its own line. Tracing
`valid_date('12-31-2020')` (December 31 — a legitimately valid date, since
December is a 31-day month) through the reference:

- Line 1 (`month in [1,3,5,7,8,10,12] and day<1 or day>31`): `month=12` is in
  the list, but `day<1` is False, so the `and` is False; `day>31` is also
  False (31 is not > 31). Line does not return.
- Line 2 (`month in [4,6,9,11] and day<1 or day>30`): `month=12` is *not* in
  `[4,6,9,11]`, so the `and` is False regardless of `day<1` — **but
  `day>30` is True** (31 > 30), and that clause is unconditional. The line
  returns `False`.

So the reference wrongly rejects December 31 — not because of anything to
do with December's actual day limit, but because the *next* line's
"greater than 30" check fires unconditionally for any day of 31, regardless
of which month is being validated. A brute-force scan of all `month-day`
combinations for 2020 against the literal spec text (`1 <= day <=
{31,29,31,30,31,30,31,31,30,31,30,31}[month]`, no leap-year handling per
the spec's own unconditional "29 for month 2" wording) finds **18 dates**
where the reference disagrees with the spec: every day-30 in a 30-day month,
and every day-30/31 in a 31-day month (`01-30`, `01-31`, `03-30`, `03-31`,
`04-30`, `05-30`, `05-31`, `06-30`, `07-30`, `07-31`, `08-30`, `08-31`,
`09-30`, `10-30`, `10-31`, `11-30`, `12-30`, `12-31`). Two of these 18
happen to fall inside the generated 15-test pool (`12-31-2020`,
`01-31-2020`).

All 5 independently-generated candidates use a fixed per-month day table
(`{1:31, 2:29, 3:31, 4:30, ...}`) and are **verified to agree with the
literal spec on all 12x31 month/day combinations, with zero mismatches**
(checked programmatically, not by inspection). The independently-generated
oracle also returns `True` for both `12-31-2020` and `01-31-2020` — i.e.
the oracle is spec-correct here too. **This is an apparent defect in the
benchmark's own reference solution, not in any candidate or in the test
oracle.**

---

## 2. Preservation of the automated classification

`find_zero` and `valid_date` remain in `results/real_experiment_combined_*`
exactly as the automated, predeclared, reference-differential procedure
classified them. Nothing above changes any stored file. The findings in
Sections 1 and 4 are recorded here as **construct-validity findings**, on
top of the frozen data, not as retroactive edits to it.

---

## 3. Three result views

### View A — Inclusive predeclared-protocol result (unchanged)

All 8 automatically-selected faults, exactly as reported in
`results/real_experiment_combined_table_iv.csv`:

| Criterion | FTR | FDR |
|---|---|---|
| Mutation | 0.950 | 0.700 |
| Branch | 0.633 | 0.484 |
| Statement | 0.633 | 0.484 |

### View B — Paper-aligned difficulty-filtered subset

**"Paper-aligned difficulty-filtered subset."** Not an exact reproduction —
the fault-generating model, benchmark scope, and test-generation process
still differ from the paper's. Faults with difficulty >= 0.75:
`count_up_to` (0.917), `encrypt` (0.917), `move_one_ball` (0.833),
`starts_one_ends` (0.857), `valid_date` (0.867) — verified directly from
`results/real_experiment_per_fault_table.csv`.

| Criterion | FTR | FDR |
|---|---|---|
| Mutation | 1.000 | 0.800 |
| Branch | 0.528 | 0.490 |
| Statement | 0.528 | 0.490 |

### View C — Semantically validated sensitivity analysis

Excludes only cases Section 1 identified as numerical-equivalence noise or
a benchmark/reference defect: `find_zero` (Category B) and `valid_date`
(Category C). `encrypt` (Category D) is **kept** — its classification is
uncertain, not settled as an artifact, so excluding it would be excluding a
case because its result is inconvenient, which the audit explicitly
prohibits. Remaining 6 faults: `how_many_times`, `concatenate`,
`count_up_to`, `encrypt`, `move_one_ball`, `starts_one_ends`.

| Criterion | FTR | FDR |
|---|---|---|
| Mutation | 0.933 | 0.933 |
| Branch | 0.645 | 0.645 |
| Statement | 0.645 | 0.645 |

This is a sensitivity analysis, not a replacement for View A.

---

## 4. Oracle accuracy reanalysis

The previously reported oracle accuracy (83/93 = 89.2%) treats any
disagreement between a generated test's `expected_output` and the real
HumanEval reference as "oracle incorrect." Recomputing directly against
each fault's full test pool (93 tests across the 8 selected faults'
pools, exact equality — the same comparison the pipeline actually uses):

| Fault | Pool size | Oracle-vs-reference mismatches |
|---|---|---|
| `how_many_times` | 15 | 0 |
| `concatenate` | 12 | 0 |
| `count_up_to` | 12 | 0 |
| `encrypt` | 12 | 0 |
| `move_one_ball` | 12 | 0 |
| `starts_one_ends` | 7 | 0 |
| `find_zero` | 8 | 8 |
| `valid_date` | 15 | 2 |
| **Total** | **93** | **10 (89.2% agreement)** |

Recomputing each of those 10 mismatches against an independent notion of
semantic correctness (not just "does it match the reference"):

- **`find_zero`'s 8 mismatches:** every oracle value matches the true
  mathematical root (to the precision the task's own docstring convention
  implies, `round(x, 2)`); the *reference* is the one carrying a
  `5.82e-11` residual from its own bisection tolerance. **Genuinely-correct
  oracle rate on this fault: 8/8.** The mismatch is 100%
  reference-disagreement, 0% genuine oracle error.
- **`valid_date`'s 2 mismatches:** both (`12-31-2020` → `True`,
  `01-31-2020` → `True`) match the literal natural-language spec; the
  *reference* is the one that is wrong (Section 1). **Genuinely-correct
  oracle rate on this fault: 2/2.** Again, 100% reference-disagreement, 0%
  genuine oracle error.

**Distinguishing the two rates:**

- **Reference-disagreement rate:** 10/93 = 10.8%.
- **Genuinely-incorrect-oracle rate** (where semantic correctness can be
  established independently from the task specification, and the oracle is
  actually found to be wrong): **0/93 = 0%.**

No instance of "the LLM-generated oracle is itself semantically wrong" was
found anywhere in the 93-test combined pool. Every reference-disagreement
in this dataset resolves in the oracle's favor once checked against the
spec/ground truth independently. This should **not** be read as evidence
that oracle quality is a solved, non-issue in general — the sample is 93
tests from a single model on two possibly-unusual tasks — only that in
*this specific dataset*, we found no case where the automated oracle was
actually mistaken.

---

## 5. The trigger/detection gap, after semantic validation

View A shows FTR > FDR overall (mutation 0.950 vs 0.700; branch/statement
0.633 vs 0.484), driven entirely by `find_zero` and `valid_date` (FDR=0.00
on both, against FTR=1.00 mutation and FTR=1.00/0.19 branch-statement
respectively — see the per-fault table). View C, which removes exactly
those two faults and nothing else, shows:

| Criterion | FTR | FDR | Gap |
|---|---|---|---|
| Mutation | 0.933 | 0.933 | **0.000** |
| Branch | 0.645 | 0.645 | **0.000** |
| Statement | 0.645 | 0.645 | **0.000** |

**The gap disappears entirely.** Every one of the 6 remaining faults has
FDR exactly equal to FTR — every test that triggers one of these 6 faults
also correctly detects it. This is a materially different picture from
View A's headline FTR>FDR gap.

**We do not claim this reproduces the paper's oracle finding.** The paper's
FDR<FTR gap is attributed to LLM-generated tests systematically writing
weak or careless assertions on inputs they already exercise correctly
(Finding 2, Section VI) — a property of test-writing quality at scale. Our
gap, before this analysis, was caused entirely by (a) exact-float-equality
noise on a numerically iterative task, and (b) a bug in the benchmark's own
reference solution — neither of which is "a careless assertion." Once those
two are set aside, our reduced dataset shows **no** trigger/detection gap
at all, which is itself informative: it suggests our 8-fault sample simply
does not contain an instance of the paper's specific "weak oracle"
phenomenon, rather than confirming or contradicting how common that
phenomenon is at the paper's scale.

---

## 6. Comparison with the original paper (conservative)

The paper reports, for HumanEval across its five fault-generating models:
moderate FTR (13.7%-45.0%, Table IV), very low FDR (0-3% on essentially
every HumanEval cell), and no criterion consistently dominating (Table IV's
per-criterion differences are small and inconsistent across benchmarks).

**Our reduced experiment does not replicate that numerical trend.** View A,
B, and C all show substantially higher FTR (0.53-1.00 vs. the paper's
0.14-0.45) and, except where the two artifacts drive it down, substantially
higher FDR (0.49-0.93 vs. the paper's 0-3%). We explicitly do **not** claim
this contradicts the paper's finding, since the two results are not
measuring comparable populations. Plausible reasons for the difference,
considered individually rather than as a single unexamined excuse:

- **Scope:** only HumanEval+, not the paper's four benchmarks.
- **Scale:** 40 attempted tasks vs. the paper's full benchmark sweep across
  5 models; 8 final faults vs. 6,066.
- **Model:** one substitute model (Claude Haiku 4.5) standing in for the
  paper's five, so our fault population reflects one model's mistake
  patterns, not a pooled cross-model population.
- **Test pool generation:** our pools (7-15 tests/fault) are far smaller
  than the paper's LLM-Plain pools (thousands per benchmark); a larger pool
  is mechanically more likely to contain a weak-oracle test, which would
  push our FDR down toward the paper's range.
- **Mutation implementation:** the paper does not specify a mutation tool;
  ours is a small custom 5-operator engine, not an established or validated
  third-party tool.
- **Structured oracle representation:** our oracles are `{args,
  expected_output}` equality checks (assumption A2'), not free-form
  assertions — a structurally different (and arguably less error-prone)
  representation than whatever the paper's LLM-Plain tool generates.
- **Three below-threshold faults in the inclusive analysis** (`how_many_times`
  0.6, `concatenate` 0.0, `find_zero` 0.0) would have been excluded entirely
  under the paper's own >=0.75 difficulty filter — View A therefore mixes
  "hard" and "easy" faults in a way the paper's Table IV does not.
- **Potential benchmark/reference defects:** `valid_date` demonstrates that
  at least one real HumanEval reference solution is itself buggy relative
  to its own spec; if the paper's much larger fault corpus contains a
  similar (rare) number of such cases, they would be a small confound in
  its numbers too, though at 6,066 faults their effect on the aggregate
  would be far smaller than the effect of 1 fault out of our 8.
- **Exact floating-point comparison:** `find_zero` shows this is not
  hypothetical — any numerically-iterative task compared under Definition
  1's literal `!=` will show artificially high FTR/FDR-suppression, and
  HumanEval+/MBPP/BigCodeBench plausibly contain other such tasks at scale.
- **Different generation process:** the paper generates 10 candidates per
  task per prompt variant across 5 models; we generate 5 candidates per
  task from one model, one prompt variant, in a single pass.

---

## 7. Aggregation check (by hand)

Confirming the combined View A values are the simple mean of the 8
per-fault, 100-iteration rates in
`results/real_experiment_per_fault_table.csv`:

```
mutation_FTR:  [0.60, 1.00, 1.00, 1.00, 1.00, 1.00, 1.00, 1.00]
               sum = 7.60, n = 8, mean = 0.9500  ✓ matches 0.950

mutation_FDR:  [0.60, 1.00, 1.00, 1.00, 1.00, 1.00, 0.00, 0.00]
               sum = 5.60, n = 8, mean = 0.7000  ✓ matches 0.700

branch_FTR:    [0.42, 1.00, 0.13, 1.00, 0.32, 1.00, 1.00, 0.19]
               sum = 5.06, n = 8, mean = 0.6325  ✓ matches 0.633 (rounded)

branch_FDR:    [0.42, 1.00, 0.13, 1.00, 0.32, 1.00, 0.00, 0.00]
               sum = 3.87, n = 8, mean = 0.4838  ✓ matches 0.484 (rounded)

statement_FTR: identical values to branch_FTR in this dataset
               mean = 0.6325  ✓ matches 0.633 (rounded)

statement_FDR: identical values to branch_FDR in this dataset
               mean = 0.4838  ✓ matches 0.484 (rounded)
```

Verified programmatically (pandas `.mean()` over the CSV columns) as well
as by manual summation above; both agree with the published table to 3
decimal places. Statement and branch values coincide for every fault in
this dataset because none of these 8 small functions has a statement whose
execution is decoupled from a branch outcome at the granularity these
tests probe — this is a property of the fault sample, not a bug in the two
separate measurement code paths (which use different `coverage.py` APIs,
`Analysis.executed` vs. `Analysis.arcs_executed_set`/`arc_possibilities`).

---

## 8. Final verdict

- **View A (inclusive) is unchanged and remains the primary reported
  result** — this document adds interpretation, not a correction.
- **2 of 8 faults are not genuine candidate semantic defects**: `find_zero`
  (numerical-equivalence artifact) and `valid_date` (benchmark reference
  defect, confirmed against the natural-language spec, not just the
  reference code).
- **1 of 8 faults (`encrypt`) is genuinely uncertain** — a real behavioral
  divergence on a case the spec never disambiguates, kept in every view
  at face value.
- **The FTR>FDR gap in View A is fully explained by the 2 excluded cases**;
  View C shows FTR=FDR exactly across all three criteria once they are set
  aside.
- **No genuinely-incorrect oracle was found anywhere in the 93-test
  combined pool** — every reference-disagreement resolved in the oracle's
  favor once checked independently against ground truth.
- **This experiment's numbers do not replicate the paper's Table IV
  trend** (much higher FTR and, outside the two artifacts, much higher
  FDR), for reasons of scale, scope, model, and tooling laid out in Section
  6 — not because either result is wrong.
