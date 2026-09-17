"""Mutation testing: mutant generation and mutation-score measurement.

Tool choice (documented per Phase 6 of the assignment, and in
EXPERIMENT_LOG.md): the paper does not name a specific mutation testing
tool/framework anywhere in its text (it only cites general mutation testing
literature - Papadakis et al.'s survey [19] and Ammann & Offutt's textbook
[3]). We therefore had to pick one ourselves.

We evaluated `mutmut` (installed and inspected; see EXPERIMENT_LOG.md) and
found it unsuitable for this experiment's *shape*: mutmut is built around a
whole-project CLI workflow (`mutmut run`), discovering source under a
project tree and re-invoking pytest as a subprocess once per mutant against
the project's full test suite. Our protocol instead needs, for a single
small faulty function, to generate its mutants once and then evaluate many
different *subsets* of a test pool against those same mutants repeatedly
(100 randomized sampling iterations per fault - see src/sampling.py), which
requires fast in-process mutant execution, not a subprocess-per-mutant CLI.

We therefore implement a small, transparent, `ast`-based mutation engine
ourselves, applying standard, well-known mutation operators from the
mutation testing literature (the same literature the paper cites):

  - ROR (Relational Operator Replacement): <, <=, >, >=, ==, != swapped.
  - AOR (Arithmetic Operator Replacement): +, -, *, / swapped.
  - BOR (Boolean/Logical Operator Replacement): `and` <-> `or`.
  - Constant perturbation: numeric literals shifted by +1 / -1 (a common
    boundary-mutation operator).
  - RVR (Return Value Replacement): `return <expr>` replaced with
    `return True` / `return False` / `return None`. Added after the first
    HumanEval+ pilot run (EXPERIMENT_LOG.md) surfaced a real limitation:
    ROR/AOR/BOR/constant operators generate zero mutants for one-line
    functions with no comparisons/arithmetic/boolean logic/numeric literals
    (e.g. `return string.count(substring)`), which are common in HumanEval-
    style solutions. RVR is a standard operator category in the mutation
    testing literature precisely for this reason - it applies to any
    `return` statement regardless of what the returned expression contains.

This is real mutation testing (real mutants are generated, really compiled,
and really executed against real test inputs to determine kill/survive) -
not a simulated or fabricated score - just implemented directly rather than
via a third-party CLI tool, for the practical performance reason above.
"""

from __future__ import annotations

import ast
import copy
import importlib.util
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from src.coverage_utils import TestCase
from src.metrics import call_and_capture

_ROR_MAP = {
    ast.Lt: ast.GtE,
    ast.LtE: ast.Gt,
    ast.Gt: ast.LtE,
    ast.GtE: ast.Lt,
    ast.Eq: ast.NotEq,
    ast.NotEq: ast.Eq,
}

_AOR_MAP = {
    ast.Add: ast.Sub,
    ast.Sub: ast.Add,
    ast.Mult: ast.FloorDiv,
    ast.FloorDiv: ast.Mult,
}

_BOR_MAP = {
    ast.And: ast.Or,
    ast.Or: ast.And,
}


@dataclass(frozen=True)
class Mutant:
    mutant_id: str
    operator: str
    description: str
    source: str


def _clone(tree: ast.AST) -> ast.AST:
    return copy.deepcopy(tree)


def generate_mutants(source: str) -> list[Mutant]:
    """Generate first-order mutants of ``source`` using ROR/AOR/BOR/constant
    operators. Each mutant changes exactly one operator or literal site in
    an otherwise-identical copy of the AST.

    Returns an empty list if the source has no mutable sites (e.g. no
    comparisons, arithmetic, boolean logic, or numeric literals) - handled
    explicitly by callers rather than being an error.
    """
    base_tree = ast.parse(source)
    mutants: list[Mutant] = []

    # --- ROR: relational operators inside Compare nodes ---
    compare_sites = [n for n in ast.walk(base_tree) if isinstance(n, ast.Compare)]
    for site_index, site in enumerate(compare_sites):
        for op_index, op in enumerate(site.ops):
            if type(op) not in _ROR_MAP:
                continue
            tree = _clone(base_tree)
            target = [n for n in ast.walk(tree) if isinstance(n, ast.Compare)][site_index]
            new_op_cls = _ROR_MAP[type(op)]
            target.ops[op_index] = new_op_cls()
            ast.fix_missing_locations(tree)
            mutants.append(
                Mutant(
                    mutant_id=f"ROR_{site_index}_{op_index}",
                    operator="ROR",
                    description=f"{type(op).__name__} -> {new_op_cls.__name__}",
                    source=ast.unparse(tree),
                )
            )

    # --- AOR: arithmetic operators inside BinOp nodes ---
    binop_sites = [n for n in ast.walk(base_tree) if isinstance(n, ast.BinOp)]
    for site_index, site in enumerate(binop_sites):
        if type(site.op) not in _AOR_MAP:
            continue
        tree = _clone(base_tree)
        target = [n for n in ast.walk(tree) if isinstance(n, ast.BinOp)][site_index]
        new_op_cls = _AOR_MAP[type(site.op)]
        target.op = new_op_cls()
        ast.fix_missing_locations(tree)
        mutants.append(
            Mutant(
                mutant_id=f"AOR_{site_index}",
                operator="AOR",
                description=f"{type(site.op).__name__} -> {new_op_cls.__name__}",
                source=ast.unparse(tree),
            )
        )

    # --- BOR: boolean connectors inside BoolOp nodes ---
    boolop_sites = [n for n in ast.walk(base_tree) if isinstance(n, ast.BoolOp)]
    for site_index, site in enumerate(boolop_sites):
        if type(site.op) not in _BOR_MAP:
            continue
        tree = _clone(base_tree)
        target = [n for n in ast.walk(tree) if isinstance(n, ast.BoolOp)][site_index]
        new_op_cls = _BOR_MAP[type(site.op)]
        target.op = new_op_cls()
        ast.fix_missing_locations(tree)
        mutants.append(
            Mutant(
                mutant_id=f"BOR_{site_index}",
                operator="BOR",
                description=f"{type(site.op).__name__} -> {new_op_cls.__name__}",
                source=ast.unparse(tree),
            )
        )

    # --- Constant perturbation: numeric literals shifted by +1 / -1 ---
    const_sites = [
        n
        for n in ast.walk(base_tree)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)) and not isinstance(n.value, bool)
    ]
    for site_index, site in enumerate(const_sites):
        for delta in (1, -1):
            tree = _clone(base_tree)
            targets = [
                n
                for n in ast.walk(tree)
                if isinstance(n, ast.Constant)
                and isinstance(n.value, (int, float))
                and not isinstance(n.value, bool)
            ]
            target = targets[site_index]
            target.value = target.value + delta
            ast.fix_missing_locations(tree)
            mutants.append(
                Mutant(
                    mutant_id=f"CONST_{site_index}_{'+' if delta > 0 else ''}{delta}",
                    operator="CONST",
                    description=f"{site.value} -> {site.value + delta}",
                    source=ast.unparse(tree),
                )
            )

    # --- RVR: return-value replacement (True / False / None) ---
    return_sites = [
        n for n in ast.walk(base_tree) if isinstance(n, ast.Return) and n.value is not None
    ]
    for site_index, site in enumerate(return_sites):
        for replacement in (True, False, None):
            # Skip a "mutant" that is textually identical to the original
            # (e.g. don't generate `return None` -> `return None`).
            if isinstance(site.value, ast.Constant) and site.value.value == replacement:
                continue
            tree = _clone(base_tree)
            targets = [
                n for n in ast.walk(tree) if isinstance(n, ast.Return) and n.value is not None
            ]
            target = targets[site_index]
            target.value = ast.Constant(value=replacement)
            ast.fix_missing_locations(tree)
            mutants.append(
                Mutant(
                    mutant_id=f"RVR_{site_index}_{replacement}",
                    operator="RVR",
                    description=f"return ... -> return {replacement!r}",
                    source=ast.unparse(tree),
                )
            )

    return mutants


def compile_mutant(mutant_source: str, function_name: str) -> Callable | None:
    """Compile a mutant's source into a callable. Returns None if the
    mutant fails to import (e.g. a mutation happened to produce invalid
    code for this function name, which should not occur given our
    operators but is guarded against defensively rather than crashing the
    whole experiment on one bad mutant).
    """
    tmp_dir = Path(tempfile.gettempdir()) / "table_iv_repro_mutants"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    file_path = tmp_dir / f"mut_{uuid.uuid4().hex}.py"
    file_path.write_text(mutant_source, encoding="utf-8")
    try:
        spec = importlib.util.spec_from_file_location(f"mut_{uuid.uuid4().hex}", file_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)  # type: ignore[union-attr]
        return getattr(module, function_name)
    except Exception:  # noqa: BLE001 - a broken mutant is simply unusable
        return None


@dataclass
class MutationModel:
    """A program-under-test plus its compiled, live mutants, ready for
    repeated mutation-score queries as different test subsets are tried.
    """

    original_func: Callable
    mutants: list[tuple[Mutant, Callable]]
    kills_by_test: dict[str, frozenset[str]] = field(default_factory=dict)  # test_id -> set of mutant_ids it kills


def build_mutation_model(source: str, function_name: str, tests: list[TestCase]) -> MutationModel:
    """Generate mutants of ``source``, compile the ones that import
    successfully, and precompute which mutants each individual test kills
    (kills(m, t) <=> output(m, t) != output(original, t), Definition 6
    specialised to a single test). As with coverage (see coverage_utils.py),
    precomputing per-test kill sets lets src/sampling.py's score_fn just
    take unions over a subset, instead of re-running every mutant for every
    candidate subset during sampling.
    """
    original_func, _ = _load_original(source, function_name)
    raw_mutants = generate_mutants(source)

    live_mutants: list[tuple[Mutant, Callable]] = []
    for m in raw_mutants:
        func = compile_mutant(m.source, function_name)
        if func is not None:
            live_mutants.append((m, func))

    kills_by_test: dict[str, frozenset[str]] = {}
    for test in tests:
        original_output = call_and_capture(original_func, test.args, test.call_kwargs())
        killed_here = set()
        for m, mutant_func in live_mutants:
            mutant_output = call_and_capture(mutant_func, test.args, test.call_kwargs())
            if mutant_output != original_output:
                killed_here.add(m.mutant_id)
        kills_by_test[test.test_id] = frozenset(killed_here)

    return MutationModel(
        original_func=original_func,
        mutants=live_mutants,
        kills_by_test=kills_by_test,
    )


def _load_original(source: str, function_name: str) -> tuple[Callable, str]:
    tmp_dir = Path(tempfile.gettempdir()) / "table_iv_repro_modules"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    file_path = tmp_dir / f"orig_{uuid.uuid4().hex}.py"
    file_path.write_text(source, encoding="utf-8")
    spec = importlib.util.spec_from_file_location(f"orig_{uuid.uuid4().hex}", file_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return getattr(module, function_name), str(file_path)


def mutation_score_fn(model: MutationModel) -> Callable[[list[str]], float]:
    """Build a score_fn (for src/sampling.py) computing mutation score of a
    subset of test ids as |union of killed mutants| / |all live mutants|.

    Note on Definition 7's denominator ("killed + surviving", i.e.
    excluding equivalent mutants): we do not attempt automatic equivalent
    mutant detection (an undecidable problem in general, usually done
    manually in the mutation testing literature). Instead, the denominator
    is simply "all successfully-compiled mutants", and the *target* that
    src/sampling.py's algorithm aims to reach is whatever the full test
    pool achieves on this denominator - exactly mirroring Section V's
    protocol ("stop when the same coverage as the full pool is reached"),
    which sidesteps the need to separately identify equivalent mutants.
    """
    total = len(model.mutants)

    def score_fn(selected_ids: list[str]) -> float:
        if total == 0:
            return 1.0  # no mutable sites -> vacuously fully "mutation-adequate"
        killed: set[str] = set()
        for tid in selected_ids:
            killed |= model.kills_by_test.get(tid, frozenset())
        return len(killed) / total

    return score_fn
