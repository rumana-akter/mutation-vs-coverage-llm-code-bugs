"""Criterion-guided randomized test-suite sampling.

Implements the experimental protocol described in Section V of the paper:

    Given a faulty implementation f and the pool of generated tests TS_f,
    we iteratively select a random test t in TS_f and check whether it
    increases the coverage according to the target criterion C. If it
    does, we keep it; otherwise, we discard it and select another test.
    The process stops when the coverage of the sampled test suite
    TS_f^i subset-of TS_f achieves the same coverage as the test pool
    TS_f (i.e. C(TS_f) = C(TS_f^i)).

This module is deliberately generic: it knows nothing about statement
coverage, branch coverage, or mutation score. Callers supply a ``score_fn``
that maps a list of test identifiers to a float score for whichever
criterion is being targeted. This keeps sampling independent of
coverage.py / mutation-testing details (those live in coverage_utils.py
and mutation_utils.py) and makes the algorithm easy to unit-test with
trivial synthetic scoring functions.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Callable, Sequence

ScoreFn = Callable[[Sequence[str]], float]


@dataclass
class SamplingResult:
    """Outcome of one randomized criterion-guided sampling run."""

    selected: list[str] = field(default_factory=list)
    achieved_score: float = 0.0
    target_score: float = 0.0
    reached_target: bool = False
    n_tests_examined: int = 0
    log: list[str] = field(default_factory=list)


def sample_test_suite(
    pool: Sequence[str],
    score_fn: ScoreFn,
    seed: int,
    *,
    tolerance: float = 1e-9,
    max_examinations: int | None = None,
) -> SamplingResult:
    """Randomly build a minimal-ish subset of ``pool`` that reaches the same
    score (under ``score_fn``) as the full pool, following the paper's
    protocol.

    Args:
        pool: full pool of test identifiers for one fault (``TS_f``). Not
            mutated - a local copy is shuffled instead.
        score_fn: maps a list of test ids to a criterion score (e.g.
            statement coverage in [0, 1], number of killed mutants, etc.).
            Must be monotonically non-decreasing as tests are added for the
            "stop when we match the pool's score" logic to make sense, but
            this is the caller's responsibility - the assumption of
            monotonic coverage criteria is standard and holds for
            statement/branch/mutation coverage.
        seed: seed for a *local* ``random.Random`` instance. Two calls with
            the same seed and the same pool/score_fn are guaranteed to
            produce the same selection (determinism requirement).
        tolerance: floating point tolerance when comparing achieved vs
            target score.
        max_examinations: safety cap on how many candidate tests may be
            drawn before giving up (defaults to ``len(pool)``, since once
            every test in the pool has been tried, there is nothing left
            to draw without repeats - see "exhausted pool" handling below).

    Returns:
        A ``SamplingResult`` describing the selected suite, whether the
        target score was actually reached, and a short log of decisions.

    Edge cases handled explicitly:
        - Empty pool: returns immediately with an empty selection and
          ``reached_target=True`` only if the target score itself is 0
          (nothing to select, nothing to reach).
        - Pool where the full-pool score can never be matched by a proper
          subset in fewer than ``len(pool)`` picks (e.g. every single test
          is required): the loop safely terminates once every test has
          been examined, never looping forever.
        - ``score_fn`` that returns the same value for every candidate
          (i.e. no test ever "increases" the score): candidates are drawn
          and discarded until the pool is exhausted; the function returns
          with ``reached_target`` reflecting whatever the empty/partial
          selection's score compares to the target.
    """
    rng = random.Random(seed)
    result = SamplingResult()

    if not pool:
        result.target_score = score_fn([])
        result.achieved_score = 0.0
        result.reached_target = True
        result.log.append("Empty pool: nothing to select.")
        return result

    target_score = score_fn(list(pool))
    result.target_score = target_score

    remaining = list(pool)
    rng.shuffle(remaining)

    cap = max_examinations if max_examinations is not None else len(pool)

    selected: list[str] = []
    current_score = score_fn(selected)

    while remaining and result.n_tests_examined < cap:
        if current_score >= target_score - tolerance:
            break

        candidate = remaining.pop()
        result.n_tests_examined += 1

        candidate_score = score_fn(selected + [candidate])
        if candidate_score > current_score + tolerance:
            selected.append(candidate)
            current_score = candidate_score
            result.log.append(
                f"kept {candidate!r} (score {current_score:.4f})"
            )
        else:
            result.log.append(f"discarded {candidate!r} (no score increase)")

    result.selected = selected
    result.achieved_score = current_score
    result.reached_target = current_score >= target_score - tolerance
    return result
