# AUDIT.md — Methodological Audit of the Real HumanEval+ Result

**Scope:** independent re-verification of the aggregated result
`HumanEval+ / claude-haiku-4-5` (mutation FTR/FDR = 0.920/0.920, branch
FTR/FDR = 0.574/0.574, statement FTR/FDR = 0.574/0.574), triggered by the
observation that FTR exactly equals FDR for every criterion — suspicious
given the paper's central finding that triggering and detection usually
diverge sharply.

**Method:** every check below was performed by writing throwaway diagnostic
scripts that re-import the actual `src/` modules and re-run the actual
computation from the actual saved `data/pilot_generation/*` artifacts — not
by re-reading `results/*.csv` and trusting it. No code or results files were
modified during this audit.

---

## 1. Code path for `triggered`

**File:** `src/metrics.py`, class `TestOutcome`, property `triggered` (line 95-98):

```python
@property
def triggered(self) -> bool:
    """Definition 1: triggered(f, t) <=> output(f,t) != output(p,t)."""
    return self.faulty_output != self.reference_output
```

**File:** `src/fault_runner.py`, function `build_outcomes` (line 79-97), which
constructs the `faulty_output`/`reference_output` inputs:

```python
for t in fault.tests:
    faulty_output = call_and_capture(faulty_func, t.args, t.kwargs or {})
    reference_output = call_and_capture(fault.reference_func, t.args, t.kwargs or {})
    ...
```

**Confirmed:** `triggered` is computed purely from `faulty_output != reference_output`
— two values obtained by *actually calling* the faulty candidate and the
real HumanEval reference implementation with the same input. `t.expected_output`
(the generated oracle) never appears in this computation. **Clean — no
oracle involvement in triggering, as required by Definition 1.**

## 2. Code path for `detected`

**File:** `src/metrics.py`, property `detected` (line 100-103):

```python
@property
def detected(self) -> bool:
    """Definition 3: detected(f, t) <=> triggered(f,t) AND oracle flags it."""
    return self.triggered and self.oracle_flags_error
```

**File:** `src/fault_runner.py`, `build_outcomes` (line 88-90):

```python
# The test's own oracle "flags an error" when the faulty output
# does not match what the oracle believes is correct.
oracle_flags_error = faulty_output != t.expected_output
```

**Confirmed:** `oracle_flags_error` compares `faulty_output` (real call
result) against `t.expected_output` — the value from the *generated test's*
own `OracleTestCase.expected_output` field. `reference_output` is **not**
used anywhere in this line. Structurally, detection uses the LLM-generated
oracle, not the reference, exactly as required.

**However** — see Section 6 below. This comparison has a real, confirmed
type-normalization bug for one data type (native Python `list`).

## 3. Oracle leakage check

Traced `t.expected_output`'s provenance end to end:

- `src/humaneval_pilot.py`, `parse_test_pool()` (line 44-63): reads
  `entry["expected_output"]` directly from the parsed JSON test file
  (`data/pilot_generation/<entry_point>_tests.json`) and applies only
  `normalize_for_comparison` (a pure list→tuple structural conversion, no
  external data). **No reference lookup anywhere in this function.**
- `scripts/run_experiment.py` (line 186-187): loads `tests` once via
  `parse_test_pool(tests_text, ...)` and reuses the *same* `tests` list
  unmodified both for `classify_candidates(...)` (fault selection) and the
  final `FaultSpec` passed into `run_fault_experiment(...)`. No
  intermediate step touches `expected_output`.
- Grepped the entire `src/` and `scripts/` tree for any place that writes
  to `.expected_output` after parsing — there is none. It is set once, at
  parse time, from the raw JSON, and never reassigned.

**Confirmed: no oracle leakage.** Generated `expected_output` values come
only from the independent, blind test-generation subagent's JSON output
(`data/pilot_generation/*_tests.json`, saved verbatim before this audit and
before any classification ran), and are never corrected, overwritten, or
derived from `canonical_solution` at any point.

## 4. Full diagnostic table — all 5 faults, entire test pools

Computed directly (not from the CSV) via `src/fault_runner.build_outcomes`
on every test in every fault's full pool (not just the ones a sampled
suite happened to select). Full raw dump is reproducible with the script
in Section 6; abbreviated below (full pools have 12-15 rows each — every
row was inspected, only the informative ones are shown here for space):

### HumanEval/18 `how_many_times`, candidate 0 (`return string.count(substring)`)

| test_id | input | reference | faulty | oracle | triggered | detected |
|---|---|---|---|---|---|---|
| how_many_times_2 | `('aaaa','aa')` | 3 | 2 | 3 | **True** | **True** |
| how_many_times_6 | `('aaaaa','aa')` | 4 | 2 | 4 | **True** | **True** |
| how_many_times_7 | `('aaaaa','aaa')` | 3 | 1 | 3 | **True** | **True** |
| how_many_times_8 | `('ababab','aba')` | 2 | 1 | 2 | **True** | **True** |
| how_many_times_11 | `('banana','ana')` | 2 | 1 | 2 | **True** | **True** |
| how_many_times_13 | `('xxxxx','xx')` | 4 | 2 | 4 | **True** | **True** |
| (9 other tests, non-overlapping cases) | — | equal | equal | equal | False | False |

6/15 triggered, all 6 detected. Oracle correctness: 15/15 (every generated
`expected_output` equals the real reference output).

### HumanEval/28 `concatenate`, candidate 4 (`return sum(strings, "")`)

| test_id | input | reference | faulty | oracle | triggered | detected |
|---|---|---|---|---|---|---|
| concatenate_1 | `(['a'],)` | `'a'` | `Raised(TypeError)` | `'a'` | **True** | **True** |
| ... (all 12 tests) | | | `Raised(TypeError)` on every input | matches reference | **True** (12/12) | **True** (12/12) |

Every call raises `TypeError` (`sum()` refuses a string start value), so
every test triggers, and every generated oracle (a correct string, matching
the real reference) necessarily disagrees with the exception sentinel — 12/12
correct oracle, 12/12 detected.

### HumanEval/96 `count_up_to`, candidate 4 (unconditionally includes 2 in the prime list)

| test_id | input | reference | faulty | oracle (as parsed) | triggered | detected (as computed) |
|---|---|---|---|---|---|---|
| count_up_to_2 | `(2,)` | `[]` | `[2]` | `()` | **True** | **True** |
| count_up_to_0 | `(0,)` | `[]` | `[]` | `()` | False | False |
| count_up_to_3 | `(3,)` | `[2]` | `[2]` | `(2,)` | False | False |
| ... (9 more, all non-triggering) | | | | | False | False |

**This is the fault where the type bug lives — see Section 6, this row set
is re-examined there in full.**

### HumanEval/89 `encrypt`, candidate 0 (over-shifts uppercase letters)

| test_id | input | reference | faulty | oracle | triggered | detected |
|---|---|---|---|---|---|---|
| encrypt_9 | `('Hi',)` | `'Hm'` | `'Lm'` | `'Hm'` | **True** | **True** |
| (11 other tests, all lowercase-only inputs) | | equal | equal | equal | False | False |

Only 1/12 tests (the sole test containing an uppercase letter) triggers.
Oracle correctness: 12/12 (see Section 9 for the full canonical-solution
verification of why `'Hm'` — not `'Lm'` — is genuinely correct).

### HumanEval/109 `move_one_ball`, candidate 2 (mishandles `break_count==1`)

| test_id | input | reference | faulty | oracle | triggered | detected |
|---|---|---|---|---|---|---|
| move_one_ball_2 | `([1,2,3,4,5],)` | `True` | `False` | `True` | **True** | **True** |
| move_one_ball_5 | `([1,2],)` | `True` | `False` | `True` | **True** | **True** |
| (10 other tests) | | equal | equal | equal | False | False |

2/12 triggered, both detected. Oracle correctness: 12/12.

## 5. Search for `triggered=True, detected=False` across all 5 full pools

**Result: zero such tests exist across all 63 tests in the 5 pools combined**
(15 + 12 + 12 + 12 + 12).

Why, broken down per fault:

- `how_many_times` (6 triggering tests), `concatenate` (12), `encrypt` (1),
  `move_one_ball` (2): **genuinely correct oracle content** on every
  triggering test (and every non-triggering test too) — verified by direct
  comparison of `expected_output` against the real `reference_output` for
  every one of these 31 triggering+non-triggering tests. These 4 faults are
  small, clean functions returning `int`, `str` (or raising), `str`, and
  `bool` respectively — data types with no type-representation ambiguity
  between JSON and Python, so the generated oracle's correctness is a real,
  unconfounded finding: a capable model, given only 10-15 cases to reason
  about at once, produced correct expected values for these specific tasks.
- `count_up_to` (1 triggering test out of 12): the apparent "0
  triggered-not-detected" here is **not fully trustworthy as stated** — see
  Section 6. The oracle *comparison mechanism* is broken for this fault
  (list-vs-tuple type mismatch), and only coincidentally produces the same
  boolean answer as a correct comparison would.

## 6. Oracle correctness, independently computed, BEFORE sampling — and a confirmed bug

Computed `oracle_correct = (generated_oracle == reference_output)` for
every test in every one of the 5 pools, comparing types carefully:

| Fault | Tests | Correct oracles (naive `==`) | Correct oracles (type-normalized) |
|---|---|---|---|
| how_many_times | 15 | 15 | 15 |
| concatenate | 12 | 12 | 12 |
| **count_up_to** | 12 | **0** | **12** |
| encrypt | 12 | 12 | 12 |
| move_one_ball | 12 | 12 | 12 |
| **Total** | **63** | **51 (81.0%)** | **63 (100%)** |

The `count_up_to` row is the finding. Investigated directly:

```
type(faulty_output)   = list   (count_up_to returns a native Python list)
type(reference_output) = list
type(expected_output)  = tuple  (JSON has no tuple type; src/humaneval_pilot.py's
                                  normalize_for_comparison() converts every
                                  JSON list to a tuple when parsing the test file)
```

**Root cause, precisely:** `src/humaneval_pilot.parse_test_pool()` calls
`normalize_for_comparison(entry["expected_output"])` **once, at parse time**,
converting the oracle's JSON array into a Python `tuple`. But
`src/fault_runner.build_outcomes()` never applies the same normalization to
`faulty_output`/`reference_output` — those are left as whatever native type
the function under test actually returns. For any function that returns a
native `list` (as `count_up_to` does), the comparison
`oracle_flags_error = faulty_output != t.expected_output` becomes
`some_list != some_tuple`, which is **`True` in Python unconditionally,
regardless of the list's and tuple's contents** (a `list` is never `==` to a
`tuple`, even holding identical elements in identical order). This makes
`oracle_flags_error` **vacuously `True` for every single test on this fault**
— the oracle comparison is not actually checking content at all for
`count_up_to`; it always claims to "flag an error," whether the generated
oracle's belief was right or wrong, and whether the faulty program's output
was right or wrong.

**Does this change the reported numbers for `count_up_to`?** I re-computed
`detected` for all 12 tests with a *type-corrected* comparison
(`normalize_for_comparison(faulty_output) != normalize_for_comparison(t.expected_output)`)
and compared it, test by test, against the as-shipped (buggy) value:

```
count_up_to_0   triggered=False  actual_oracle_flags_error=True   corrected=False  actual_detected=False  corrected_detected=False
count_up_to_1   triggered=False  actual_oracle_flags_error=True   corrected=False  actual_detected=False  corrected_detected=False
count_up_to_2   triggered=True   actual_oracle_flags_error=True   corrected=True   actual_detected=True   corrected_detected=True
count_up_to_3..11  (all non-triggering, same pattern as _0/_1)
Number of tests where corrected detected != actual detected: 0
```

**Zero of the 12 tests' `detected` values change.** This is because (a)
`detected` requires `triggered` first, which correctly gates out the
vacuously-`True` oracle flag for the 11 non-triggering tests regardless of
the bug, and (b) on the *one* triggering test (`n=2`), the generated
oracle's actual content (`empty list`) is independently correct (matches
the real reference), so `oracle_flags_error` is `True` under both the buggy
and the corrected computation — for the same wrong reason and the right
reason, respectively, happening to agree.

**This is still a real, confirmed bug.** It means: for `count_up_to`
specifically, our pipeline is not actually validating "the generated oracle
correctly rejected the faulty output" — it is asserting that unconditionally,
irrespective of the oracle's content, and got the right answer by
coincidence (the oracle was independently correct anyway). Had the
LLM-generated oracle for `count_up_to_2` instead been *wrong* (e.g., if it
had guessed `[2]`, matching the faulty output rather than the true `[]`),
the as-shipped code would **still** report `detected=True` — a false
positive — because the comparison never actually inspects list contents at
all for this data type. The bug is latent in every list-returning function
in this codebase (`sort_array`, `remove_duplicates`, `sort_third`,
`triples_sum_to_zero` all return lists too, though none of them had a fault
selected in this run, so the bug never had a chance to bite there).

**Grand total oracle correctness, once the type bug is corrected for:
63/63 = 100%.** This is a genuinely small, favorable sample (see Section 11
verdict) — not fabricated, but not to be over-interpreted either.

## 7. Aggregation verification (independent of the CSV)

Recomputed directly from `results/real_experiment_raw_results.csv`, but
cross-checked arithmetic by hand rather than trusting `build_table_iv.py`:

| fault_id | criterion | n_triggered/100 | n_detected/100 | FTR | FDR |
|---|---|---|---|---|---|
| HumanEval_18_candidate_0 | statement | 42 | 42 | 0.42 | 0.42 |
| HumanEval_18_candidate_0 | branch | 42 | 42 | 0.42 | 0.42 |
| HumanEval_18_candidate_0 | mutation | 60 | 60 | 0.60 | 0.60 |
| HumanEval_28_candidate_4 | statement | 100 | 100 | 1.00 | 1.00 |
| HumanEval_28_candidate_4 | branch | 100 | 100 | 1.00 | 1.00 |
| HumanEval_28_candidate_4 | mutation | 100 | 100 | 1.00 | 1.00 |
| HumanEval_96_candidate_4 | statement | 13 | 13 | 0.13 | 0.13 |
| HumanEval_96_candidate_4 | branch | 13 | 13 | 0.13 | 0.13 |
| HumanEval_96_candidate_4 | mutation | 100 | 100 | 1.00 | 1.00 |
| HumanEval_89_candidate_0 | statement | 100 | 100 | 1.00 | 1.00 |
| HumanEval_89_candidate_0 | branch | 100 | 100 | 1.00 | 1.00 |
| HumanEval_89_candidate_0 | mutation | 100 | 100 | 1.00 | 1.00 |
| HumanEval_109_candidate_2 | statement | 32 | 32 | 0.32 | 0.32 |
| HumanEval_109_candidate_2 | branch | 32 | 32 | 0.32 | 0.32 |
| HumanEval_109_candidate_2 | mutation | 100 | 100 | 1.00 | 1.00 |

Manual re-derivation of the final table (mean of the 5 per-fault rates,
per criterion):

```
mutation:  FTR = [1.00, 0.60, 1.00, 1.00, 1.00] -> mean = 0.9200  (matches reported 0.920)
           FDR = [1.00, 0.60, 1.00, 1.00, 1.00] -> mean = 0.9200  (matches reported 0.920)
branch:    FTR = [0.42, 0.32, 0.13, 1.00, 1.00] -> mean = 0.5740  (matches reported 0.574)
           FDR = [0.42, 0.32, 0.13, 1.00, 1.00] -> mean = 0.5740  (matches reported 0.574)
statement: FTR = same set as branch -> mean = 0.5740 (matches reported 0.574)
           FDR = same set as branch -> mean = 0.5740 (matches reported 0.574)
```

**Aggregation is arithmetically correct** — it is exactly the mean of the
5 per-fault rates, matching `scripts/build_table_iv.py`'s documented
two-level averaging (per-fault mean over 100 iterations, then mean across
faults). `FTR == FDR` in every one of these 15 (fault, criterion) rows is
not an aggregation artifact — it genuinely reflects that `detected == triggered`
for every single one of the 1,500 raw rows, which traces back to oracle
correctness (Sections 5-6) at the per-test level, not to anything in the
aggregation code.

## 8. Verification of five distinct faults

From `results/real_experiment_fault_selection.json` (`outcome: "fault_selected"` entries):

| task_id | entry_point | selected candidate index | difficulty |
|---|---|---|---|
| HumanEval/18 | how_many_times | 0 | 0.600 |
| HumanEval/28 | concatenate | 4 | 0.000 |
| HumanEval/96 | count_up_to | 4 | 0.917 |
| HumanEval/89 | encrypt | 0 | 0.917 |
| HumanEval/109 | move_one_ball | 2 | 0.833 |

**Confirmed: five distinct HumanEval task IDs** (18, 28, 96, 89, 109), one
selected candidate each. `scripts/run_experiment.py`'s per-task loop
(`for entry in TASK_MANIFEST`) processes each task independently and
selects at most one fault per task via `max(faulty_reports, key=...)`
before ever calling `run_fault_experiment` — there is no code path that
could produce multiple faults from the same task in the final raw CSV.
Grepped `results/real_experiment_raw_results.csv`'s `fault_id` column
directly: exactly 5 unique values, one per task above. The "5/5 candidates
made the same encrypt mistake" observation (Section 9) describes *why*
`encrypt`'s single selected fault has difficulty 0.917 (all 5 raw candidates
were faulty, so whichever was picked would show the same bug) — it does not
mean 5 faults were counted for that one task; only candidate 0 was ever
promoted to a `FaultSpec` and run through `run_fault_experiment`.

## 9. `encrypt` audit

**Original HumanEval/89 prompt actually given to the candidate-generation subagent:**

```python
def encrypt(s):
    """Create a function encrypt that takes a string as an argument and
    returns a string encrypted with the alphabet being rotated. 
    The alphabet should be rotated in a manner such that the letters 
    shift down by two multiplied to two places.
    For example:
    encrypt('hi') returns 'lm'
    encrypt('asdfghjkl') returns 'ewhjklnop'
    encrypt('gf') returns 'kj'
    encrypt('et') returns 'ix'
    """
```

(Confirmed via `data/pilot_humaneval_tasks.json["HumanEval/89"]["prompt"]`
— this is the **original, unmodified** prompt; `EXPERIMENT_LOG.md` Entry 10
used original, not under-specified, prompts for this batch of 15 tasks, and
this file confirms that directly — no under-specification was applied here.)

**Real canonical solution (never shown to any subagent):**

```python
d = 'abcdefghijklmnopqrstuvwxyz'
out = ''
for c in s:
    if c in d:
        out += d[(d.index(c)+2*2) % 26]
    else:
        out += c
return out
```

**Each of the 5 generated implementations** (`data/pilot_generation/encrypt_candidates_v3_haiku.txt`)
adds an extra `elif 'A' <= c <= 'Z': ...shift...` branch (or an equivalent
uppercase-aware character map) that the canonical solution does not have —
the canonical solution's `if c in d` check only ever matches lowercase
letters (since `d` is the lowercase alphabet), so **any non-lowercase
character, uppercase or otherwise, falls through to `else: out += c`
(left unchanged)** in the real reference.

**Exact divergence:** on input `'Hi'`, the real reference returns `'Hm'`
(H untouched, i shifted 4 positions to m); all 5 candidates return `'Lm'`
(both H and i shifted).

**Was uppercase actually required by the original specification?** No.
None of the prompt's 4 worked examples contain an uppercase letter, and the
canonical solution's `d = 'abcdefghijklmnopqrstuvwxyz'` / `if c in d` idiom
is an explicit (if implicit-looking) design choice to leave anything outside
the lowercase alphabet untouched. This is a genuine specification-consistent
ground truth, not an artifact of an ambiguous or under-specified prompt —
**the fault classification here is correct**: 5/5 candidates generalized
beyond what both the spec's examples and the reference implementation
actually do.

## 10. Mutation testing audit

Computed via `src/mutation_utils.generate_mutants`/`build_mutation_model`
directly on each fault's actual source (not read from any cached report):

| Fault | Mutants generated | Compiled OK | Full-pool score | Operators present |
|---|---|---|---|---|
| how_many_times (candidate 0) | 3 | 3 | 1.000 (3/3 killed) | RVR: 3 |
| concatenate (candidate 4) | 3 | 3 | 1.000 (3/3 killed) | RVR: 3 |
| count_up_to (candidate 4) | 20 | 20 | 0.900 (18/20 killed) | ROR: 3, AOR: 1, CONST: 10, RVR: 6 |
| encrypt (candidate 0) | 21 | 21 | 0.857 (18/21 killed) | ROR: 4, AOR: 6, CONST: 8, RVR: 3 |
| move_one_ball (candidate 2) | 29 | 29 | 1.000 (29/29 killed) | ROR: 4, AOR: 2, CONST: 14, RVR: 9 |

No mutants failed to compile for any of the 5 faults (0 "surviving/uncompilable"
across the board); we do not attempt automatic equivalent-mutant detection
(documented design choice, `src/mutation_utils.py` docstring), so the 2
surviving `count_up_to` mutants and 3 surviving `encrypt` mutants are simply
uncounted as "killed" — `sample_test_suite`'s target is always the *achievable*
full-pool score, so this does not affect FTR/FDR (Section 7 already confirmed
the mutation-criterion numbers independently).

**RVR generality check:** `generate_mutants()` (in `src/mutation_utils.py`)
walks *every* `ast.Return` node with a non-`None` value in the given source,
unconditionally, for any function passed to it. It appears in all 5 faults'
mutant sets above (3, 3, 6, 3, 9 RVR mutants respectively — scaling with
each function's number of `return` statements) with no fault-specific
branching or special-casing anywhere in the operator's code. **Confirmed
generic, not tuned to these 5 faults** — it was added once (Entry 9, for
the `how_many_times` one-liner) and applies identically to every subsequent
fault, including the 4 found afterward.

Concrete illustration of *why* mutation beats branch/statement on
`count_up_to` (re-ran `sample_test_suite` with the fault's actual seeds):

```
--- criterion=branch ---
  seed=25000: selected=['count_up_to_6', 'count_up_to_10', 'count_up_to_0']       triggered=False
  seed=25001: selected=['count_up_to_8', 'count_up_to_0']                        triggered=False
  seed=25002: selected=['count_up_to_7', 'count_up_to_1']                        triggered=False

--- criterion=mutation ---
  seed=25000: selected=['count_up_to_6', 'count_up_to_10', 'count_up_to_0', 'count_up_to_1', 'count_up_to_2']  triggered=True
  seed=25001: selected=['count_up_to_8', 'count_up_to_0', 'count_up_to_1', 'count_up_to_2']                    triggered=True
  seed=25002: selected=['count_up_to_7', 'count_up_to_2', 'count_up_to_1']                                     triggered=True
```

Branch-adequate suites reach full branch coverage without ever needing
`count_up_to_2` (`n=2`); mutation-adequate suites are forced to include it
(likely to kill a `CONST`/`ROR` mutant near the small-`n` boundary), which
is exactly the `n=2` input that reveals the bug.

## 11. Verdict

**B. RESULT HAS A BUG.**

**What the bug is:** `src/humaneval_pilot.normalize_for_comparison()` is
applied to the generated test oracle's `expected_output` at parse time
(converting JSON arrays to Python tuples), but `src/fault_runner.build_outcomes()`
never applies the equivalent normalization to the *actual* `faulty_output`/
`reference_output` values obtained by calling the real functions. For any
function under test that natively returns a Python `list` (as opposed to a
`tuple`, `int`, `str`, or `bool`), the oracle-comparison line
`oracle_flags_error = faulty_output != t.expected_output` degenerates to
`list != tuple`, which is unconditionally `True` in Python regardless of
element-wise content. This makes the oracle check vacuous — always
"flagging an error" — for every test on every list-returning function,
irrespective of whether the LLM-generated oracle was actually right or
wrong.

**Does it affect the specific numbers currently reported?** No — verified
directly, test by test: for the one affected fault in this run
(`count_up_to`), recomputing `detected` with a type-corrected comparison
changes **zero** of its 12 per-test outcomes, because (a) the bug is
irrelevant for the 11 non-triggering tests (`detected` requires `triggered`
first, computed correctly and independently), and (b) on the 1 triggering
test, the generated oracle's content happens to be independently correct
anyway. The reported per-fault FTR/FDR values, the full aggregation
(Section 7), and the five-distinct-faults check (Section 8) are all
independently verified correct.

**Why this is still a bug, not just a footnote:** the equality `FTR == FDR`
for `count_up_to` is not, as currently computed, evidence that "the
generated oracle correctly caught the fault" — the code would have printed
the identical `detected=True` even if the oracle's stated belief for `n=2`
had been wrong (e.g., had it guessed `[2]` instead of `[]`), because the
comparison never actually inspects list contents for this data type. This
is a latent defect affecting every list-returning HumanEval task in the
corpus (`sort_array`, `remove_duplicates`, `sort_third`,
`triples_sum_to_zero` all return lists; none happened to have a selected
fault in this run, so the bug has not yet produced an incorrect number, but
it would on the next one that does). **Do not scale up, and do not trust
any future list-typed fault's FDR, until `src/fault_runner.build_outcomes`
normalizes `faulty_output`/`reference_output` the same way
`expected_output` is normalized before comparing them** (e.g., by applying
`normalize_for_comparison` — or an equivalent canonical-form conversion — to
all three values symmetrically at comparison time, not just to the
JSON-sourced one at parse time).

No other bug, leakage, or aggregation defect was found. Items 1-3, 5 (for
4 of 5 faults), 7, 8, 9, and 10 all independently check out as
methodologically sound.

---

## 12. Post-fix verification (applied after this audit's initial verdict)

**Fix applied** (full description in `EXPERIMENT_LOG.md` Entry 11; diff
shown to the user in the same turn as this section was added):

1. `normalize_for_comparison` moved from `src/humaneval_pilot.py` into
   `src/metrics.py` as the single shared implementation (recursive:
   `list`/`tuple` -> `tuple`, `dict` values normalized recursively, scalars
   and the `_Raised` exception sentinel untouched).
2. `src/fault_runner.build_outcomes()` now applies it to **all three**
   values — `faulty_output`, `reference_output`, and the oracle's
   `expected_output` — symmetrically, before any comparison.
3. `src/humaneval_pilot.parse_test_pool()` no longer normalizes at parse
   time; it stores the raw JSON-decoded value, matching its own
   (previously inaccurate) docstring.

**Regression tests:** `tests/test_fault_runner.py` (new, 10 tests) plus 11
new tests in `tests/test_metrics.py::TestNormalizeForComparison`. All 64
tests pass, including the critical case that would have failed under the
pre-fix code (`faulty=[1,3]`, `reference=[1,2]`, oracle wrongly expects
`[1,3]` -> must be `triggered=True, detected=False`).

**Re-verification, from the existing saved LLM artifacts only** (no
candidate/test regeneration):

| Check | Result |
|---|---|
| Fault selection (`real_experiment_fault_selection.json`) | Identical before/after — same 5 tasks, same candidate indices, same difficulty scores (expected: selection depends only on `triggered`, never on the buggy `detected` path) |
| Aggregate Table IV row | Identical: mutation 0.920/0.920, branch 0.574/0.574, statement 0.574/0.574 |
| Per-fault, per-criterion FTR/FDR (15 rows) | Identical, all 15 |
| Raw CSV, row by row (1,500 rows) | 0 rows differ in `triggered`, `detected`, or `selected_test_count` |
| Synthetic experiment (600 rows, regression check) | 0 rows differ (never exposed to this bug — its oracles are plain strings/booleans) |

**Confirmed: the bug was latent but non-impacting for this specific
dataset.** It never changed a reported number, because (a) `detected`
requires `triggered` first, which correctly gated out the vacuous oracle
flag on every non-triggering test regardless of the bug, and (b) on
`count_up_to`'s one triggering test, the generated oracle's content was
independently correct anyway — the buggy vacuous `True` and the corrected
content-based `True` happened to coincide. Had that one oracle instead been
wrong, the pre-fix code would have silently produced a false-positive
`detected=True`; this was a real, live defect, not a hypothetical one, now
closed at the source for any future scale-up.

## 13. Final verdict (post-fix)

**A. RESULT VERIFIED — implementation and aggregation are methodologically
correct**, as of the fix in Entry 11. The Section 11 verdict (B) applied to
the code as it stood at audit time; the fix has since been applied,
regression-tested, and the entire real-experiment pipeline re-run from the
existing saved artifacts with zero change to any reported value. No
further bug, leakage, or aggregation defect remains open.
