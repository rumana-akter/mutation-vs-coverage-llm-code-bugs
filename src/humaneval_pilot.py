"""Helpers specific to the HumanEval+ pilot (Phase 8): parsing Claude-
generated candidate implementations and test pools, and classifying which
candidates are "faulty" relative to the real HumanEval reference solution.

Kept separate from src/fault_runner.py (which is benchmark-agnostic) so the
generic pipeline stays reusable, while HumanEval-specific parsing lives here.
"""

from __future__ import annotations

import importlib.util
import json
import re
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from src.fault_runner import FaultSpec, OracleTestCase, build_outcomes
from src.metrics import fault_difficulty

_IMPL_MARKER_RE = re.compile(r"###\s*IMPLEMENTATION\s+(\d+)\s*###", re.IGNORECASE)


def parse_candidates(raw_text: str) -> list[str]:
    """Split a subagent's raw output on '### IMPLEMENTATION i ###' markers,
    returning a list of Python source strings, one per candidate.
    """
    parts = _IMPL_MARKER_RE.split(raw_text)
    # re.split with a capturing group returns: [pre, num1, code1, num2, code2, ...]
    candidates = [parts[i].strip() for i in range(2, len(parts), 2)]
    return [c for c in candidates if c]


def _strip_json_fences(raw_text: str) -> str:
    text = raw_text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n", "", text)
        text = re.sub(r"\n```$", "", text)
    return text.strip()


def parse_test_pool(raw_json_text: str, test_id_prefix: str) -> list[OracleTestCase]:
    """Parse a JSON array of {"args": [...], "expected_output": ...} objects
    into OracleTestCase instances.

    ``expected_output`` is stored exactly as JSON decoded it (e.g. a Python
    ``list`` for a JSON array), with no type coercion here. JSON has no
    tuple type, so a generated oracle's expected value might need to be
    compared against a function that natively returns a ``list`` (e.g.
    ``count_up_to``) or one that natively returns a ``tuple`` (e.g.
    ``sum_product``) - normalizing only at *this* parsing step previously
    caused a real bug (see AUDIT.md): converting every JSON array to a
    tuple here made the oracle check vacuous for any list-returning
    function, since a Python ``list`` is never ``==`` to a ``tuple``
    regardless of contents. The fix is to apply the same normalization to
    every value on both sides of a comparison, together, at comparison
    time - see ``src.metrics.normalize_for_comparison`` and
    ``src.fault_runner.build_outcomes``, not here.
    """
    text = _strip_json_fences(raw_json_text)
    data = json.loads(text)
    tests = []
    for i, entry in enumerate(data):
        tests.append(
            OracleTestCase(
                test_id=f"{test_id_prefix}_{i}",
                args=tuple(entry["args"]),
                kwargs=None,
                expected_output=entry["expected_output"],
            )
        )
    return tests


def load_callable(source: str, function_name: str) -> Callable:
    tmp_dir = Path(tempfile.gettempdir()) / "table_iv_repro_modules"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    file_path = tmp_dir / f"pilot_{uuid.uuid4().hex}.py"
    file_path.write_text(source, encoding="utf-8")
    spec = importlib.util.spec_from_file_location(f"pilot_{uuid.uuid4().hex}", file_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return getattr(module, function_name)


@dataclass
class CandidateReport:
    candidate_index: int
    source: str
    is_faulty: bool
    difficulty: float
    n_triggering_tests: int
    n_pool_tests: int


def classify_candidates(
    task_id: str,
    entry_point: str,
    reference_source: str,
    candidate_sources: list[str],
    tests: list[OracleTestCase],
) -> list[CandidateReport]:
    """For each candidate, determine (against the real reference
    implementation) whether it is faulty on this test pool, and its
    difficulty (Definition 5) if so.

    A candidate that fails to even compile/import (e.g. malformed code) is
    reported as such rather than silently skipped, since that is itself a
    meaningful, documentable outcome for a "vibe coding" experiment.
    """
    reference_func = load_callable(reference_source, entry_point)
    reports = []
    for idx, source in enumerate(candidate_sources):
        try:
            candidate_func = load_callable(source, entry_point)
        except Exception as exc:  # noqa: BLE001
            reports.append(
                CandidateReport(
                    candidate_index=idx,
                    source=source,
                    is_faulty=True,  # a candidate that crashes to import is trivially "faulty"
                    difficulty=0.0,  # trivial: it fails on every test (import error)
                    n_triggering_tests=len(tests),
                    n_pool_tests=len(tests),
                )
            )
            continue

        fault_spec = FaultSpec(
            fault_id=f"{task_id}_candidate_{idx}",
            faulty_source=source,
            function_name=entry_point,
            reference_func=reference_func,
            tests=tests,
        )
        outcomes = build_outcomes(fault_spec, candidate_func)
        difficulty = fault_difficulty(list(outcomes.values()))
        n_triggering = sum(1 for o in outcomes.values() if o.triggered)
        is_faulty = n_triggering > 0

        reports.append(
            CandidateReport(
                candidate_index=idx,
                source=source,
                is_faulty=is_faulty,
                difficulty=difficulty if is_faulty else 1.0,  # non-faulty: difficulty undefined, report 1.0 (never triggers)
                n_triggering_tests=n_triggering,
                n_pool_tests=len(tests),
            )
        )
    return reports
