"""Opt-in live proof for replay-safe updates to an existing Flow Character."""

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

import pytest
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from pytest_bdd import given, scenarios, then, when

scenarios("../features/character_update_live.feature")

_RUN_ENV = "GFLOW_CLI_E2E_RUN_CHARACTER_UPDATE"
_PROJECT_ENV = "GFLOW_CLI_E2E_CHARACTER_UPDATE_PROJECT"
_ENTITY_ENV = "GFLOW_CLI_E2E_CHARACTER_UPDATE_ENTITY"
_PORTRAIT_ENV = "GFLOW_CLI_E2E_CHARACTER_UPDATE_PORTRAIT"
_FULL_BODY_ENV = "GFLOW_CLI_E2E_CHARACTER_UPDATE_FULL_BODY"
_REPLAY_DB_ENV = "GFLOW_CLI_E2E_CHARACTER_UPDATE_REPLAY_DB"
_REPLAY_OPERATION_ENV = "GFLOW_CLI_E2E_CHARACTER_UPDATE_REPLAY_OPERATION"
_TIMEOUT_S = 300


def _required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        pytest.skip(f"set {name} to run the Character update E2E")
    return value


def _canonical_uuid(value: str, name: str) -> str:
    try:
        canonical = str(uuid.UUID(value))
    except ValueError as exc:
        pytest.fail(f"{name} must be a canonical UUID", pytrace=False)
        raise AssertionError from exc
    if canonical != value:
        pytest.fail(f"{name} must be a canonical UUID", pytrace=False)
    return canonical


def _build_world(e2e_env: dict[str, str], e2e_profile_dir: Path) -> dict[str, Any]:
    project = _canonical_uuid(_required_env(_PROJECT_ENV), _PROJECT_ENV)
    entity = _canonical_uuid(_required_env(_ENTITY_ENV), _ENTITY_ENV)
    portrait = Path(_required_env(_PORTRAIT_ENV)).expanduser().resolve()
    full_body = Path(_required_env(_FULL_BODY_ENV)).expanduser().resolve()
    for name, path in (("portrait", portrait), ("full-body", full_body)):
        if not path.is_file():
            pytest.fail(f"configured {name} source must be an existing local file", pytrace=False)

    replay_db_value = os.environ.get(_REPLAY_DB_ENV, "").strip()
    replay_operation_value = os.environ.get(_REPLAY_OPERATION_ENV, "").strip()
    if bool(replay_db_value) != bool(replay_operation_value):
        pytest.fail(f"set {_REPLAY_DB_ENV} and {_REPLAY_OPERATION_ENV} together", pytrace=False)
    replay_db: Path | None = None
    replay_operation: str | None = None
    if replay_db_value:
        replay_db = Path(replay_db_value)
        if not replay_db.is_absolute() or not replay_db.is_file() or replay_db.is_symlink():
            pytest.fail(
                f"{_REPLAY_DB_ENV} must be an absolute existing regular file", pytrace=False
            )
        replay_operation = _canonical_uuid(replay_operation_value, _REPLAY_OPERATION_ENV)
        _validate_replay_database(replay_db, replay_operation)

    env = dict(e2e_env)
    env.update(
        GFLOW_CLI_PROFILE=os.environ["GFLOW_CLI_E2E_PROFILE"].strip(),
        GFLOW_CLI_HEADLESS="1",
        GFLOW_CLI_BROWSER_BACKGROUND="0",
        GFLOW_CLI_LEASE_WAIT_SECONDS="0",
        GFLOW_CLI_FLOW_HOST="flow.google.com",
        GFLOW_MCP_NO_SPEND="1",
    )
    if replay_db is not None:
        env["GFLOW_CLI_DB_PATH"] = str(replay_db)
    return {
        "env": env,
        "profile": env["GFLOW_CLI_PROFILE"],
        "profile_dir": e2e_profile_dir,
        "project": project,
        "entity": entity,
        "portrait": portrait,
        "full_body": full_body,
        "replay_operation_id": replay_operation,
    }


def _validate_replay_database(database: Path, operation_id: str) -> None:
    try:
        database_uri = f"{database.resolve().as_uri()}?mode=ro"
        with sqlite3.connect(database_uri, uri=True) as connection:
            rows = connection.execute(
                "SELECT command, mode, status FROM operations WHERE id = ?",
                (operation_id,),
            ).fetchall()
    except sqlite3.Error as exc:
        pytest.fail(f"replay database is unreadable: {type(exc).__name__}", pytrace=False)
    if rows != [("character update-images", "character", "succeeded")]:
        pytest.fail(
            "replay database must contain exactly the requested succeeded Character update",
            pytrace=False,
        )


@given(
    "an opted-in existing Character and portrait and full-body source images",
    target_fixture="world",
)
def _prepare_world(e2e_env: dict[str, str], e2e_profile_dir: Path) -> dict[str, Any]:
    if os.environ.get(_RUN_ENV, "0").strip() != "1":
        pytest.skip(f"set {_RUN_ENV}=1 to update an existing Character")
    return _build_world(e2e_env, e2e_profile_dir)


def _run_gflow(args: list[str], *, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, "-m", "gflow_cli", *args]
    with tempfile.TemporaryDirectory(prefix="gflow-character-update-e2e-") as directory:
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
                process.wait(timeout=_TIMEOUT_S)
            except subprocess.TimeoutExpired:
                timed_out = True
                process.kill()
                process.wait(timeout=30)
        stdout = stdout_path.read_text(encoding="utf-8", errors="replace")
        stderr = stderr_path.read_text(encoding="utf-8", errors="replace")
    if timed_out:
        pytest.fail("CLI Character update timed out; inspect its journal before any retry")
    return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)


def _cli_payload(result: subprocess.CompletedProcess[str], label: str) -> dict[str, Any]:
    if result.returncode != 0:
        try:
            problem = json.loads(result.stdout.strip())
        except json.JSONDecodeError:
            problem = {}
        if isinstance(problem, dict) and isinstance(problem.get("error"), dict):
            problem = problem["error"]
        detail = problem.get("detail", "no structured detail") if isinstance(problem, dict) else ""
        pytest.fail(f"{label} exited {result.returncode}: {str(detail)[:400]}")
    try:
        payload = json.loads(result.stdout.strip())
    except json.JSONDecodeError as exc:
        raise AssertionError(f"{label} did not return JSON") from exc
    assert isinstance(payload, dict) and payload.get("status") == "ok"
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
        assert texts, f"{label} returned no result"
        payload = json.loads(texts[0])
    assert isinstance(payload, dict) and payload.get("status") == "ok"
    return payload


def _snapshot(world: dict[str, Any], operation_id: str) -> tuple[str, str, str, str]:
    with sqlite3.connect(world["env"]["GFLOW_CLI_DB_PATH"]) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            "SELECT command, mode, status, metadata_json FROM operations WHERE id = ?",
            (operation_id,),
        ).fetchall()
    assert len(rows) == 1, "expected exactly one durable operation for this update UUID"
    row = rows[0]
    assert row["command"] == "character update-images"
    assert row["mode"] == "character"
    return row["command"], row["mode"], row["status"], row["metadata_json"]


def _assert_only_update_operation(world: dict[str, Any], operation_id: str) -> None:
    with sqlite3.connect(world["env"]["GFLOW_CLI_DB_PATH"]) as connection:
        rows = connection.execute("SELECT id, command FROM operations").fetchall()
    assert [(str(row[0]), str(row[1])) for row in rows] == [
        (operation_id, "character update-images")
    ]


async def _call_mcp(world: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "gflow_cli", "mcp", "run", "--profile", world["profile"], "--no-spend"],
        env=world["env"],
    )
    async with stdio_client(parameters) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            initialized = await asyncio.wait_for(session.initialize(), timeout=30)
            assert initialized.server_info.name == "gflow-cli"
            tools = await asyncio.wait_for(session.list_tools(), timeout=30)
            names = {tool.name for tool in tools.tools}
            assert "gflow_character_update_images" in names
            assert "gflow_generate_image" not in names
            assert "gflow_generate_video" not in names
            result = await asyncio.wait_for(
                session.call_tool("gflow_character_update_images", request),
                timeout=_TIMEOUT_S,
            )
    return _mcp_payload(result, "MCP stdio Character update")


def _request(world: dict[str, Any], *, both: bool) -> dict[str, Any]:
    replay_operation = world.get("replay_operation_id")
    if replay_operation is not None and not both:
        pytest.fail("replay-only operation is restricted to the both-slot scenario", pytrace=False)
    request: dict[str, Any] = {
        "project": world["project"],
        "entity_id": world["entity"],
        "operation_id": replay_operation or str(uuid.uuid4()),
        "portrait_path": str(world["portrait"]),
        "profile": world["profile"],
    }
    if both:
        request["full_body_path"] = str(world["full_body"])
    return request


def _cli_args(request: dict[str, Any], *, both: bool) -> list[str]:
    args = [
        "character",
        "update-images",
        "--project",
        request["project"],
        "--entity-id",
        request["entity_id"],
        "--operation-id",
        request["operation_id"],
        "--portrait",
        request["portrait_path"],
        "--profile",
        request["profile"],
        "--json",
    ]
    if both:
        args.extend(["--full-body", request["full_body_path"]])
    return args


def _assert_source_hashes(
    world: dict[str, Any], request: dict[str, Any], payload: dict[str, Any], *, both: bool
) -> None:
    assert payload["project"] == world["project"]
    assert payload["entity_id"] == world["entity"]
    expected_slots = {"portrait", "full_body"} if both else {"portrait"}
    assert set(payload["images"]) == expected_slots
    paths = {"portrait": world["portrait"], "full_body": world["full_body"]}
    for slot in expected_slots:
        image = payload["images"][slot]
        assert image["workflow_id"] and image["media_id"]
        assert image["source_sha256"] == hashlib.sha256(paths[slot].read_bytes()).hexdigest()


@when("MCP stdio updates both Character image slots")
def _mcp_updates_both(world: dict[str, Any]) -> None:
    world["request"] = _request(world, both=True)
    world["first"] = asyncio.run(_call_mcp(world, world["request"]))
    world["both"] = True
    _assert_source_hashes(world, world["request"], world["first"], both=True)
    world["journal"] = _snapshot(world, world["request"]["operation_id"])
    assert world["journal"][2] == "succeeded"
    metadata = json.loads(world["journal"][3])
    assert metadata["before"]["metadata_sha256"] == metadata["expected_state"]["metadata_sha256"]
    _assert_only_update_operation(world, world["request"]["operation_id"])


@when("the CLI replays the same Character update operation")
def _cli_replays_both(world: dict[str, Any]) -> None:
    before = _snapshot(world, world["request"]["operation_id"])
    result = _run_gflow(_cli_args(world["request"], both=True), env=world["env"])
    world["cli_replay"] = _cli_payload(result, "CLI Character update replay")
    assert _snapshot(world, world["request"]["operation_id"]) == before == world["journal"]


@when("MCP stdio replays the same Character update operation")
def _mcp_replays(world: dict[str, Any]) -> None:
    before = _snapshot(world, world["request"]["operation_id"])
    world["mcp_replay"] = asyncio.run(_call_mcp(world, world["request"]))
    assert _snapshot(world, world["request"]["operation_id"]) == before == world["journal"]


@when("the CLI updates only the portrait slot")
def _cli_updates_portrait(world: dict[str, Any]) -> None:
    if world.get("replay_operation_id") is not None:
        pytest.fail("replay-only database cannot run the portrait-only scenario", pytrace=False)
    world["request"] = _request(world, both=False)
    result = _run_gflow(_cli_args(world["request"], both=False), env=world["env"])
    world["first"] = _cli_payload(result, "CLI Character portrait update")
    world["both"] = False
    _assert_source_hashes(world, world["request"], world["first"], both=False)
    world["journal"] = _snapshot(world, world["request"]["operation_id"])
    assert world["journal"][2] == "succeeded"
    _assert_only_update_operation(world, world["request"]["operation_id"])


@then("both returned slots match the sources and the journal is verified")
def _both_updates_verified(world: dict[str, Any], record_property: Any) -> None:
    metadata = json.loads(world["journal"][3])
    assert metadata["before"]["metadata_sha256"] == metadata["expected_state"]["metadata_sha256"]
    record_property("character_update_project", world["project"])
    record_property("character_update_entity", world["entity"])
    record_property("character_update_operation", world["request"]["operation_id"])
    record_property(
        "character_update_workflows",
        json.dumps(
            {slot: binding["workflow_id"] for slot, binding in world["first"]["images"].items()}
        ),
    )
    record_property(
        "character_update_source_hashes",
        json.dumps(
            {slot: image["source_sha256"] for slot, image in world["first"]["images"].items()}
        ),
    )


@then("the CLI replay matches and the journal is unchanged")
def _cli_replay_matches(world: dict[str, Any]) -> None:
    assert world["cli_replay"] == world["first"]


@then("the MCP replay matches and the journal is unchanged")
def _mcp_replay_matches(world: dict[str, Any], record_property: Any) -> None:
    assert world["mcp_replay"] == world["first"]
    record_property("character_update_operation", world["request"]["operation_id"])
    record_property("character_update_status", world["journal"][2])


@then("the journal proves the omitted slot and metadata were preserved")
def _portrait_only_preserved(world: dict[str, Any], record_property: Any) -> None:
    metadata = json.loads(world["journal"][3])
    before = metadata["before"]
    expected = metadata["expected_state"]
    assert expected["images"]["full_body"] == before["images"]["full_body"]
    assert expected["metadata_sha256"] == before["metadata_sha256"]
    record_property("character_update_operation", world["request"]["operation_id"])
    record_property("character_update_metadata_sha256", expected["metadata_sha256"])
    record_property(
        "character_update_untouched_full_body", json.dumps(expected["images"]["full_body"])
    )
