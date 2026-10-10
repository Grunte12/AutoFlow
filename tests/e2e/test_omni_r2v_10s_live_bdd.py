"""Opt-in real MCP/browser wire capture for mixed-reference Omni R2V, no generation."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import re
import sys
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from pytest_bdd import given, scenarios, then, when

from gflow_cli.api.video import is_media_uuid
from gflow_cli.config import reset_settings

scenarios("../features/omni_r2v_10s_live.feature")

_ROOT = Path(__file__).resolve().parents[2]
_REQUEST_ENV = "AUTOFLOW_E2E_OMNI10_REQUEST_JSON"
_INPUTS_ENV = "AUTOFLOW_E2E_OMNI10_INPUTS_DIR"
_RUN_ENV = "AUTOFLOW_E2E_RUN_OMNI10"
_FILE_ID = re.compile(r"^[a-f0-9]{32}$")


def _canonical_uuid(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        return str(UUID(value)) == value
    except ValueError:
        return False


def _load_capture_helper() -> Any:
    path = _ROOT / "scripts" / "dev" / "capture_omni_r2v_mcp.py"
    spec = importlib.util.spec_from_file_location("capture_omni_r2v_mcp", path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"could not load registered MCP capture helper: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@given(
    "an opt-in private Omni R2V request with two Characters and two images",
    target_fixture="prepared",
)
def prepare_request(
    e2e_profile_dir: Path,
    e2e_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, Any]:
    if os.environ.get(_RUN_ENV) != "1":
        pytest.skip(f"Set {_RUN_ENV}=1 after preparing the private request and inputs")

    request_file = Path(os.environ.get(_REQUEST_ENV, ""))
    inputs_dir = Path(os.environ.get(_INPUTS_ENV, ""))
    if not request_file.is_absolute() or not request_file.is_file():
        pytest.fail(f"{_REQUEST_ENV} must name an existing absolute private JSON file")
    if not inputs_dir.is_absolute() or not inputs_dir.is_dir():
        pytest.fail(f"{_INPUTS_ENV} must name an existing absolute private inputs directory")

    document = json.loads(request_file.read_text(encoding="utf-8"))
    arguments = document.get("arguments") if isinstance(document, dict) else None
    if not isinstance(arguments, dict):
        pytest.fail("private request JSON must contain an arguments object")
    arguments = dict(arguments)

    file_ids = arguments.pop("reference_file_ids", None)
    entity_ids = arguments.get("reference_entities")
    entity_names = arguments.get("reference_entity_names")
    if (
        not isinstance(file_ids, list)
        or len(file_ids) != 2
        or len(set(file_ids)) != 2
        or not all(isinstance(value, str) and _FILE_ID.fullmatch(value) for value in file_ids)
    ):
        pytest.fail("private request must carry exactly two unique 32-hex reference_file_ids")
    if (
        not isinstance(entity_ids, list)
        or len(entity_ids) != 2
        or not all(_canonical_uuid(value) for value in entity_ids)
        or not isinstance(entity_names, list)
        or len(entity_names) != 2
        or not all(isinstance(value, str) and value.strip() for value in entity_names)
    ):
        pytest.fail("private request must carry two canonical Character UUIDs and paired names")
    if (
        arguments.get("mode") != "r2v"
        or arguments.get("model") != "omni_flash"
        or arguments.get("duration") != 10
        or arguments.get("count") != 1
        or not is_media_uuid(arguments.get("project"))
        or not isinstance(arguments.get("prompt"), str)
        or not arguments["prompt"].strip()
    ):
        pytest.fail("private request must be r2v, omni_flash, 10s, count=1 with project and prompt")

    images = [inputs_dir / f"{file_id}.png" for file_id in file_ids]
    if not all(path.is_absolute() and path.is_file() and not path.is_symlink() for path in images):
        pytest.fail("each private reference file must exist as a regular non-symlink {file_id}.png")
    arguments["reference_images"] = [str(path.resolve()) for path in images]
    arguments["profile"] = e2e_env["GFLOW_CLI_PROFILE"]
    arguments["wait"] = True

    # Reuse the E2E fixture's isolated database/output paths while preserving the
    # explicitly selected authenticated home/profile. The real MCP tool runs in this process.
    for key in ("GFLOW_CLI_DB_PATH", "GFLOW_CLI_OUTPUT_DIR", "GFLOW_CLI_PROFILE"):
        monkeypatch.setenv(key, e2e_env[key])
    monkeypatch.setenv("GFLOW_CLI_FLOW_HOST", "flow.google.com")
    monkeypatch.setenv("GFLOW_CLI_HEADLESS", "false")
    monkeypatch.setenv("GFLOW_CLI_LEASE_WAIT_SECONDS", "0")
    reset_settings()

    return {
        "arguments": arguments,
        "entity_ids": list(entity_ids),
        "file_ids": file_ids,
        "profile_dir": str(e2e_profile_dir),
    }


@when(
    "the native MCP handler captures its submit with generation blocked",
    target_fixture="capture",
)
def capture(prepared: dict[str, Any]) -> dict[str, Any]:
    helper = _load_capture_helper()
    return asyncio.run(helper.capture(prepared["arguments"], probe_unverified=False))


@then("exactly one Omni R2V 10s submit is captured without dispatch")
def exact_capture(capture: dict[str, Any]) -> None:
    assert capture["capture_count"] == 1
    assert capture["generation_dispatched"] == 0
    assert capture["rpcid"] == "MZZa6b"
    assert capture["model_key"] == "abra_r2v_10s"
    assert capture["count"] == 1
    assert capture["settings_verified"] == {
        "model": "omni_flash",
        "duration": 10,
        "aspect": "portrait",
        "resolution": "720p",
        "count": 1,
    }


@then("both Character and media bindings and the prompt are verified")
def bindings(capture: dict[str, Any], prepared: dict[str, Any]) -> None:
    assert capture["entity_ids"] == prepared["entity_ids"]
    assert len(capture["entity_ids"]) == 2
    assert len(capture["media_ids"]) == 2
    assert capture["prompt_verified"] is True
    assert capture["bindings_verified"] is True
