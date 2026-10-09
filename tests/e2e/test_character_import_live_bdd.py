"""Opt-in live proof for native Character-sheet import via CLI and MCP stdio.

The test creates two uniquely named verification Characters, one through each
surface, from an operator-supplied local image. It never edits canonical
characters or invokes a generation command. Replays use the same operation UUID
from fresh CLI/MCP processes and must preserve the exact journal and bindings.

There is no upload counter on the current public surfaces. Stable entity and
workflow/media bindings plus an unchanged operation journal are the observable
replay proof; the MCP server also runs in no-spend mode with generation tools
unregistered.

Run only when explicitly opted in:

    GFLOW_CLI_E2E_RUN_CHARACTER_IMPORT=1 \\
    GFLOW_CLI_E2E_PROFILE=<profile> \\
    GFLOW_CLI_E2E_CHARACTER_IMPORT_PROJECT=<project-uuid> \\
    GFLOW_CLI_E2E_CHARACTER_IMPORT_SHEET=/absolute/path/to/sheet.png \\
    uv run pytest -m e2e_character tests/e2e/test_character_import_live_bdd.py -v

The final single-Character cross-surface scenario uses
``GFLOW_CLI_E2E_RUN_CHARACTER_IMPORT_FINAL=1`` and can be selected by its BDD node id.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import pytest
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from pytest_bdd import given, scenarios, then, when

from gflow_cli.api.client import FlowApiClient

scenarios("../features/character_import_live.feature")

_RUN_ENV = "GFLOW_CLI_E2E_RUN_CHARACTER_IMPORT"
_FINAL_RUN_ENV = "GFLOW_CLI_E2E_RUN_CHARACTER_IMPORT_FINAL"
_PROJECT_ENV = "GFLOW_CLI_E2E_CHARACTER_IMPORT_PROJECT"
_SHEET_ENV = "GFLOW_CLI_E2E_CHARACTER_IMPORT_SHEET"
_IMPORT_TIMEOUT_S = 300


def _required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        pytest.skip(f"set {name} to run the native Character import E2E")
    return value


def _run_gflow(
    args: list[str], *, env: dict[str, str], timeout: float
) -> subprocess.CompletedProcess[str]:
    """Run the real CLI without pipe-drain hangs from browser grandchildren."""
    command = [sys.executable, "-m", "gflow_cli", *args]
    with tempfile.TemporaryDirectory(prefix="gflow-character-import-e2e-") as directory:
        stdout_path = Path(directory) / "stdout.txt"
        stderr_path = Path(directory) / "stderr.txt"
        with (
            stdout_path.open("w", encoding="utf-8") as stdout_file,
            stderr_path.open("w", encoding="utf-8") as stderr_file,
        ):
            process = subprocess.Popen(  # noqa: S603
                command,
                env=env,
                stdout=stdout_file,
                stderr=stderr_file,
            )
            timed_out = False
            try:
                process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                process.kill()
                process.wait(timeout=30)
        stdout = stdout_path.read_text(encoding="utf-8", errors="replace")
        stderr = stderr_path.read_text(encoding="utf-8", errors="replace")

    if timed_out:
        pytest.fail(f"CLI import command timed out after {timeout:g}s")
    return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)


def _cli_payload(result: subprocess.CompletedProcess[str], label: str) -> dict[str, Any]:
    if result.returncode != 0:
        # Keep the specific structured failure in the private receipt, not a
        # truncated CompletedProcess repr containing arbitrary stderr logs.
        try:
            problem = json.loads(result.stdout.strip())
        except json.JSONDecodeError:
            problem = {}
        if isinstance(problem, dict) and isinstance(problem.get("error"), dict):
            problem = problem["error"]
        detail = (
            problem.get("detail", "no structured detail")
            if isinstance(problem, dict)
            else "no structured detail"
        )
        pytest.fail(f"{label} exited {result.returncode}: {str(detail)[:400]}")
    try:
        payload = json.loads(result.stdout.strip())
    except json.JSONDecodeError as exc:
        raise AssertionError(f"{label} did not return its JSON result") from exc
    assert isinstance(payload, dict)
    assert payload.get("status") == "ok", f"{label} did not succeed"
    return payload


def _mcp_payload(result: Any, label: str) -> dict[str, Any]:
    is_error = getattr(result, "is_error", getattr(result, "isError", False))
    assert is_error is not True, f"{label} returned an MCP error"
    structured = getattr(result, "structured_content", None)
    if isinstance(structured, dict):
        payload = structured
    else:
        texts = [
            text
            for block in getattr(result, "content", [])
            if isinstance((text := getattr(block, "text", None)), str)
        ]
        assert texts, f"{label} returned no structured result"
        try:
            payload = json.loads(texts[0])
        except json.JSONDecodeError as exc:
            raise AssertionError(f"{label} returned no JSON result") from exc
    assert isinstance(payload, dict)
    assert payload.get("status") == "ok", f"{label} did not succeed"
    return payload


def _identity(
    payload: dict[str, Any],
) -> tuple[str, str, tuple[str, ...], tuple[tuple[str, str], ...]]:
    character = payload.get("character")
    assert isinstance(character, dict)
    entity_id = character.get("entity_id")
    project_id = character.get("project_id")
    workflow_ids = character.get("workflow_ids")
    bindings = payload.get("workflow_media_bindings")
    assert isinstance(entity_id, str) and entity_id
    assert isinstance(project_id, str) and project_id
    assert isinstance(workflow_ids, list) and workflow_ids
    assert all(isinstance(workflow, str) and workflow for workflow in workflow_ids)
    assert isinstance(bindings, list) and bindings
    pairs: list[tuple[str, str]] = []
    for binding in bindings:
        assert isinstance(binding, dict)
        workflow_id = binding.get("workflow_id")
        media_id = binding.get("media_id")
        assert isinstance(workflow_id, str) and workflow_id
        assert isinstance(media_id, str) and media_id
        pairs.append((workflow_id, media_id))
    return entity_id, project_id, tuple(workflow_ids), tuple(pairs)


def _operation_snapshot(env: dict[str, str], operation_id: str) -> tuple[str, str, str, str]:
    with sqlite3.connect(env["GFLOW_CLI_DB_PATH"]) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            "SELECT command, mode, status, metadata_json FROM operations WHERE id = ?",
            (operation_id,),
        ).fetchall()
    assert len(rows) == 1, "expected one durable operation row for this idempotency key"
    row = rows[0]
    assert row["command"] == "character import"
    assert row["mode"] == "character"
    return row["command"], row["mode"], row["status"], row["metadata_json"]


def _operation_rows(env: dict[str, str]) -> list[tuple[str, str, str]]:
    with sqlite3.connect(env["GFLOW_CLI_DB_PATH"]) as connection:
        rows = connection.execute("SELECT id, command, mode FROM operations").fetchall()
    return [(str(row[0]), str(row[1]), str(row[2])) for row in rows]


def _build_import_world(e2e_env: dict[str, str], e2e_profile_dir: Path) -> dict[str, Any]:
    project_id = _required_env(_PROJECT_ENV)
    try:
        canonical_project_id = str(uuid.UUID(project_id))
    except ValueError as exc:
        pytest.fail(f"{_PROJECT_ENV} must be a canonical UUID", pytrace=False)
        raise AssertionError from exc
    if canonical_project_id != project_id:
        pytest.fail(f"{_PROJECT_ENV} must be a canonical UUID", pytrace=False)

    sheet_value = _required_env(_SHEET_ENV)
    sheet = Path(sheet_value).expanduser()
    if not sheet.is_file():
        pytest.fail(f"{_SHEET_ENV} must point to a local image file", pytrace=False)

    env = dict(e2e_env)
    env["GFLOW_CLI_PROFILE"] = os.environ["GFLOW_CLI_E2E_PROFILE"].strip()
    env["GFLOW_CLI_HEADLESS"] = "1"
    env["GFLOW_CLI_FLOW_HOST"] = "flow.google.com"
    env["GFLOW_MCP_NO_SPEND"] = "1"
    return {
        "env": env,
        "profile": env["GFLOW_CLI_PROFILE"],
        "profile_dir": e2e_profile_dir,
        "project_id": project_id,
        "sheet": sheet.resolve(),
    }


@given("an opted-in Flow profile, project, and source image", target_fixture="world")
def _prepare_import_world(e2e_env: dict[str, str], e2e_profile_dir: Path) -> dict[str, Any]:
    if os.environ.get(_RUN_ENV, "0").strip() != "1":
        pytest.skip(f"set {_RUN_ENV}=1 to create the CLI and MCP verification Characters")
    return _build_import_world(e2e_env, e2e_profile_dir)


@given("the final opted-in Flow profile, project, and source image", target_fixture="world")
def _prepare_final_import_world(e2e_env: dict[str, str], e2e_profile_dir: Path) -> dict[str, Any]:
    if os.environ.get(_FINAL_RUN_ENV, "0").strip() != "1":
        pytest.skip(f"set {_FINAL_RUN_ENV}=1 to create the one final verification Character")
    return _build_import_world(e2e_env, e2e_profile_dir)


def _start_character(surface: str) -> dict[str, str]:
    suffix = uuid.uuid4().hex[:10]
    return {
        "name": f"e2e-import-{surface}-{suffix}",
        "personality": f"verification personality {suffix}",
        "operation_id": str(uuid.uuid4()),
    }


def _cli_import(world: dict[str, Any], request: dict[str, str]) -> dict[str, Any]:
    result = _run_gflow(
        [
            "character",
            "import",
            "--project",
            world["project_id"],
            "--name",
            request["name"],
            "--sheet",
            str(world["sheet"]),
            "--operation-id",
            request["operation_id"],
            "--personality",
            request["personality"],
            "--profile",
            world["profile"],
            "--json",
        ],
        env=world["env"],
        timeout=_IMPORT_TIMEOUT_S,
    )
    return _cli_payload(result, "CLI Character import")


@when("the real CLI imports a uniquely named verification Character")
def _cli_import_step(world: dict[str, Any]) -> None:
    request = _start_character("cli")
    world["cli_request"] = request
    world["cli_first"] = _cli_import(world, request)
    world["cli_journal_before_replay"] = _operation_snapshot(world["env"], request["operation_id"])


@when("the CLI replays the first Character with its same operation UUID")
def _cli_replay_step(world: dict[str, Any]) -> None:
    request = world["cli_request"]
    before = _operation_snapshot(world["env"], request["operation_id"])
    world["cli_replay"] = _cli_import(world, request)
    after = _operation_snapshot(world["env"], request["operation_id"])
    assert before == after == world["cli_journal_before_replay"]


async def _call_mcp_import(world: dict[str, Any], request: dict[str, str]) -> dict[str, Any]:
    parameters = StdioServerParameters(
        command=sys.executable,
        args=[
            "-m",
            "gflow_cli",
            "mcp",
            "run",
            "--profile",
            world["profile"],
            "--no-spend",
        ],
        env=world["env"],
    )
    async with stdio_client(parameters) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            initialized = await asyncio.wait_for(session.initialize(), timeout=30)
            assert initialized.server_info.name == "gflow-cli"
            listed = await asyncio.wait_for(session.list_tools(), timeout=30)
            tool_names = {tool.name for tool in listed.tools}
            assert "gflow_character_import" in tool_names
            assert "gflow_generate_image" not in tool_names
            assert "gflow_generate_video" not in tool_names
            result = await asyncio.wait_for(
                session.call_tool(
                    "gflow_character_import",
                    {
                        "project": world["project_id"],
                        "name": request["name"],
                        "sheet_path": str(world["sheet"]),
                        "operation_id": request["operation_id"],
                        "personality": request["personality"],
                        "profile": world["profile"],
                    },
                ),
                timeout=_IMPORT_TIMEOUT_S,
            )
    return _mcp_payload(result, "MCP stdio Character import")


@when("the real MCP stdio server imports a separate verification Character")
def _mcp_import_step(world: dict[str, Any]) -> None:
    request = _start_character("mcp")
    world["mcp_request"] = request
    world["mcp_first"] = asyncio.run(_call_mcp_import(world, request))
    world["mcp_journal_before_replay"] = _operation_snapshot(world["env"], request["operation_id"])


@when("the MCP stdio server replays it with the same operation UUID")
def _mcp_replay_step(world: dict[str, Any]) -> None:
    request = world["mcp_request"]
    before = _operation_snapshot(world["env"], request["operation_id"])
    world["mcp_replay"] = asyncio.run(_call_mcp_import(world, request))
    after = _operation_snapshot(world["env"], request["operation_id"])
    assert before == after == world["mcp_journal_before_replay"]


@when("MCP stdio imports one final verification Character")
def _final_mcp_import_step(world: dict[str, Any]) -> None:
    request = _start_character("mcp-final")
    world["final_request"] = request
    world["final_first"] = asyncio.run(_call_mcp_import(world, request))
    world["final_journal_before_replay"] = _operation_snapshot(
        world["env"], request["operation_id"]
    )


@when("the CLI replays it with the same operation UUID")
def _final_cli_replay_step(world: dict[str, Any]) -> None:
    request = world["final_request"]
    before = _operation_snapshot(world["env"], request["operation_id"])
    world["final_cli_replay"] = _cli_import(world, request)
    after = _operation_snapshot(world["env"], request["operation_id"])
    assert before == after == world["final_journal_before_replay"]


@when("MCP stdio replays it again with the same operation UUID")
def _final_mcp_replay_step(world: dict[str, Any]) -> None:
    request = world["final_request"]
    before = _operation_snapshot(world["env"], request["operation_id"])
    world["final_mcp_replay"] = asyncio.run(_call_mcp_import(world, request))
    after = _operation_snapshot(world["env"], request["operation_id"])
    assert before == after == world["final_journal_before_replay"]


def _verify_replay(
    world: dict[str, Any], surface: str, record_property: Any
) -> tuple[str, str, str, str]:
    request = world[f"{surface}_request"]
    first = world[f"{surface}_first"]
    replay = world[f"{surface}_replay"]
    first_identity = _identity(first)
    replay_identity = _identity(replay)
    assert first_identity == replay_identity
    entity_id, project_id, workflow_ids, bindings = first_identity
    assert project_id == world["project_id"]
    assert set(workflow_ids) == {workflow for workflow, _ in bindings}
    source_hash = hashlib.sha256(world["sheet"].read_bytes()).hexdigest()
    assert first.get("source_sha256") == source_hash
    assert replay.get("source_sha256") == source_hash
    assert first["character"]["display_name"] == request["name"]
    assert replay["character"]["display_name"] == request["name"]
    journal = world[f"{surface}_journal_before_replay"]
    assert journal[2] == "succeeded"
    metadata = json.loads(journal[3])
    assert metadata["entity_id"] == entity_id
    assert metadata["workflow_media_bindings"] == [list(binding) for binding in bindings]

    record_property(f"{surface}_entity_id", entity_id)
    record_property(f"{surface}_workflow_ids", ",".join(workflow_ids))
    record_property(f"{surface}_media_ids", ",".join(media for _, media in bindings))
    record_property(f"{surface}_operation_id", request["operation_id"])
    return entity_id, request["name"], request["personality"], project_id


@then("the CLI import and replay return the same exact entity and bindings")
def _cli_same_identity(world: dict[str, Any], record_property: Any) -> None:
    world["cli_verified"] = _verify_replay(world, "cli", record_property)


@then("the MCP import and replay return the same exact entity and bindings")
def _mcp_same_identity(world: dict[str, Any], record_property: Any) -> None:
    world["mcp_verified"] = _verify_replay(world, "mcp", record_property)


async def _verify_native_form(
    profile_dir: Path,
    *,
    project_id: str,
    entity_id: str,
    name: str,
    personality: str,
) -> None:
    route = f"https://flow.google.com/project/{project_id}/character/{entity_id}"
    async with FlowApiClient(profile_dir=profile_dir, headless=True) as client:
        page = client.page
        await page.goto(route, wait_until="domcontentloaded", timeout=45_000)
        await page.locator("flow-character-edit-page").wait_for(timeout=15_000)
        await page.wait_for_function(
            "expected => document.querySelector('flow-character-form input.name-input')?.value "
            "=== expected.name && document.querySelector("
            "'flow-character-form textarea.personality-textarea')?.value "
            "=== expected.personality",
            arg={"name": name, "personality": personality},
            timeout=20_000,
        )
        expected_path = f"/project/{project_id}/character/{entity_id}"
        assert urlsplit(page.url).path == expected_path
        assert await page.locator("flow-character-form input.name-input").input_value() == name
        assert (
            await page.locator("flow-character-form textarea.personality-textarea").input_value()
            == personality
        )


@then("the CLI Character retains its name and personality after reload")
def _cli_remote_fields(world: dict[str, Any]) -> None:
    entity_id, name, personality, project_id = world["cli_verified"]
    asyncio.run(
        _verify_native_form(
            world["profile_dir"],
            project_id=project_id,
            entity_id=entity_id,
            name=name,
            personality=personality,
        )
    )


@then("the MCP Character retains its name and personality after reload")
def _mcp_remote_fields(world: dict[str, Any]) -> None:
    entity_id, name, personality, project_id = world["mcp_verified"]
    asyncio.run(
        _verify_native_form(
            world["profile_dir"],
            project_id=project_id,
            entity_id=entity_id,
            name=name,
            personality=personality,
        )
    )


@then("the isolated journal contains only these two import operations")
def _only_import_operations(world: dict[str, Any]) -> None:
    expected = {
        world["cli_request"]["operation_id"],
        world["mcp_request"]["operation_id"],
    }
    rows = _operation_rows(world["env"])
    assert {operation_id for operation_id, _, _ in rows} == expected
    assert all(command == "character import" and mode == "character" for _, command, mode in rows)


@then("the MCP import and CLI/MCP replays return the same exact entity and bindings")
def _final_same_identity(world: dict[str, Any], record_property: Any) -> None:
    request = world["final_request"]
    first = world["final_first"]
    cli_replay = world["final_cli_replay"]
    mcp_replay = world["final_mcp_replay"]
    identity = _identity(first)
    assert _identity(cli_replay) == identity
    assert _identity(mcp_replay) == identity
    entity_id, project_id, workflow_ids, bindings = identity
    assert project_id == world["project_id"]
    assert set(workflow_ids) == {workflow for workflow, _ in bindings}
    source_hash = hashlib.sha256(world["sheet"].read_bytes()).hexdigest()
    assert first.get("source_sha256") == source_hash
    assert cli_replay.get("source_sha256") == source_hash
    assert mcp_replay.get("source_sha256") == source_hash
    assert first["character"]["display_name"] == request["name"]
    assert cli_replay["character"]["display_name"] == request["name"]
    assert mcp_replay["character"]["display_name"] == request["name"]

    journal = world["final_journal_before_replay"]
    assert journal[2] == "succeeded"
    metadata = json.loads(journal[3])
    assert metadata["entity_id"] == entity_id
    assert metadata["workflow_media_bindings"] == [list(binding) for binding in bindings]

    record_property("final_entity_id", entity_id)
    record_property("final_workflow_ids", ",".join(workflow_ids))
    record_property("final_media_ids", ",".join(media for _, media in bindings))
    record_property("final_operation_id", request["operation_id"])
    world["final_verified"] = entity_id, request["name"], request["personality"], project_id


@then("the final MCP Character retains its name and personality after reload")
def _final_remote_fields(world: dict[str, Any]) -> None:
    entity_id, name, personality, project_id = world["final_verified"]
    asyncio.run(
        _verify_native_form(
            world["profile_dir"],
            project_id=project_id,
            entity_id=entity_id,
            name=name,
            personality=personality,
        )
    )


@then("the final journal contains only one completed import operation")
def _final_only_import_operation(world: dict[str, Any]) -> None:
    operation_id = world["final_request"]["operation_id"]
    rows = _operation_rows(world["env"])
    assert rows == [(operation_id, "character import", "character")]
    assert _operation_snapshot(world["env"], operation_id)[2] == "succeeded"
