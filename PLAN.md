# PLAN.md — Reproduction Plan for Table IV

**Paper:** "How effective are traditional test criteria at detecting bugs in
large language models generated code?" (arXiv:2609.09315, submitted 8 Sep 2026)

**Assignment:** Reproduce Table IV (Professor Benoit Baudry).

This document is written *before* any substantial implementation, per the
assignment instructions. It records what the paper actually says (verified
by reading the PDF directly, not just the assignment's summary), what is
reproducible, what is missing, and the strategy we will follow.

---

## 1. What Table IV Actually Measures

Table IV ("FAULT TRIGGER RATE (FTR) AND FAULT DETECTION RATE (FDR) ACROSS
FIVE LLM FAULT MODELS AND FOUR BENCHMARKS COMPARING THE THREE COVERAGE
CRITERIA") reports, for every (benchmark × fault-generating model) pair,
6 numbers: FTR and FDR for each of Mutation, Branch, and Statement coverage.
Values are "averaged over 100 iterations" (Section V).

### Core definitions (Section IV-A, quoted precisely from the PDF)

- **Fault Trigger** (Def. 1): `triggered(f, t) ↔ output(f, t) ≠ output(p, t)`
  — a test `t` triggers fault `f` if the faulty program `f` and the
  reference/correct program `p` produce different output on `t`.
  For a suite `T`: `triggered(f, T) ↔ ∃ t ∈ T : triggered(f, t)`.

- **Fault Trigger Rate** (Def. 2): `FTR(T) = |{f ∈ F : triggered(f,T)}| / |F|`

- **Fault Detection** (Def. 3): `detected(f, t) ↔ triggered(f, t) ∧
  output(f, t) ≠ oracle(t)` — the test must trigger the fault **and** the
  test's own oracle/assertion must flag the faulty output as wrong (i.e. the
  assertion in the generated test fails when run against the faulty program).
  For a suite: `detected(f, T) ↔ ∃ t ∈ T : detected(f, t)`.

- **Fault Detection Rate** (Def. 4): `FDR(T) = |{f ∈ F : detected(f,T)}| / |F|`

- Consequently `FDR(T) ≤ FTR(T)` always, since detection requires triggering
  plus a correct oracle.

- **Mutation Score** (Def. 6, 7): a mutant `m` is killed by suite `T` if
  `∃ t ∈ T: output(m,t) ≠ output(p,t)`. `MS(T) = killed / (killed + surviving)`.

### Experimental protocol that produces each cell of Table IV (Section V)

For a single faulty implementation `f` with its generated test pool `TS_f`,
and for one target criterion `C ∈ {statement, branch, mutation}`:

1. Start with an empty selected suite.
2. Repeatedly pick a **random** remaining test `t` from `TS_f`.
3. If adding `t` **increases** `C`'s score on the selected suite, keep it;
   otherwise discard it and draw another.
4. Stop when the selected suite's score under `C` equals the score of the
   *entire pool* `TS_f` (i.e., `C(selected) = C(TS_f)`).
5. Evaluate the resulting suite: does it trigger `f`? Does it detect `f`
   (i.e., does some test's own assertion fail on the faulty program)?
6. Repeat steps 1–5 **100 times** (100 independent random selections) per
   fault per criterion. This is why the paper reports "52,000 sampled test
   suites for HumanEval" = 520 faults × 100 iterations (and similarly for
   the other benchmarks).
7. For a given fault, its FTR/FDR is the fraction of the 100 sampled suites
   that trigger/detect it (0/100 to 100/100).
8. **Table IV's numbers are the mean of these per-fault rates, averaged over
   all faults belonging to that (benchmark, model) cell.** This is an
   important, easy-to-miss aggregation detail: Definitions 2/4 define FTR/FDR
   over a *set of faults F* for one suite, but the actual protocol computes a
   per-fault probability across 100 resamples and then averages across
   faults — we replicate the *protocol* (Section V) rather than a literal
   one-shot reading of Definitions 2/4, since Section V is the operational
   description used to build Table IV.

### Underlying fault corpus (Section IV-C, Table II)

6,066 "non-trivial" faults total, built by:
- Generating implementations from 4 benchmarks × 5 LLMs × 10 samples ×
  2 prompt variants (original + under-specified) = 233,300 generations.
- Keeping only implementations whose behavior differs from the reference
  on some test (73,785 "valid faulty implementations").
- Augmenting benchmark test suites with LLM-generated differential tests
  (via an LLM "tester") to strengthen the ground-truth comparison.
- Computing a **difficulty score** per fault (Def. 5: 1 − fraction of pool
  tests that trigger it) and discarding faults with difficulty < 0.75
  (i.e., keeping only faults triggered by < 25% of the augmented pool).
- Keeping only the single hardest fault per task.

### Test pool (Section IV-D)

Tests are generated once per faulty implementation using "LLM-Plain" — a
plain LLM-based test generator with no coverage feedback — producing large
pools (thousands of tests per benchmark total).

---

## 2. What Data/Artifacts Would Be Required for a Literal Reproduction

1. The 4 benchmark datasets with reference implementations (HumanEval+,
   MBPP, BigCodeBench, NaturalCodeBench) — **publicly available**.
2. The exact 6,066 faulty LLM-generated implementations (or enough info to
   regenerate an equivalent set) — **not published**, no replication link.
3. The exact LLM-generated + augmented test pools (with their oracles/
   assertions as originally generated) — **not published**.
4. The prompt-variant corpus from Larbi et al. (under-specified/ambiguous
   prompts) — referenced but not bundled in this paper.
5. Exact LLM versions/settings (GPT-5-mini, GPT-4.1-mini, Claude-Haiku-4.5,
   Llama-3.3-70B-Instruct, DeepSeek-v4-flash at temperature 0.8) — some of
   these (e.g. GPT-5-mini) require paid API access we do not have configured
   in this environment; reproducing the *exact* generation process is out of
   scope for a graduate assignment done locally.
6. The specific mutation testing tool/config used — **not named in the
   paper** (only cited generically via Papadakis et al.'s mutation testing
   survey [19] and Ammann & Offutt's textbook [3]). No tool name (e.g.
   `mutmut`, `cosmic-ray`, PIT, MutPy) appears anywhere in the text.

## 3. Search for a Replication Package

**Searched on 2026-09-11, thoroughly, before any substitute artifact was
created**, across the following sources:

1. arXiv abstract page (`arxiv.org/abs/2609.09315`) — no data/code links.
2. arXiv full HTML rendering (`arxiv.org/html/2609.09315`) — full text
   scanned for "replication", "artifact", "github", "zenodo", "data
   availability"; only one prose mention ("...detailed results in our
   replication package...", discussing Figure 4/RQ2) with **no URL and no
   footnote**.
3. General web search for the arXiv ID + "replication package" / "GitHub".
4. General web search for the author names (Asma Hamidi, Michael
   Konstantinou, Renzo Degiovanni, Mike Papadakis) + "replication package"
   / "github" / "zenodo".
5. Web search for `"2609.09315" OR "How effective are traditional test
   criteria" zenodo` — no Zenodo record found.
6. Renzo Degiovanni's personal publications page
   (`rdegiovanni.github.io/publications/`) — this paper is not even listed
   yet (it is a 3-day-old preprint as of the search date).
7. Mike Papadakis's homepage and publications page (`mpapad.github.io`,
   `mpapad.github.io/publications/`) — paper not listed yet; no matching
   code/artifact link among his other 2026 publications.
8. Michael Konstantinou's GitHub profile
   (`github.com/michaelkonstantinou`), all 18 repositories inspected by
   name, description, and last-push date. Most relevant hits are
   `llm-plain` (the test-generation *tool* cited as reference [36] in the
   paper — a generic tool, not this paper's dataset) and
   `replication-study-test-repair` (replication package for a **different**
   paper, on content-based test repair, last updated May 2026 — predates
   this paper's Sep 2026 submission). Nothing pushed since Aug 2026 relates
   to Table IV, faults, or coverage/mutation criteria.

**Conclusion: no official replication package, dataset, generated fault
corpus, generated test pool, or supplementary artifact could be found for
arXiv:2609.09315.** This is consistent with it being a very recent preprint
(submitted 2026-09-08, i.e. 3 days before this search) that has not yet had
an artifact released or indexed. Nothing is reused from an official source
because nothing official was found. See `EXPERIMENT_LOG.md` for the
timestamped log entry of this search.

## 4. What Is Reproducible From Available Information

- **The core FTR/FDR/mutation-score definitions** — fully reproducible;
  they are precise, formal definitions (Defs. 1–7).
- **The randomized, criterion-guided sampling algorithm** — fully
  reproducible; described unambiguously in Section V.
- **Statement and branch coverage measurement** — reproducible with
  `coverage.py`, a standard, well-documented tool.
- **Mutation score measurement** — reproducible using a real mutation
  testing tool (tool choice is our own decision, documented as an
  assumption, since the paper does not specify one).
- **HumanEval+ as a benchmark with reference implementations** — publicly
  available (EvalPlus / HumanEval).
- **The overall experimental protocol (steps 1–7 above) on a reduced,
  self-generated set of faults and tests** — reproducible in spirit, not
  in exact numbers, because the specific faulty implementations and LLM
  test pools from the paper are unavailable.

## 5. What Is Missing / Cannot Be Reproduced Exactly

- The original 6,066 faults and their exact difficulty rankings.
- The original LLM-generated test pools and their oracles.
- Exact numeric replication of Table IV's cell values — **impossible**
  without the original artifacts. We can only reproduce the *method* on a
  smaller, independently constructed dataset and compare *qualitative*
  trends (e.g., "FDR << FTR", "criteria differ only marginally") against
  the paper's reported trends.
- Some fault-generating LLMs are commercial/gated (GPT-5-mini, Claude
  Haiku 4.5) and reproducing the paper's exact generation pipeline for all
  five models is not practical for this assignment; see Section 8 below
  for the simplification we adopt.

## 6. Proposed Reproduction Strategy

Given the above, we follow a **layered strategy**, from fully controlled to
increasingly realistic, so every claim we make is backed by code we
actually ran:

1. **Synthetic reproduction** (Phase 4): a hand-written reference function,
   a few hand-written faulty mutants, and hand-written tests of varying
   oracle quality. This validates our FTR/FDR/sampling/coverage/mutation
   machinery end-to-end on a case small enough to verify by hand.
2. **Real benchmark, reduced-scope reproduction** (Phase 8): using
   HumanEval+ only (public, small, self-contained), we will:
   - Take reference solutions as ground truth.
   - Construct a *small* set of faulty implementations ourselves (since we
     cannot use the paper's), using a documented, simple, transparent
     method (see assumptions below) rather than 5 paid commercial LLMs.
   - Generate a test pool for each faulty implementation.
   - Run the criterion-guided random sampling procedure described in
     Section V, with 100 iterations per fault per criterion, computing
     FTR/FDR from actual code execution, not simulated numbers.
   - Aggregate into a Table-IV-shaped CSV/Markdown table, clearly labeled
     as a **"Focused reproduction of Table IV — HumanEval+ subset"**, not
     as the original Table IV.
3. Report honestly that benchmark coverage (only 1 of 4 benchmarks) and
   fault-model coverage (not the original 5 commercial/OSS LLMs) are
   reduced, and discuss why the numbers will legitimately differ from the
   paper (different faults, different test pools, much smaller sample).

## 7. Key Assumptions We Expect to Need (to be finalized during implementation)

These will be copied into `EXPERIMENT_LOG.md` and `report/report.md` as they
are actually made, but are anticipated here:

- **A1 — Fault source.** We cannot regenerate faults via GPT-5-mini/Claude-
  Haiku-4.5/etc. at the scale of the paper. We will use whichever LLM
  access is actually available in this environment to generate a *small*
  number of faulty implementations for a handful of HumanEval+ tasks
  (documented per Phase 8), OR, if no LLM code-generation access is
  available at all in this environment, we will construct faulty
  implementations via **manual, realistic mutation of reference solutions**
  (small logic changes resembling the kinds of mistakes described in the
  paper — off-by-one, wrong operator, boundary condition, incomplete
  condition) and clearly label these as "hand-crafted faults standing in
  for LLM-generated faults", not as LLM output.
- **A2 — Test pool source.** Likewise, the "LLM-generated test pool" will
  either be generated by an available LLM or, if unavailable, hand-written
  by us with deliberately mixed oracle quality (mirroring the synthetic
  example in Phase 4), and documented as such.
- **A3 — Mutation tool.** We will pick one established Python mutation
  tool (candidates: `mutmut`, `cosmic-ray`) and justify the choice in
  `EXPERIMENT_LOG.md`/report. This is a simplifying assumption since the
  paper names no tool.
- **A4 — Scope.** Only HumanEval+ is attempted for the "real benchmark"
  phase, and only a small number of tasks/faults (not all 164), for
  computational tractability. This will be explicit in every output file
  and table caption.
- **A5 — Aggregation level.** We follow Section V's protocol (average of
  per-fault rates across 100 resamples, then across faults in a cell)
  rather than a literal one-shot application of Definitions 2/4 over the
  whole fault set at once, since that is what actually produces Table IV.

## 8. Non-Goals (explicitly out of scope, to set expectations)

- We will **not** claim to reproduce exact Table IV numbers.
- We will **not** run all 4 benchmarks × 5 models.
- We will **not** fabricate FTR/FDR numbers to "look like" Table IV.
- We will **not** implement RQ2 (cost-efficiency curves) or RQ3
  (specification-guided oracle repair) in depth — those are separate
  research questions; we may briefly discuss them in the report if time
  permits, but Table IV (RQ1) is the assignment's actual target.

## 9. Confirmed Fallback Decision (2026-09-11, after user review of search results)

After the search in Section 3 found no official artifact, the user
confirmed the following approach for the real-benchmark phase (this
supersedes earlier speculative options and is the one actually implemented):

- Use **Claude (this session's model, invoked via isolated subagent calls)**
  as a single substitute fault-generating LLM, in place of the paper's five
  commercial/OSS models. This is a scope reduction, not a like-for-like
  substitute, and is labelled as such everywhere.
- Scope: **HumanEval+ only**, starting with a **3-task pilot**, then scaling
  to roughly **20–30 tasks** if the pilot works end-to-end.
- Blind generation: candidate implementations are generated by a subagent
  given only the task's NL prompt + function signature — never the
  reference implementation.
- Blind test generation: the test pool is generated by a separate subagent
  call, also given only the NL prompt + signature — never the reference
  implementation and never a candidate implementation. Tests are recorded
  in a structured `(args, expected_output)` form (see assumption A2' below)
  rather than free-form pytest source, so that fault-triggering and
  fault-detection can be computed exactly and safely, without executing
  arbitrary LLM-authored assertion code.
- The HumanEval+ reference implementation is used **only after** generation,
  purely as ground truth to (a) classify a candidate as faulty and (b)
  compute whether a given test input triggers a behavioral difference.
- Fault selection mirrors the paper's principle where feasible: keep
  implementations that diverge from the reference on some test, compute
  difficulty (Def. 5) from the generated pool, prefer difficulty ≥ 0.75, and
  keep the hardest fault per task. Given the much smaller pool size in our
  reduced experiment, we document if/when no candidate reaches the 0.75
  threshold and, in that case, still report the hardest one found, clearly
  labelled as below the paper's threshold.
- Coverage/mutation criteria are computed against the **faulty
  implementation itself** (the "program under test" in a realistic testing
  scenario), while triggering/detection are computed by comparing the
  faulty implementation's output against the HumanEval+ reference on the
  same input — consistent with Definitions 1–7.
- All prompts, generated candidates, generated tests, model identity, and
  generation settings are saved as reproducibility artifacts (see
  `data/` and `results/` under the real-experiment scripts).
- The final output table is labelled prominently:
  **"Focused methodological reproduction of Table IV — HumanEval+ subset
  using Claude-generated artifacts."** It is never presented as a
  reproduction of the paper's original Table IV values.
- Handcrafted faults are used **only** for the synthetic unit-test example
  (Phase 4), never for the real-benchmark experiment.
- If Claude-based generation cannot be driven programmatically/reproducibly
  in this environment, the plan is to stop and report the limitation rather
  than silently substitute another method (see A1 below).

### Assumption A2' (supersedes A2 above)

Generated tests are represented as a structured `{args: [...], kwargs: {...},
expected_output: <value>}` record instead of free-form pytest functions.
Executing a test means calling the candidate/reference function with
`args`/`kwargs`; the "oracle" is the equality check
`actual_output == expected_output`. This is a deliberate simplification of
"the test oracle/assertion" (Def. 3) that makes `output(f,t)`,
`output(p,t)`, and `oracle(t)` all mechanically computable and safe to
execute, while preserving the FTR-vs-FDR distinction: a test can trigger
(candidate output ≠ reference output) yet not detect (the LLM's
`expected_output` happens to still equal the candidate's — wrong — output).

---

*Next step: build the repository skeleton (Phase 1) and implement the core
FTR/FDR definitions with unit tests (Phase 2), then the synthetic
end-to-end example (Phase 4), then the HumanEval+ 3-task pilot.*
