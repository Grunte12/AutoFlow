"""Credit-free live readback check for Character personality via CLI and MCP."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import pytest
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from pytest_bdd import given, scenarios, then, when

scenarios("../features/character_readback_live.feature")

_RUN_ENV = "GFLOW_CLI_E2E_RUN_CHARACTER_READBACK"
_PROJECT_ENV = "GFLOW_CLI_E2E_CHARACTER_READBACK_PROJECT"
_ENTITY_ENV = "GFLOW_CLI_E2E_CHARACTER_READBACK_ENTITY"
_PERSONALITY_SHA_ENV = "GFLOW_CLI_E2E_CHARACTER_READBACK_PERSONALITY_SHA256"
_TIMEOUT_S = 300


def _required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        pytest.skip(f"set {name} to run the Character readback E2E")
    return value


def _run_cli(world: dict[str, Any]) -> dict[str, Any]:
    command = [
        sys.executable,
        "-m",
        "gflow_cli",
        "character",
        "show",
        "--project",
        world["project"],
        "--id",
        world["entity"],
        "--profile",
        world["profile"],
        "--json",
    ]
    with tempfile.TemporaryDirectory(prefix="gflow-character-readback-e2e-") as directory:
        stdout_path = Path(directory) / "stdout.txt"
        stderr_path = Path(directory) / "stderr.txt"
        with (
            stdout_path.open("w", encoding="utf-8") as stdout,
            stderr_path.open("w", encoding="utf-8") as stderr,
        ):
            process = subprocess.Popen(command, env=world["env"], stdout=stdout, stderr=stderr)  # noqa: S603
            try:
                process.wait(timeout=_TIMEOUT_S)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=30)
                pytest.fail("CLI Character readback timed out")
        raw = stdout_path.read_text(encoding="utf-8", errors="replace")
    if process.returncode != 0:
        # Do not surface stdout/stderr: either may contain private Character data.
        pytest.fail(f"CLI Character readback exited {process.returncode}")
    try:
        payload = json.loads(raw.strip())
    except json.JSONDecodeError as exc:
        raise AssertionError("CLI Character readback did not return JSON") from exc
    assert isinstance(payload, dict) and payload.get("status") == "ok"
    return payload


async def _read_mcp(world: dict[str, Any]) -> dict[str, Any]:
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "gflow_cli", "mcp", "run", "--profile", world["profile"], "--no-spend"],
        env=world["env"],
    )
    async with stdio_client(parameters) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.call_tool(
                "gflow_character_show",
                {
                    "project": world["project"],
                    "entity_id": world["entity"],
                    "profile": world["profile"],
                },
            )
    is_error = getattr(result, "is_error", getattr(result, "isError", False))
    assert is_error is not True, "MCP Character readback returned an error"
    structured = getattr(result, "structured_content", None)
    if isinstance(structured, dict):
        payload = structured
    else:
        texts = [
            block.text
            for block in getattr(result, "content", [])
            if isinstance(getattr(block, "text", None), str)
        ]
        assert texts, "MCP Character readback returned no result"
        try:
            payload = json.loads(texts[0])
        except json.JSONDecodeError as exc:
            raise AssertionError("MCP Character readback did not return JSON") from exc
    assert isinstance(payload, dict) and payload.get("status") == "ok"
    return payload


def _read_state(
    payload: dict[str, Any], world: dict[str, Any]
) -> tuple[str, str, tuple[str, ...], str]:
    character = payload.get("character")
    assert isinstance(character, dict)
    entity_id = character.get("entity_id")
    project_id = character.get("project_id")
    workflows = character.get("workflow_ids")
    personality = character.get("personality")
    if entity_id != world["entity"]:
        pytest.fail("readback returned a different entity", pytrace=False)
    if project_id != world["project"]:
        pytest.fail("readback returned a different project", pytrace=False)
    assert isinstance(workflows, list) and all(isinstance(item, str) and item for item in workflows)
    assert isinstance(personality, str), "Character personality is missing or not text"
    return (
        entity_id,
        project_id,
        tuple(workflows),
        hashlib.sha256(personality.encode("utf-8")).hexdigest(),
    )


@given("an opted-in existing Character and expected personality digest", target_fixture="world")
def _prepare_world(e2e_env: dict[str, str], e2e_profile_dir: Path) -> dict[str, Any]:
    if os.environ.get(_RUN_ENV, "0").strip() != "1":
        pytest.skip(f"set {_RUN_ENV}=1 to run the read-only Character CLI/MCP check")
    project = _required_env(_PROJECT_ENV)
    entity = _required_env(_ENTITY_ENV)
    expected_sha = _required_env(_PERSONALITY_SHA_ENV).lower()
    if len(expected_sha) != 64 or any(char not in "0123456789abcdef" for char in expected_sha):
        pytest.fail(f"{_PERSONALITY_SHA_ENV} must be a SHA-256 hex digest", pytrace=False)
    env = dict(e2e_env)
    env.update(
        GFLOW_CLI_PROFILE=os.environ["GFLOW_CLI_E2E_PROFILE"].strip(),
        GFLOW_CLI_HEADLESS="false",
        GFLOW_CLI_BACKGROUND="0",
        GFLOW_CLI_LEASE_WAIT_SECONDS="0",
        GFLOW_CLI_FLOW_HOST="flow.google.com",
        GFLOW_MCP_NO_SPEND="1",
    )
    return {
        "env": env,
        "profile": env["GFLOW_CLI_PROFILE"],
        "profile_dir": e2e_profile_dir,
        "project": project,
        "entity": entity,
        "expected_sha": expected_sha,
    }


@when("the CLI reads the Character")
def _cli_reads(world: dict[str, Any]) -> None:
    world["cli"] = _run_cli(world)


@then("its identity and personality digest match the operator's expected state")
def _cli_read_matches(world: dict[str, Any]) -> None:
    state = _read_state(world["cli"], world)
    assert state[3] == world["expected_sha"], "CLI personality digest differs from expected value"
    world["cli_state"] = state


@when("native MCP stdio reads the same Character")
def _mcp_reads(world: dict[str, Any]) -> None:
    world["mcp"] = asyncio.run(_read_mcp(world))


@then("MCP identity and personality digest match the CLI read")
def _mcp_read_matches(world: dict[str, Any]) -> None:
    mcp_state = _read_state(world["mcp"], world)
    if mcp_state != world["cli_state"]:
        pytest.fail(
            "MCP readback differs from the CLI entity/workflow/personality state", pytrace=False
        )
