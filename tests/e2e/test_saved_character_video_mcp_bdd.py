"""One paid MCP regression. Requires explicit request JSON and video opt-in.

The request and once-only journal live outside Git. Never repeat an uncertain
paid outcome: inspect its journal, project and MCP queue before another run.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from pytest_bdd import given, scenarios, then, when

scenarios("../features/saved_character_video_mcp.feature")


@given("an explicit one-clip saved Character test request", target_fixture="request_state")
def authorized_request(e2e_profile_dir: Path) -> dict:
    if os.environ.get("GFLOW_CLI_E2E_RUN_VIDEO") != "1":
        pytest.skip("Set GFLOW_CLI_E2E_RUN_VIDEO=1 after explicit one-clip approval")
    source = os.environ.get("GFLOW_CLI_CHARACTER_TEST_REQUEST")
    if not source:
        pytest.skip("Requires a private owner-authorized Character request JSON")
    path = Path(source)
    args = json.loads(path.read_text())
    assert args["count"] == 1 and args["mode"] == "r2v" and args["wait"] is True
    assert args["reference_entities"] and args["reference_entity_names"]
    assert args["profile"] == os.environ["GFLOW_CLI_E2E_PROFILE"]
    assert e2e_profile_dir.is_dir()
    return {"args": args, "root": path.parent}


@when("the request runs once through the candidate stdio MCP server")
def run_mcp_once(request_state: dict) -> None:
    async def execute() -> None:
        root: Path = request_state["root"]
        marker = root / "candidate-request-once.json"
        # Exclusive creation before dispatch is deliberate, including on failure.
        with marker.open("x") as journal:
            json.dump({"state": "dispatching", "arguments": request_state["args"]}, journal)
        env = os.environ.copy()
        env["GFLOW_CLI_HOME"] = os.environ["GFLOW_CLI_E2E_HOME"]
        env["GFLOW_CLI_DB_PATH"] = str(root / "candidate-mcp.sqlite3")
        env["GFLOW_CLI_HEADLESS"] = "false"
        env["PYTHONPATH"] = str(Path(__file__).resolve().parents[2] / "src")
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "gflow_cli", "mcp", "run"],
            env=env,
            cwd=str(Path(__file__).resolve().parents[2]),
        )
        with (root / "candidate-mcp.log").open("w") as log:
            async with stdio_client(params, errlog=log) as (read, write):
                async with ClientSession(read, write, read_timeout_seconds=1200) as session:
                    await session.initialize()
                    result = await session.call_tool(
                        "gflow_generate_video", request_state["args"], read_timeout_seconds=1200
                    )
                    data = result.model_dump(mode="json")
                    (root / "candidate-result.json").write_text(
                        json.dumps(data, ensure_ascii=False)
                    )
                    request_state["result"] = data

    asyncio.run(execute())


@then("MCP reports a completed task with a local playable video")
def verify_video(request_state: dict) -> None:
    data = request_state["result"]
    texts = [block["text"] for block in data["content"] if block["type"] == "text"]
    response = json.loads(texts[0])
    assert response["status"] in ("completed", "success"), response
    output = Path(request_state["args"]["output"])
    assert output.is_file() and output.stat().st_size > 10000
    subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(output), "-f", "null", "-"],
        check=True,
        capture_output=True,
    )
