from __future__ import annotations

import ast
import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_FEATURE = _ROOT / "tests/features/character_update_live.feature"
_BINDER = _ROOT / "tests/e2e/test_character_update_live_bdd.py"
_STEP_LINE = re.compile(r"^\s*(?:Given|When|Then|And)\s+(.+?)\s*$")


def _feature_steps() -> set[str]:
    steps = set()
    for line in _FEATURE.read_text(encoding="utf-8").splitlines():
        match = _STEP_LINE.match(line)
        if match:
            steps.add(" ".join(match.group(1).split()))
    return steps


def _bound_steps() -> set[str]:
    tree = ast.parse(_BINDER.read_text(encoding="utf-8"))
    steps = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call) or not isinstance(decorator.func, ast.Name):
                continue
            if decorator.func.id not in {"given", "when", "then"} or not decorator.args:
                continue
            value = ast.literal_eval(decorator.args[0])
            if isinstance(value, str):
                steps.add(" ".join(value.split()))
    return steps


def test_character_update_feature_steps_match_bdd_bindings_exactly() -> None:
    feature_steps = _feature_steps()
    bound_steps = _bound_steps()

    assert feature_steps == bound_steps, (
        f"unbound feature steps: {sorted(feature_steps - bound_steps)}; "
        f"unused bindings: {sorted(bound_steps - feature_steps)}"
    )
