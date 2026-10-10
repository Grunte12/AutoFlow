"""Opt-in BDD wrapper and offline contract tests for the no-credit parity probe."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from pytest_bdd import given, scenarios, then, when

scenarios("../features/character_picker_parity.feature")

_RUN = "GFLOW_CLI_E2E_RUN_CHARACTER_PICKER_PARITY"
_INPUT = "GFLOW_CLI_E2E_CHARACTER_PICKER_PARITY_INPUT"
_PROFILE = "GFLOW_CLI_E2E_PROFILE"
_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _ROOT / "scripts/dev/character_picker_parity.py"


@given(
    "an opted-in migrated project with existing media and saved Characters",
    target_fixture="parity_world",
)
def _configured_world() -> dict[str, Any]:
    if os.environ.get(_RUN) != "1":
        pytest.skip(f"set {_RUN}=1 to run the authenticated, no-generation browser probe")
    input_path = Path(os.environ.get(_INPUT, "")).expanduser().resolve()
    if not input_path.is_file() or input_path.is_symlink():
        pytest.fail(f"set {_INPUT} to an existing regular JSON file", pytrace=False)
    if not os.environ.get(_PROFILE, "").strip():
        pytest.skip(f"set {_PROFILE} to an authenticated migrated profile")
    return {"input": input_path, "profile": os.environ[_PROFILE].strip()}


@when("the native picker and production composer inputs are captured with submit blocked")
def _run_probe(parity_world: dict[str, Any], e2e_env: dict[str, str]) -> None:
    env = dict(e2e_env)
    env.update(
        GFLOW_CLI_FLOW_HOST="flow.google.com",
        GFLOW_CLI_LEASE_WAIT_SECONDS="0",
        GFLOW_CLI_BACKGROUND="0",
    )
    command = [
        sys.executable,
        str(_SCRIPT),
        "--input",
        str(parity_world["input"]),
        "--profile",
        parity_world["profile"],
    ]
    result = subprocess.run(
        command, cwd=_ROOT, env=env, capture_output=True, text=True, timeout=240, check=False
    )
    safe_output = "\n".join(
        line
        for stream in (result.stdout, result.stderr)
        for line in stream.splitlines()
        if line.startswith(("SAFE_", "SAFE"))
    )
    if result.returncode:
        detail = (
            f"parity probe failed with exit {result.returncode}; "
            f"safe output:\n{safe_output or '<none>'}"
        )
        pytest.fail(
            detail,
            pytrace=False,
        )
    markers = [
        line for line in result.stdout.splitlines() if line.startswith("SAFE_NATIVE_PARITY ")
    ]
    assert len(markers) == 1, "probe must emit exactly one safe parity marker"
    parity_world["report"] = json.loads(markers[0].removeprefix("SAFE_NATIVE_PARITY "))
    print(markers[0], flush=True)


@then("ordered reference bindings match and backend image consumption remains unproved")
def _assert_serialization_only(parity_world: dict[str, Any]) -> None:
    report = parity_world["report"]
    assert report["generation_dispatched"] == report["mutation_dispatched"] == 0
    assert len(report["arms"]) == 3
    assert report["generation_spec_comparison"]["all_nonvarying_fields_equal"]
    for arm in report["arms"]:
        assert all(arm["equal_to_inputs"].values())
        assert "settings_ui_readback" in arm
        assert "generation_spec" in arm
    assert all(report["arm_parity"].values())
    assert report["server_media_ids_unchanged"] is True
    assert report["client_serialization_only"] is True
    assert report["backend_image_consumption_proved"] is False
