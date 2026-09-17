# EXPERIMENT_LOG.md

Running log of decisions, problems, and outcomes during this reproduction.
Entries are append-only; failed approaches are kept, not deleted, because
they are part of the research record.

---

## 2026-09-11 — Entry 1: Search for official replication package

**Attempt:** Before generating any substitute data, searched thoroughly for
an official replication package / artifact for arXiv:2609.09315.

**What was checked:**
- arXiv abstract page and full HTML text (scanned for "replication",
  "artifact", "github", "zenodo", "data availability").
- Web search: arXiv ID + "replication package"/"GitHub".
- Web search: all four author names + "replication package"/"github"/
  "zenodo".
- Web search: arXiv ID / paper title + "zenodo".
- Renzo Degiovanni's personal publications page.
- Mike Papadakis's homepage and publications page.
- Michael Konstantinou's full GitHub repository list (18 repos, inspected
  by name/description/date).

**Finding:** No replication package, dataset, GitHub repo, or Zenodo record
exists for this paper. The paper's own text mentions "our replication
package" once (in the RQ2/Figure 4 discussion) but provides no URL and no
data-availability statement. The paper was submitted 2026-09-08, only 3
days before this search — consistent with an artifact simply not having
been released/indexed yet.

**Decision:** Documented this clearly in `PLAN.md` Section 3 rather than
silently substituting data. Per the user's explicit instruction, stopping
here to confirm the fallback approach before generating any substitute
faulty implementations or test pools.

**Outcome:** Proceeding to ask the user how to source faults/tests for the
"real benchmark" phase (Phase 8), since no original artifact is available.
The synthetic example (Phase 4) and the core metric/sampling code (Phases
2–3) do not depend on this decision and can proceed regardless.

---

## 2026-09-11 — Entry 2: User decision on fault/test source for Phase 8

**Decision (from user):** Use Claude (this session's model) as a substitute
fault-generating LLM, via isolated subagent calls blind to the reference
implementation, for a 3-task HumanEval+ pilot first, then scale to ~20-30
tasks if the pilot works. Results must be labelled "Focused methodological
reproduction... using Claude-generated artifacts", never presented as the
paper's original Table IV. Handcrafted faults are reserved strictly for the
synthetic unit-test example. Full rationale recorded in `PLAN.md` Section 9.

**Outcome:** Proceeding with Phases 1-6 (skeleton, metrics, sampling,
synthetic example, coverage, mutation) before touching HumanEval+, since
none of that infrastructure depends on the fault source.

---

## 2026-09-11 — Entry 3: Mutation testing tool selection

**Problem:** The paper does not name a specific mutation testing tool
(Section II-A only cites general mutation testing literature). Phase 6
requires either identifying and using the paper's tool, or - if not
identifiable - choosing and justifying an established Python mutation tool.

**Attempt:** Installed `mutmut` 3.7.0 (`pip install mutmut`) and inspected
its design (CLI-driven, `mutmut run`, whole-project source discovery via
libcst, orchestrates pytest as a subprocess per mutant, caches results in a
SQLite db).

**Diagnosis:** Our experimental protocol (Section V of the paper) needs, for
a single small faulty function, to generate its mutants once and then
evaluate hundreds of different *subsets* of a test pool against those same
mutants (100 randomized resampling iterations per fault, as part of
`sample_test_suite`'s repeated `score_fn` calls). mutmut's subprocess/CLI
architecture (one pytest invocation per mutant against a whole project) is
built for a different shape of problem (a one-off CI-style project mutation
run) and would be far too slow to invoke per candidate-subset per iteration.
`cosmic-ray` has a similar CLI/whole-project orientation and was not
installed after recognizing the same mismatch from its documented design.

**Decision:** Implement a small, transparent, `ast`-based mutation engine
directly in `src/mutation_utils.py`, applying standard first-order mutation
operators from the mutation testing literature the paper itself cites
(ROR, AOR, BOR, constant perturbation). Mutants are compiled in-process
(via `importlib`) so that repeated scoring during sampling is fast. This is
real mutation testing (real mutants, real execution, real kill/survive
determination) - not a simulated score - just without a third-party CLI
wrapper, for the performance reason above. This is documented as the
Phase 6 simplifying assumption in `PLAN.md` and `report/report.md`.

**Outcome:** `mutmut` remains installed in the environment (harmless) but is
not used by any script; `requirements.txt` does not list it as a dependency.

---

## 2026-09-11 — Entry 4: coverage.py API verification

**Problem:** coverage.py's advertised public API is oriented around
producing whole-project reports (textual/HTML), not returning raw
per-single-run executed-line/executed-branch sets for one function call.

**Action:** Ran small interactive probes (not guessed) against the actually
installed `coverage==7.16.0` to find the right API: confirmed
`Coverage._analyze(file_path)` returns an `Analysis` object with
`.executed` (statement lines hit this run), `.statements` (all executable
lines, static), `.arcs_executed_set` (branch arcs hit this run), and
`.arc_possibilities` (all possible branch arcs, static). Verified with a
throwaway `grade()`-like function and two sample inputs that the executed
line/arc sets change correctly between different inputs.

**Decision:** Use this (underscore-prefixed, semi-private) method directly,
documented in `src/coverage_utils.py`'s module docstring, since it is the
only way to get precisely the per-run raw data our sampling algorithm needs
without re-invoking coverage.py's full reporting pipeline per candidate
subset.

**Outcome:** `src/coverage_utils.py` implements `measure_per_test_coverage`
on top of this, precomputing each test's individual coverage contribution
once, then building `statement_score_fn`/`branch_score_fn` as fast in-memory
set unions - verified end-to-end in Entry 5.

---

## 2026-09-11 — Entry 5: Phase 4 synthetic experiment - first full pipeline run

**Action:** Implemented `src/metrics.py`, `src/sampling.py`,
`src/coverage_utils.py`, `src/mutation_utils.py`, `src/fault_runner.py`, and
`scripts/run_synthetic_experiment.py`/`scripts/build_table_iv.py`. Ran the
full pipeline (100 iterations x 3 criteria x 2 hand-crafted faults) via
`python -m scripts.run_synthetic_experiment` followed by
`python scripts/build_table_iv.py`.

**Result (actually computed, not simulated):**

| fault_id | criterion | FTR | FDR | mean suite size |
|---|---|---|---|---|
| synthetic_grade_boundary_fault | statement | 0.49 | 0.20 | 4.00 |
| synthetic_grade_boundary_fault | branch | 0.49 | 0.20 | 4.00 |
| synthetic_grade_boundary_fault | mutation | 1.00 | 0.45 | 3.75 |
| synthetic_parity_inverted_fault | statement | 1.00 | 0.72 | 2.00 |
| synthetic_parity_inverted_fault | branch | 1.00 | 0.72 | 2.00 |
| synthetic_parity_inverted_fault | mutation | 1.00 | 1.00 | 2.33 |

**Diagnosis (why this is a meaningful sanity check, not just "it ran"):**
- `synthetic_grade_boundary_fault` is a genuinely hard-to-trigger boundary
  bug (only `score == 70` reveals it). Statement/branch-adequate suites
  reach full statement/branch coverage of the faulty function *without*
  needing the specific boundary test (other tests already cover the same
  lines/branches), so FTR is only 0.49. Mutation-adequate suites are forced
  to include a boundary-discriminating test to kill the relational-operator
  mutants near that comparison, so FTR reaches 1.00. This reproduces, in
  miniature, exactly the paper's central claim that mutation testing can
  outperform structural coverage on hard-to-trigger faults, precisely
  because coverage criteria are insensitive to *which* input is chosen as
  long as the same lines/branches are hit.
- FDR < FTR in every row where a weak-oracle test is what's driving
  triggering, confirming the FTR/FDR distinction (Definition 3) is wired
  correctly, not just always equal to FTR.
- `synthetic_parity_inverted_fault` is a trivial, easy-to-trigger fault (any
  odd/nonzero input differs), so FTR=1.00 for all three criteria, consistent
  with the paper's Fig. 2 observation that many faults are "relatively
  simple to find" (a difficulty near 0 in the paper's Definition 5 terms).

**Outcome:** All 43 unit tests pass (`python -m pytest -q`), including four
tests that directly check the assignment's four required demonstration
scenarios (`tests/test_synthetic_experiment.py`). Proceeding to `README.md`,
`requirements.txt`, `.gitignore`, then the HumanEval+ pilot (Phase 8).

---

## 2026-09-11 — Entry 6: HumanEval+ 3-task pilot - candidate/test generation

**Action:** Obtained real HumanEval reference implementations via the
`human-eval` PyPI package (bundles `HumanEval.jsonl.gz` locally, no network
fetch needed - see note on HumanEval vs HumanEval+ below). Selected 3 pilot
tasks: `HumanEval/0` (`has_close_elements`), `HumanEval/3` (`below_zero`),
`HumanEval/8` (`sum_product`) - simple, well-known tasks chosen for a first
pilot. Saved prompts + canonical solutions to
`data/pilot_humaneval_tasks.json`.

Dispatched 6 isolated subagent calls (3 candidate-generation + 3
test-generation), each given ONLY the task's prompt (docstring + signature)
- never the reference solution, never a candidate implementation for the
test-generation calls. Each candidate-generation call asked for 5
independent implementations (reduced from the paper's 10, documented
reduction for pilot cost); each test-generation call asked for 12-15
structured `{args, expected_output}` test cases (assumption A2' from
PLAN.md). Raw outputs saved verbatim to
`data/pilot_generation/*_candidates.txt` and `*_tests.json`.

**Note on HumanEval vs HumanEval+:** we use the original HumanEval's
canonical solutions (identical between HumanEval and HumanEval+ - HumanEval+
only strengthens the *provided test suite*, not the reference
implementations) as ground truth. We do not use HumanEval+'s stronger test
suite at all, since our own protocol generates an independent test pool via
a blind LLM pass, mirroring the paper's own test-augmentation step rather
than reusing benchmark-provided tests.

**Result of fault classification (computed, not assumed):** Ran every
candidate against the real reference implementation over its task's
generated test pool (`src/humaneval_pilot.classify_candidates`).
**0 of 15 candidates (5 per task x 3 tasks) diverged from the reference on
any test.** Every candidate was classified as behaviorally correct. As an
additional sanity check, cross-checked every one of the 45 generated test
oracles' `expected_output` directly against the real reference
implementation: **0 disagreements** - the generated test pools are also all
correct on these 3 tasks.

**Diagnosis:** This is a genuine null result, not a bug in our harness (the
same code correctly found the hand-injected boundary bug in the Phase 4
synthetic experiment). `has_close_elements`, `below_zero`, and `sum_product`
are simple, extremely well-known introductory exercises; it is plausible
that a capable model reliably solves them correctly, consistent with the
paper's own observation that not all generations are faulty (their overall
faulty rate across all tasks/models was ~31.6%, and simpler tasks likely
sit well below that average). The paper's own methodology (Section IV-C-1)
anticipated this exact problem and addressed it by additionally prompting
with *under-specified/ambiguous* task descriptions (via Larbi et al.'s
prompt variants) specifically "to increase the likelihood and diversity of
the faulty implementations generated" - i.e., using harder/more complex
tasks and/or deliberately under-specified prompts is not a deviation from
the paper, it is the paper's own documented technique for this exact
problem.

**Decision:** Stopping here to report this null result to the user (per
their explicit request to see pilot results and problems before scaling)
rather than silently expanding scope or picking different tasks
unilaterally. Proposed next step: adopt the paper's own under-specification
technique and/or select more complex HumanEval tasks for a second pilot
batch, pending user direction.

**User decision:** Use under-specified prompts on the SAME 3 tasks (not
harder tasks), following the paper's own technique.

---

## 2026-09-11 — Entry 7: Under-specified prompt variants (second pilot batch)

**Important caveat documented explicitly:** we do not have access to Larbi
et al.'s actual under-specified prompt artifacts (that is a separate,
unpublished-to-us dataset cited by the paper). We therefore constructed our
OWN under-specified variants of the 3 pilot prompts, in the same *spirit*
described by the paper (removing a disambiguating detail/example so the
specification becomes genuinely ambiguous on one particular edge case) -
this is our own construction, not a reuse of Larbi et al.'s artifact, and is
documented here as such.

Changes made per task (only the prompt given to the candidate-generation
subagent changed; the test pools - built from the clear, original spec in
Entry 6 - are reused unmodified, since they represent ground-truth intent
that a prompt-confused implementation should still be checked against):

- **has_close_elements**: removed both worked examples and reworded the
  docstring to drop the phrase "are any two numbers"; kept a single vaguer
  sentence: "Check if any numbers in the given list are close to each
  other, closer than a given distance." No examples remain to anchor
  strict-vs-inclusive threshold semantics or pairwise-comparison intent.
- **below_zero**: removed both worked examples and the disambiguating
  detail was reworded from "at that point function should return True" to
  a vaguer "detect whether the account balance ever becomes negative" -
  removing the concrete walk-through of *when* during the operations this
  is checked.
- **sum_product**: removed the explicit sentence "Empty sum should be equal
  to 0 and empty product should be equal to 1." and removed the
  `sum_product([])` example, leaving only the `sum_product([1,2,3,4])`
  example. This specifically targets the non-obvious empty-list product
  identity (1, not 0), a well-known naive-implementation mistake pattern.

**Outcome:** proceeding to dispatch 3 new candidate-generation subagent
calls (5 candidates each) using these under-specified prompts.

**Result:** Again **0 of 15 candidates diverged from the reference** on the
existing (correct) test pools. Combined with Entry 6, this is **0 faults
out of 30 total candidates** across 3 tasks, both with the original and
with under-specified prompts.

**Supporting evidence this is not a fluke of our method:** the paper's own
Table II reports only **520 of 6,066** final non-trivial faults (8.6%) came
from HumanEval, across all 5 of the paper's fault-generating models -
substantially lower than HumanEval's ~13.6% share of the paper's total
generation budget (16,400 of 233,300 initial generations, Table I), and far
below BigCodeBench's share (3,925/6,066 = 64.7%). This is independent
evidence, from the paper itself, that HumanEval is the *hardest* of the 4
benchmarks to reliably induce faults on, even for the paper's own 5 models
and its more aggressive (10x, temperature 0.8, plus under-specified
prompt variants from a dedicated separate study) generation protocol. Our
null result on 2 independent HumanEval attempts (original + under-specified
prompts, 30 candidates total) is consistent with, not contradictory to,
the paper's own data.

**Decision:** Reporting this second null result to the user rather than
continuing to spend budget on the same 3 easy tasks. Proposing to move to
more algorithmically intricate HumanEval(+) tasks (still within the
Phase 8 "HumanEval+ only" scope), combined with under-specified prompts,
for a third pilot attempt.

**User decision:** switch to 3 trickier tasks known for classic off-by-one/
edge-case traps, combined with under-specified prompts: `HumanEval/18`
(`how_many_times` - overlapping substring counting), `HumanEval/33`
(`sort_third` - index-conditional reordering), `HumanEval/43`
(`pairs_sum_to_zero` - distinct-element pair check).

---

## 2026-09-11 — Entry 8: Third pilot batch - trickier tasks, under-specified

**Under-specification applied per task** (again, our own construction in
the spirit of the paper's technique, not a reuse of Larbi et al.'s
artifact):

- **how_many_times**: removed the sentence "Count overlaping cases." and
  removed the third example (`how_many_times('aaaa', 'aa') == 3`, which
  demonstrates overlap-counting), keeping only the two non-overlap-revealing
  examples. Targets the classic `str.count()` bug, which under-counts
  overlapping matches (`'aaaa'.count('aa') == 2`, not 3).
- **sort_third**: removed the second example
  (`sort_third([5,6,3,4,8,9,2]) == [2,6,3,4,8,9,5]`, the only example that
  actually exercises non-trivial sorting-at-every-3rd-index behavior),
  keeping only the trivial first example (`[1,2,3] -> [1,2,3]`, which has
  only one index divisible by 3 and is therefore a no-op regardless of a
  correct or incorrect implementation).
- **pairs_sum_to_zero**: removed the word "distinct" from "two distinct
  elements" (-> "two elements"), and removed 2 of the 4 examples, keeping
  only `pairs_sum_to_zero([2,4,-5,3,5,7]) == True` and
  `pairs_sum_to_zero([1]) == False`. Targets the classic "does a complement
  exist in the list" bug pattern (`for x in l: if -x in l: return True`)
  which self-pairs incorrectly when `x == 0` and only one zero is present.

**Outcome:** proceeding to dispatch 3 candidate-generation + 3
test-generation subagent calls (blind, as before) using these
under-specified prompts.

**Result:** **0 of 15 candidates diverged from the reference** again. This
is the THIRD consecutive null result: **0 faults out of 45 total
candidates**, across 6 different HumanEval tasks (3 easy + 3 deliberately
tricky/off-by-one-prone), with both original and under-specified prompts.
Manually reviewing the generated code confirms it is genuinely handling the
tricky cases correctly (e.g. `how_many_times` candidates consistently use
sliding-window or `str.find(..., start=idx+1)` patterns that correctly
count overlaps, rather than the classic `str.count()` under-counting bug;
`pairs_sum_to_zero` candidates consistently use "seen so far" or
distinct-index patterns that correctly avoid self-pairing a lone zero).

**Diagnosis:** This is a real, negative finding about our substitute-LLM
setup, not a harness defect (the same code correctly flags the Phase 4
hand-crafted fault). A single strong current-generation model (Claude, one-
shot, blind to the reference), even when the task prompt is deliberately
weakened, reliably produces correct code on HumanEval-style problems that
are individually simple, self-contained, and (very likely) well-represented
in training data - unlike the paper's protocol, which pools generations
from 5 different models including weaker/older ones (Llama-3.3-70B,
DeepSeek-v4-flash) across 10 samples at temperature 0.8 each, and explicitly
uses a separate, dedicated adversarial prompt-defect study (Larbi et al.)
that we cannot fully reproduce (Entry 7 caveat). Our one-model, one-shot,
self-authored-ambiguity setup is a strictly weaker fault-inducing pressure
than the original paper's.

**Decision:** Stopping to report this to the user rather than unilaterally
either (a) burning further budget on more of the same, or (b) silently
switching to hand-crafted faults for the real-benchmark phase, which the
user explicitly ruled out for anything but the synthetic example.

**User decision:** Accept the 0/45 null result as a legitimate, documented
pilot finding. Do not force a fault to appear artificially. This is now the
official pilot finding, to be written up honestly in `report/report.md`
(Section 13/14) rather than treated as a failed attempt to be hidden.

**Immediate implication for scale-up:** naively repeating the same protocol
(single strong model, one-shot, blind generation) at 20-30 tasks carries a
real risk of yielding few or zero additional faults, at a real subagent-
token cost, given the consistent 0/45 result across 6 varied tasks and two
prompting strategies. Before spending that budget, we are taking this back
to the user as a distinct decision (see next entry).

---

## 2026-09-11 — Entry 9: Haiku (weaker model) as fault-generator - success

**User decision:** try a weaker/smaller model (Claude Haiku 4.5, via the
Agent tool's `model` parameter) as the candidate-generation subagent on the
same 5 of the 6 pilot tasks (dropped `sum_product` to keep the batch at 5
per the user's ask), reusing the existing validated test pools and prompts
(original for the 2 easy tasks, under-specified for the 3 tricky tasks).
Rationale: mirrors the paper's inclusion of weaker models
(Llama-3.3-70B-Instruct, DeepSeek-v4-flash) alongside stronger ones - still
a real LLM, zero hand-crafting.

**Result:** `has_close_elements`, `below_zero`, `sort_third`,
`pairs_sum_to_zero` - still 0/5 faulty each. **`how_many_times` - 4/5
candidates faulty** (candidates 0, 1, 3, 4). Candidate 0
(`return string.count(substring)`) is the textbook non-overlap-counting
mistake predicted in Entry 8; candidates 1 and 4 use equivalent
non-overlapping `str.find`/`str.replace`-based logic; candidate 4's
`re.findall` also does non-overlapping matching by default. Only candidate 2
(direct sliding-window slicing) is correct. Difficulty = 0.600 (6/15 pool
tests trigger it) - **below the paper's 0.75 non-trivial threshold**,
reported honestly as such rather than silently treated as equivalent to a
paper-qualifying hard fault.

**First real (non-synthetic) Table IV row produced**
(`results/real_experiment_table_iv.csv`, `scripts/run_experiment.py`):

| benchmark | fault_model | mutation FTR | branch FTR | statement FTR | mutation FDR | branch FDR | statement FDR |
|---|---|---|---|---|---|---|---|
| HumanEval+ | claude-haiku-4-5 | 0.0 | 0.42 | 0.42 | 0.0 | 0.42 | 0.42 |

**Problem found while inspecting this result:** mutation FTR/FDR = 0.0 looked
suspicious (worse than random). Diagnosis: `generate_mutants` on the
selected faulty source (`return string.count(substring)`, a one-liner with
no comparisons/arithmetic/boolean-logic/numeric-literals) produces **0
mutants**. With 0 mutants, `mutation_score_fn` is vacuously 1.0 for any
subset including the empty one, so `sample_test_suite` stops immediately
having selected zero tests, hence mutation never triggers anything. Not a
bug in the sampling/scoring logic (correct handling of a documented edge
case) but a real coverage gap in our operator set for very short
return-only functions, which are common in HumanEval-style solutions.

**Decision (user-approved):** add a Return Value Replacement (RVR) mutation
operator to `src/mutation_utils.py` (`return <expr>` -> `return True` /
`return False` / `return None`), a standard operator category in the
mutation testing literature, chosen specifically because it applies to any
return statement regardless of its contents. Verified directly:
`generate_mutants` on the same one-liner now produces 3 mutants. Re-ran the
full test suite (43/43 pass, no regression) and both experiments:
synthetic results unchanged (600/600 rows identical FTR/FDR - those
functions already had comparisons for ROR to act on); real experiment's
mutation FTR/FDR changed from 0.0 to **0.6** (now correctly matching or
exceeding branch/statement's 0.42, restoring the qualitatively expected
"mutation >= structural coverage" pattern for this fault).

**Outcome:** proceeding to scale up per the user's approval, adding 15 new
HumanEval tasks (bringing the total distinct tasks attempted to 20, the low
end of the 20-30 target) using Haiku for candidate generation.

---

## 2026-09-11 — Entry 10: 20-task scale-up - final pilot results

**Action:** Added 15 new HumanEval tasks (make_palindrome, string_xor,
longest, remove_duplicates, concatenate, triples_sum_to_zero,
is_simple_power, count_up_to, sort_array, prod_signs, can_arrange,
cycpattern_check, encrypt, move_one_ball, compare_one), chosen for known
edge-case/off-by-one trap potential per common HumanEval difficulty
discussions, using ORIGINAL (not under-specified) prompts this time for
simplicity, since Haiku already demonstrated real mistakes without needing
deliberate under-specification (Entry 9). Candidate generation via Haiku (5
per task, blind); test generation via the default model (blind), 10-15
structured tests per task. All 30 raw artifacts saved under
`data/pilot_generation/`.

**Result:** **8/75 new candidates faulty**, across 4 of the 15 new tasks:

| Task | Faulty/Total | Best difficulty | Meets 0.75 threshold |
|---|---|---|---|
| concatenate (`sum(strings, "")` crashes - TypeError) | 1/5 | 0.000 | No (trivial - crashes on everything) |
| count_up_to (unconditionally includes 2 in the prime list even when n=2, where 2 is not < n) | 1/5 | 0.917 | **Yes** |
| encrypt (**5/5** candidates wrongly extend the rotation cipher to uppercase letters, a case the spec's examples never cover) | 5/5 | 0.917 | **Yes** |
| move_one_ball (`break_count == 1` branch wrongly special-cases and returns False for an already-sorted array, whose circular break-count is always exactly 1) | 1/5 | 0.833 | **Yes** |

11 of the 15 new tasks (make_palindrome, string_xor, longest,
remove_duplicates, triples_sum_to_zero, is_simple_power, sort_array,
prod_signs, can_arrange, cycpattern_check, compare_one) - 0/5 faulty each,
consistent with the pattern from Entries 6-9 that many canonical HumanEval
tasks are reliably solved correctly.

The `encrypt` result is a particularly notable finding: all 5 independently
generated candidates made the identical mistake (over-generalizing the
lowercase-only rotation logic to uppercase letters), because the task's
worked examples never include an uppercase letter - a genuine, reproducible
LLM blind spot, not a random one-off error.

Combined with the earlier `how_many_times` fault (Entry 9), the pilot now
has **5 real faults** across 20 attempted HumanEval tasks (25 candidates x
... total 100 Haiku-generated candidates across all 20 tasks, 9 faulty).

**Final Table IV-style result**
(`results/real_experiment_table_iv.csv`, 1,500 raw rows in
`results/real_experiment_raw_results.csv`, 100 iterations x 3 criteria x 5
faults):

| benchmark | fault_model | mutation FTR | branch FTR | statement FTR | mutation FDR | branch FDR | statement FDR |
|---|---|---|---|---|---|---|---|
| HumanEval+ | claude-haiku-4-5 | 0.920 | 0.574 | 0.574 | 0.920 | 0.574 | 0.574 |

Per-fault breakdown (see `results/real_experiment_raw_results.csv`) shows
this aggregate is not an artifact of averaging: on `count_up_to`,
statement/branch FTR is only 0.13 while mutation FTR is 1.00 (mutation
mutants of the `primes=[2]`/`range(3,n,2)` literals force inclusion of a
small-n test that a random coverage-adequate suite rarely picks); similarly
for `move_one_ball` (0.32 vs 1.00). On `encrypt`, all three criteria reach
1.00 because achieving full statement/branch coverage of the faulty
function *also* requires exercising its uppercase branch, which happens to
be the same branch that reveals the bug - a case where structural coverage
and mutation coincide. FDR equals FTR in every row here (unlike the paper's
much larger gap) - our small, carefully-generated test pools (10-15 tests,
reasoned through explicitly by a capable model) had essentially no weak
oracles among the tests that mattered for these specific faults, unlike the
paper's much larger LLM-Plain pools aggregated over thousands of tests.

**Decision:** This is a substantive enough real-benchmark result (5 real
faults, 20 tasks, matching the paper's qualitative "mutation > structural
coverage on hard faults" finding on 3/5 faults) to stop scaling further and
move to consolidating the report, README, and final documentation.

---

## 2026-09-11 — Entry 11: Post-hoc audit found and fixed a real oracle-comparison bug

**Problem:** before pushing to GitHub, a methodological audit was requested
of the real-experiment result, specifically because `FTR == FDR` exactly
for every criterion in the aggregate table — suspicious given the paper's
central finding that triggering and detection usually diverge. Full audit
in `AUDIT.md` (written before any fix, per the audit's own instructions not
to modify code/results until reviewed).

**Root cause found:** `src/humaneval_pilot.parse_test_pool()` normalized a
generated test oracle's `expected_output` at parse time (JSON list ->
Python `tuple`, via a local `normalize_for_comparison` helper), but
`src/fault_runner.build_outcomes()` never applied the same normalization to
the *actual* `faulty_output`/`reference_output` obtained by calling the
real functions. For any HumanEval task whose function naturally returns a
Python `list` (`count_up_to`, and also `sort_array`, `remove_duplicates`,
`sort_third`, `triples_sum_to_zero` — none of which happened to have a
selected fault in this run), the oracle comparison
`oracle_flags_error = faulty_output != t.expected_output` degenerated to
`some_list != some_tuple`, which is unconditionally `True` in Python
regardless of contents — the oracle check was vacuous (always "flagging an
error") for every test on every list-returning function, irrespective of
whether the LLM's generated oracle was actually right or wrong.

**How it was found:** by writing throwaway diagnostic scripts (not trusting
the CSV) that recomputed `triggered`/`detected` directly from
`data/pilot_generation/*` for every test in every one of the 5 faults' full
pools, and specifically searching for `triggered=True, detected=False`
instances. Zero were found; for 4 of 5 faults this was genuinely explained
by correct oracles (independently verified against the real HumanEval
reference), but for `count_up_to` the oracle-correctness check itself
(naive `==`) reported 0/12 "correct" due to the same list/tuple mismatch —
which, on investigation, turned out to be the bug rather than evidence of
a wrong oracle.

**Fix applied** (see code diff in the corresponding commit / diff shown to
the user):
1. Moved `normalize_for_comparison` out of `src/humaneval_pilot.py` and
   into `src/metrics.py` (the shared, dependency-free core module), as the
   single canonical implementation — recursive, converts `list`/`tuple` to
   `tuple`, recurses into `dict` values, leaves scalars and the `_Raised`
   exception sentinel untouched.
2. `src/fault_runner.build_outcomes()` now applies this same function to
   **all three** values before any comparison: `faulty_output`,
   `reference_output`, and the generated oracle's `expected_output` -
   symmetrically, not just to the oracle side.
3. `src/humaneval_pilot.parse_test_pool()` no longer normalizes at parse
   time at all (it stores the raw JSON-decoded value); normalization now
   happens exactly once, centrally, at comparison time in `build_outcomes`.
   This also fixes a docstring/code mismatch that existed even before this
   incident (the old docstring already claimed normalization happened "at
   comparison time," but the code was actually doing it at parse time).

**Regression tests added:** `tests/test_fault_runner.py` (new file, 10
tests) exercising the exact bug scenario end-to-end via `build_outcomes` —
including the critical case (`test_triggering_bug_with_wrong_oracle_is_not_detected`):
faulty returns `[1,3]`, reference returns `[1,2]`, oracle incorrectly
expects `[1,3]` (matching the faulty output) -> must be `triggered=True,
detected=False`. Before the fix this would have incorrectly reported
`detected=True`. Also added 11 direct unit tests for
`normalize_for_comparison` itself in `tests/test_metrics.py` (nested
list/tuple/dict structures, scalars, the `_Raised` sentinel). All 64 tests
pass (43 pre-existing + 21 new).

**Verification that fault selection was never affected:** `classify_candidates`'s
`is_faulty`/`difficulty` decisions depend only on `triggered` (via
`fault_difficulty`), never on `detected`/`oracle_flags_error` — and
`triggered` compares two real function-call outputs directly (never
touching JSON-derived data), so it was never affected by this bug. The same
5 tasks, same candidate indices, and same difficulty scores were selected
both before and after the fix (confirmed by diffing
`real_experiment_fault_selection.json` before/after — identical).

**Re-ran the real experiment from existing saved artifacts only** (no LLM
regeneration - `python -m scripts.run_experiment` reads
`data/pilot_generation/*_v3_haiku.txt`/`*_tests.json` unchanged) and rebuilt
the table. Compared old vs. new at every level:

- Aggregate table: **identical**, cell for cell (mutation 0.920/0.920,
  branch 0.574/0.574, statement 0.574/0.574).
- Per-fault, per-criterion FTR/FDR: **identical** for all 5 faults x 3
  criteria (15 rows).
- Raw CSV, row by row (1,500 rows, `triggered`/`detected`/
  `selected_test_count` columns): **zero rows differ**.
- Synthetic experiment (600 rows) also re-ran as a regression check:
  **zero rows differ** (its hand-crafted test oracles are all plain
  strings/booleans, never lists/tuples, so it was never exposed to this
  bug in the first place).

**The bug was confirmed latent but non-impacting for this specific
dataset.** It happened not to change any reported number because (a)
`detected` requires `triggered` first, which correctly gated out the
vacuously-`True` oracle flag on every non-triggering test regardless of the
bug, and (b) on `count_up_to`'s one triggering test, the generated oracle's
actual content was independently correct anyway, so the (buggy) vacuous
`True` and the (correct) content-based `True` happened to agree. Had that
one test's generated oracle instead been wrong, the pre-fix code would have
silently reported a false-positive detection — this was a real defect, not
merely a hypothetical one, and is now fixed at the source for any future
scale-up involving list-returning functions.

**Outcome:** `report/report.md` and `results/*.csv`/`*.md` require no
numeric changes (nothing in the report cites any value that changed). No
further scale-up performed per the user's instruction; still 5 real faults,
20 attempted tasks. `AUDIT.md` updated with a post-fix verification
section recording this outcome.

---

## 2026-09-11 — Entry 12: Controlled scale-up, Batch 2 - a real infinite-loop
bug found in a generated candidate, and a new timeout safety mechanism

**Task selection (frozen, predeclared, before any generation):** 20
additional HumanEval tasks selected via `random.Random(42).sample(eligible,
20)`, where `eligible` = all 164 HumanEval task IDs minus the 21 already
attempted. Full record (seed, eligible list, selected IDs) saved to
`data/scaleup_task_selection_record.json` *before* any candidate/test
generation began. Selected: HumanEval/{38, 9, 83, 74, 69, 47, 36, 160, 31,
125, 14, 13, 32, 67, 71, 149, 62, 124, 68, 132} (decode_cyclic, rolling_max,
starts_one_ends, total_match, search, median, fizz_buzz, do_algebra,
is_prime, split_words, all_prefixes, greatest_common_divisor, find_zero,
fruit_distribution, triangle_area, sorted_list_sum, derivative, valid_date,
pluck, is_nested) - a genuinely mixed-difficulty set (includes both trivial
tasks like `fizz_buzz` and notoriously hard ones like `find_zero` and
`valid_date`), confirming no cherry-picking occurred.

**Generation (frozen protocol, matching the batch that produced 4 of the
original 5 faults):** Claude Haiku 4.5, blind (prompt + signature only,
never the reference), 5 candidates per task, original (not under-specified)
prompts. All 20 candidate batches generated and saved to
`data/pilot_generation/*_candidates_v3_haiku.txt` before any classification
was attempted.

**Problem found while manually reviewing the generated code (before running
any classification):** `greatest_common_divisor` candidate 3
(subtraction-based Euclidean algorithm) infinite-loops whenever either
input is 0:

```python
def greatest_common_divisor(a: int, b: int) -> int:
    a, b = abs(a), abs(b)
    while a != b:
        if a > b:
            a = a - b
        else:
            b = b - a          # a == 0 here forever subtracts 0 from b
    return a
```

Verified directly with a thread-based, timeout-guarded probe - the probe
itself hung (its `ThreadPoolExecutor` context manager blocked on shutdown
waiting for the un-killable stuck thread) and had to be force-stopped via
`TaskStop`, conclusively demonstrating both the bug and why a thread-based
timeout cannot safely contain it (Python cannot forcibly terminate a
running thread).

**Decision:** stopped the experiment immediately (no test pool had been
generated yet for any of the 20 new tasks, and no candidate had been run
through `classify_candidates`/`build_outcomes`) and reported the finding to
the user before touching any code, per their explicit instruction to do so
for any newly discovered defect. This is a gap in the *execution harness*
(no candidate/reference call had ever needed a timeout in the original
audited batch), not a logic bug in the comparison/aggregation code that was
just audited (Entry 11) - but it is a real, confirmed hazard: any future
zero-valued test input for this specific candidate would hang the whole
pipeline indefinitely with no automatic recovery.

**User-approved fix:** add a `_TimedOut` sentinel and execute every
candidate/reference call in a **separate OS process** (not a thread - only
a process can be forcibly killed) with a hard timeout, keeping the
candidate itself in the experiment rather than excluding it (non-termination
is treated as part of the program's observable behavior, exactly like a
raised exception).

**Design and why:** `src/metrics.py` now runs a single **persistent**
worker process (not one fresh process per call) that receives
`(func, args, kwargs)` payloads over a queue and posts back results.
Measured on this machine: spawning a fresh process costs ~100-200ms
(Windows "spawn" re-runs interpreter startup) - with call volumes in the
hundreds to thousands per fault (once per test per candidate during
classification, plus once per test per mutant during mutation scoring),
spawning fresh per call would make the experiment impractically slow
(confirmed empirically: 5 spawns averaged 0.130s each). A single reused
worker keeps the common (no-timeout) case fast (confirmed: 5 repeated calls
after warm-up completed in ~0ms total), and is only killed
(`Process.kill()`) and replaced with a fresh one when a call actually times
out. The functions under test are dynamically compiled from LLM-generated
source via `exec` (and some reference functions in tests are lambdas), which
the standard library's `pickle` cannot serialize for transport to a
subprocess - `cloudpickle` (new dependency, `requirements.txt`) is used
instead, exactly the tool this ecosystem uses for this problem.

**Timeout value: 5.0 seconds** (`DEFAULT_CALL_TIMEOUT_SECONDS` in
`src/metrics.py`), chosen because every HumanEval-style function call in
this study (whenever it terminates at all) completes in well under 100ms;
5 seconds is generous enough to never false-positive on legitimately slow
(but terminating) code, while keeping the cost of a genuine hang bounded to
a few seconds rather than forever.

**Comparison rule for `_TimedOut` (the specific question the user asked to
be shown before continuing):**

- Two `_TimedOut` instances compare **equal** to each other. Rationale: if
  both the faulty and the reference implementation time out on the same
  input, neither side ever produced an answer to compare - there is no
  *observed* behavioral divergence, so `triggered` must be `False` for that
  test under Definition 1 (`triggered(f,t) <=> output(f,t) != output(p,t)`).
- A `_TimedOut` instance is **never equal** to a normal return value, and
  **never equal** to a `_Raised` instance (even one wrapping the same
  "conceptual" failure). Rationale: a program that raises an exception and
  one that never returns at all are different observable outcomes, and a
  program that hangs vs. one that returns a real answer are obviously
  different outcomes too. So: reference returns + faulty times out ->
  `triggered=True`; reference raises + faulty times out -> `triggered=True`;
  reference times out + faulty returns/raises -> `triggered=True` (fully
  symmetric); reference times out + faulty times out -> `triggered=False`.
- This exact rule was proposed by the user and implemented as specified,
  without alteration.

**Regression tests added** (`tests/test_metrics.py`:
`TestCallAndCaptureTimeout`, `TestTimedOutComparisonSemantics`;
`tests/test_fault_runner.py`: `TestTimeoutSemantics`): normal return still
works; raised exception still works; a hanging call returns `_TimedOut`
within the timeout; the worker recovers and serves normal calls correctly
after a kill; faulty-times-out-reference-returns -> triggered; reference-
times-out-faulty-returns -> triggered (the symmetric case); both-time-out
-> not triggered; two `_TimedOut` instances are equal; a `_TimedOut` is
never equal to a normal value or to a `_Raised`. **All 74 tests pass**
(64 pre-existing + 10 new), full suite runtime 7.91s (up from 0.6s, due to
~7 tests that each deliberately wait out a short 1s timeout).

**Direct verification on the actual candidate:** loaded
`greatest_common_divisor` candidate 3 via the real loader
(`src/humaneval_pilot.load_callable`) and called it with `(0, 5)` through
`call_and_capture(..., timeout=3)`: returned `TimedOut()` after ~3.05s
(no hang), and a subsequent normal call `(25, 15)` on the same (now
restarted) worker correctly returned `5` in 0.22s - the harness recovers
cleanly and continues to function correctly afterward.

**Outcome:** proceeding with the full 20-task scale-up (test-pool
generation, classification, and the 100-iteration protocol for any faults
found) using this now-hardened harness. No other frozen methodology
(FTR/FDR definitions, normalization, oracle representation, coverage,
mutation operators/scoring, difficulty, sampling algorithm, iteration
count, fault-selection rule) was touched.

---

## 2026-09-11 — Entry 13: Configuration check before the scale-up found a
second real bug - the timeout fix broke statement/branch coverage measurement

**Problem found during the pre-scale-up configuration check:** before
running the new 20-task batch, re-ran the already-audited 5-fault batch as
a sanity check (confirming the timeout hardening from Entry 12 had not
silently changed anything). It had: **branch and statement FTR/FDR dropped
from 0.574/0.574 to 0.0/0.0**; mutation stayed correct at 0.920/0.920.

**Root cause:** `coverage_utils.measure_per_test_coverage()` wraps a call
with `coverage.Coverage().start()`/`.stop()`, relying on `sys.settrace`-based
instrumentation, which is process-local - it can only observe execution
happening in the same process where it is installed. Entry 12's timeout fix
made every `call_and_capture` call execute inside a separate persistent
worker process, so the parent process's coverage.py trace hooks never
observed the child's execution. Every test then measured zero executed
lines/arcs, so `sample_test_suite`'s target score (matching the full pool)
became 0, trivially "met" by the empty selection - branch/statement
criteria collapsed to always selecting zero tests, hence FTR=FDR=0 for
those two criteria specifically. Mutation testing was unaffected because it
only ever compares return values (never uses coverage.py tracing).

**Decision:** stopped again immediately (before running anything on the new
20 tasks) and reported the finding, since it touches something on the
user's explicitly frozen list ("statement/branch coverage implementation").

**User-approved fix:** instrument coverage.py *inside* the same
timeout-guarded worker process, rather than in the parent. Implemented with
no changes to `src/metrics.py` at all: `src/coverage_utils.py` now builds a
small wrapper closure (`_make_coverage_probe`) that itself starts coverage,
calls the real function, stops coverage, and returns the executed line/arc
sets - and this whole closure is handed to the *existing*
`call_and_capture(probe, args, kwargs)` unchanged, so it runs inside the
worker process where the function actually executes, preserving both the
hard timeout and correct coverage attribution. A test whose probe times out
contributes an empty coverage set for that test (there is no way to recover
partial coverage from a process killed before it reached `cov.stop()`) -
this is the only behavioral compromise, and only affects tests that were
already going to time out regardless.

**Verification:** re-ran the audited 5-fault batch again after the fix -
**exact byte-for-byte restoration** of the correct values (mutation
0.920/0.920, branch 0.574/0.574, statement 0.574/0.574, and all 15
per-fault/per-criterion rows identical to the values verified in Entry 11).
Full test suite: 74/74 still passing.

**Outcome:** this is now the second infrastructure gap found and fixed
between the original audited batch and the scale-up (Entry 12: no
execution timeout at all; Entry 13: timeout mechanism broke coverage
tracing). Both fixes are execution-harness concerns, not changes to any
frozen experimental definition - FTR/FDR, normalization, oracle
representation, coverage's *definition* (statement/branch via coverage.py),
mutation operators/scoring, difficulty, the sampling algorithm, the
iteration count, and the fault-selection rule are all unchanged from the
audited batch. Proceeding with the 20-task scale-up now.

**Configuration check (as requested before the scale-up run):**
- Timeout value used for every candidate/reference execution in the
  production scale-up: **5.0 seconds** (`DEFAULT_CALL_TIMEOUT_SECONDS` in
  `src/metrics.py`), applied uniformly to `build_outcomes` (trigger/detect
  computation), `measure_per_test_coverage` (statement/branch), and
  `build_mutation_model` (mutation scoring) - none of these production call
  sites override the default. Only the unit test suite uses shorter
  timeouts (1-3s), confined entirely to `tests/`.
- This value is recorded in the run metadata written alongside the batch-2
  results (see `results/real_experiment_batch2_run_metadata.json`).

---

## 2026-09-11 — Entry 14: Batch 2 scale-up executed - results, and two
faults that turned out to be measurement artifacts rather than genuine bugs

**Task selection (fixed, predeclared, before any generation):** 20 tasks
via `random.Random(42).sample(eligible, 20)` where `eligible` = all 164
HumanEval IDs minus the 21 tasks with any prior artifact. Full record in
`data/scaleup_task_selection_record.json`. Selected:
`decode_cyclic, rolling_max, starts_one_ends, total_match, search, median,
fizz_buzz, do_algebra, is_prime, split_words, all_prefixes,
greatest_common_divisor, find_zero, fruit_distribution, triangle_area,
sorted_list_sum, derivative, valid_date, pluck, is_nested`.

**Generation and classification:** same frozen setup as batch 1's
successful round (Claude Haiku 4.5, blind, 5 candidates/task, original
prompts; blind test generation, 7-15 tests/task). 100 candidates
generated, **11 faulty**, across **3 of 20 tasks**
(`starts_one_ends`, `find_zero`, `valid_date` - 1, 5, and 5 faulty
candidates respectively). One selected fault per task per the frozen rule
(hardest by difficulty, ties broken by lowest candidate index):

| Task | Candidate | Difficulty | Meets 0.75? |
|---|---|---|---|
| `starts_one_ends` | 3 | 0.857 | Yes |
| `find_zero` | 0 | 0.000 | No |
| `valid_date` | 0 | 0.867 | Yes |

Ran the full frozen protocol (100 iterations x 3 criteria) on all 3 - 900
raw rows, 0 timeout events, 0 infrastructure failures. Full run metadata
(timeout=5.0s applied uniformly, task counts) in
`results/real_experiment_batch2_run_metadata.json`.

**Investigation of two of the three faults (before treating them as
genuine, per the conservative-interpretation instruction):**

- **`starts_one_ends` candidate 3**: a genuine implementation bug -
  mishandles `n=1` (returns 9, the count of ALL single-digit numbers,
  instead of 1, the count of numbers starting/ending with digit 1
  specifically). Oracle correctly detects it (FDR=FTR=1.00 on all
  criteria). A clean, unambiguous real fault.

- **`find_zero` candidate 0**: investigated by printing reference vs.
  faulty vs. oracle for all 8 tests. Reference computes
  `-0.5000000000582077`; the candidate computes exactly `-0.5`. **Both are
  correct to well within the task's own stated 2-decimal-place tolerance**
  - they are two different, independently-converged floating-point
  approximations to the same true root (the reference's own bisection
  implementation, using `[-1, 1]` starting bounds, and the candidate's
  Newton's-method implementation converge to slightly different floats).
  `triggered` (exact equality, Definition 1) is `True` on every single test
  as a structural consequence of comparing two independent floating-point
  iterative computations - not because the candidate is behaviorally wrong.
  The generated oracle's literal (the clean mathematical value) matches the
  candidate's output exactly, so `detected` is `False` on every test
  (FTR=1.00, FDR=0.00 across all criteria) - the oracle is, in a real
  sense, "more right" than the noisy reference here. **This is not a
  genuine implementation fault; it is a measurement artifact of exact
  float-equality comparison applied to an iterative numerical algorithm.**

- **`valid_date` candidate 0** (and all 5 candidates, identically):
  investigated by printing the real canonical solution. It contains:
  `if month in [1,3,5,7,8,10,12] and day < 1 or day > 31: return False` -
  a genuine **operator-precedence bug** (`and` binds tighter than `or` in
  Python, so this parses as `(month in [...] and day < 1) or (day > 31)`,
  not the intended `month in [...] and (day < 1 or day > 31)`), causing the
  *reference itself* to incorrectly reject valid dates like `12-31-2020`
  and `01-31-2020`. All 5 independently-generated candidates return the
  behaviorally-correct answer (`True`) for these two inputs, diverging from
  the (buggy) reference - hence `triggered=True`. The generated oracle,
  reasoning blindly from the NL specification, also independently arrived
  at the behaviorally-correct answer, so it does not flag the candidate's
  (correct) output as wrong - `detected=False` for both affected tests.
  **This is exactly the "defect in the reference solution could lead to
  misclassification" threat to validity the original paper itself names**
  (Section VII) - encountered here directly, not hypothetically.

**Why this matters for interpretation:** this is the first point in the
entire project where FDR < FTR for any fault (batch 1's 5 faults all had
FDR == FTR exactly). A naive reading would say "the new batch reproduces
the paper's oracle-quality gap." The precise reading is more conservative:
2 of the 3 new faults show the gap for reasons that are NOT "the LLM wrote
a careless assertion" (the paper's actual finding) - they are a
floating-point noise artifact and a reference-implementation bug,
respectively, both of which happen to make the *oracle* look "wrong" while
the oracle was in fact reasoning correctly about the true specification.
Only `starts_one_ends` is a clean instance of the paper's actual
phenomenon (a genuine candidate bug, correctly triggered and detected).

**Oracle statistics, combined across all 8 selected faults' full test
pools (93 tests total):** 83/93 (89.2%) of generated oracles exactly match
the reference's output; all 10 "incorrect" instances are concentrated
entirely in `find_zero` (8/8) and `valid_date` (2/15) - the two
artifact-affected tasks. The other 6 faults have 100% oracle accuracy.

**Timeout tracking:** added `faulty_timed_out`/`reference_timed_out`/
`timeout_seconds` fields to `RawResultRow` (`src/fault_runner.py`) and
corresponding properties to `TestOutcome` (`src/metrics.py`) - additive,
diagnostic fields only; they do not change `triggered`/`detected` or any
other frozen definition. Re-ran batch 1 after this addition and confirmed
byte-for-byte identical FTR/FDR values (43/43, then 74/74 tests still
passing throughout). Zero timeout events occurred in the actual 100-
iteration production runs for any of the 8 selected faults across both
batches - the known-hazardous `greatest_common_divisor` candidate was
never selected as a fault (0/5 faulty on this batch's blindly-generated
test pool, which happens not to include a zero-valued input), so its
hang risk was never exercised in practice, only in the isolated
verification from Entry 12.

**Outcome:** stopping here per the user's instruction not to expand beyond
these 20 additional tasks. Full results in
`results/real_experiment_batch2_*`, `results/real_experiment_combined_*`,
and `results/real_experiment_per_fault_table.csv`. Final counts, tables,
and analysis presented to the user; `report/report.md`, `README.md`, and
`FINAL_STATUS.md` updated accordingly.

## 2026-09-11 — Entry 15: Final results validity audit - no data changed,
one additional fault reclassified from "clean" to "uncertain"

With the 40-task dataset frozen (per Entry 14's stopping point), performed
a final semantic validity audit before submission: manually/programmatically
re-inspected all 8 selected faults against their original HumanEval task
specification (not just the reference implementation), per the user's
explicit instruction not to assume the reference is correct by default.
No candidates, tests, or sampled suites were regenerated; no stored result
file was edited. Full document: `FINAL_RESULTS_AUDIT.md`.

**Classification (Category A = genuine semantic fault, B = numerical-
equivalence artifact, C = apparent benchmark/reference defect, D =
uncertain):** `how_many_times`=A, `concatenate`=A, `count_up_to`=A,
`move_one_ball`=A, `starts_one_ends`=A, `find_zero`=B (confirmed - see
Entry 14), `valid_date`=C (confirmed and further verified - see below),
`encrypt`=**D, a new finding this session**.

**`encrypt` reclassified.** Entry 10/Section 13 of the report had described
`encrypt` as "the most convincing single result" - 5/5 independently
generated candidates rotating uppercase letters where the reference does
not. Closer inspection this session found the real HumanEval reference's
lookup table (`d = 'abcdefghijklmnopqrstuvwxyz'`) is lowercase-only by
construction, silently passing uppercase characters through unchanged - and
the task's natural-language spec never states or exemplifies uppercase
behavior at all (every worked example is lowercase). Since the spec is
silent rather than contradicted (unlike `valid_date`, below), this is
better classified as genuinely uncertain (Category D) than as a clean
instance of "5 candidates share a blind spot." It remains in every
reported view unchanged - reclassifying it does not remove it from the
data, and (since `encrypt` has FTR=FDR=1.00 on every criterion, i.e. no
trigger/detection gap) does not change any View A/B/C number.

**`valid_date` verified more rigorously than in Entry 14.** Brute-force
comparison of the reference against the literal spec text across all
12x31 month/day combinations (not just the 2 pool entries previously
inspected) found **18 distinct dates** where the reference's operator-
precedence bug causes it to wrongly reject a valid date (every day-30 in a
30-day month, every day-30/31 in a 31-day month). All 5 independently-
generated candidates were verified programmatically to agree with the
literal spec on all 372 combinations, with zero mismatches. This
strengthens, rather than changes, Entry 14's conclusion.

**Oracle reanalysis.** Recomputed oracle-vs-reference mismatches directly
per fault's full test pool (93 tests, 8 faults): 0 mismatches in 6 of the
8 pools, 8/8 in `find_zero`, 2/15 in `valid_date` - reproducing Entry 14's
83/93 (89.2%) figure exactly. Then checked each of the 10 mismatches
against ground truth independent of the reference: all 8 `find_zero`
mismatches match the true mathematical root (oracle correct, reference
carries a `5.82e-11` bisection-tolerance residual); both `valid_date`
mismatches match the literal spec (oracle correct, reference buggy).
**Genuinely-incorrect-oracle rate across the full 93-test combined pool:
0/93.** Every reference-disagreement in this dataset resolves in the
oracle's favor once checked independently - a materially different
statement than "10.8% of oracles are wrong."

**Three views computed and verified by hand + programmatically
(`FINAL_RESULTS_AUDIT.md` Sections 3 and 7):**

| View | Faults | Mutation FTR/FDR | Branch FTR/FDR | Statement FTR/FDR |
|---|---|---|---|---|
| A - inclusive (unchanged) | 8 | 0.950 / 0.700 | 0.633 / 0.484 | 0.633 / 0.484 |
| B - difficulty>=0.75 subset | 5 | 1.000 / 0.800 | 0.528 / 0.490 | 0.528 / 0.490 |
| C - excl. find_zero+valid_date | 6 | 0.933 / 0.933 | 0.645 / 0.645 | 0.645 / 0.645 |

**The key finding: View C's FTR/FDR gap is exactly zero on all three
criteria.** The entire trigger/detection gap visible in View A (and, more
strongly, View B) is attributable in full to `find_zero` and `valid_date`.
This is reported plainly rather than read as "our data confirms the
paper's oracle-quality finding" - the paper's finding is specifically about
LLM-generated tests writing weak/careless assertions, and neither excluded
case is an instance of that (Entry 14; `FINAL_RESULTS_AUDIT.md` Section 5).

**Outcome:** View A (the stored, previously-reported combined result) is
preserved exactly, unchanged, as the primary result. `report/report.md`
Section 11 was reorganized into the requested order (scope/yield, View A,
View B, View C, comparison, oracle observations, threats) and a new
"Unexpected benchmark-ground-truth issues" subsection added; Section 13's
`encrypt` bullet and Section 18's conclusion were rewritten to reflect the
D classification and to use the requested, more conservative closing
language ("reproduces the experimental methodology... on a reduced
independently generated HumanEval+ dataset", not "confirms"/"reproduces
Table IV"/"mutation testing is superior"). No pipeline code was changed;
this was a pure post-hoc interpretation pass on already-frozen data.
