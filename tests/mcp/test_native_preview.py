"""Real stdio MCP subprocess smoke: isolated fixtures, no browser/account/credits."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import get_default_environment, stdio_client
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
SPEND_TOOLS = {"gflow_generate_image", "gflow_generate_video", "gflow_generate_video_batch"}


def _params(tmp_path: Path, *, no_spend: bool) -> StdioServerParameters:
    env = get_default_environment()
    env.update(
        {
            "PYTHONPATH": str(ROOT / "src"),
            "GFLOW_CLI_HOME": str(tmp_path / "home"),
            "GFLOW_CLI_DB_PATH": str(tmp_path / "home" / "gflow.db"),
            "GFLOW_CLI_OUTPUT_DIR": str(tmp_path / "outputs"),
            "GFLOW_CLI_UPDATE_CHECK": "0",
            "GFLOW_MCP_NO_SPEND": "1" if no_spend else "0",
        }
    )
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "gflow_cli", "mcp", "run"],
        env=env,
        cwd=str(tmp_path),
    )


@pytest.mark.asyncio
async def test_native_no_spend_list_excludes_batch_and_preserves_recovery(tmp_path: Path) -> None:
    async with stdio_client(_params(tmp_path, no_spend=True)) as (read, write):
        async with ClientSession(read, write, read_timeout_seconds=30) as client:
            await client.initialize()
            names = {tool.name for tool in (await client.list_tools()).tools}
            assert not names.intersection(SPEND_TOOLS)
            assert {"gflow_download_media", "gflow_auth_status", "gflow_list_projects"} <= names
            guide = await client.read_resource("gflow://docs/mcp-guide")
            assert "NO-SPEND" in str(guide)


@pytest.mark.asyncio
async def test_native_batch_dry_run_round_trip_without_browser_or_ledger(tmp_path: Path) -> None:
    (tmp_path / "home" / "profile_fixture").mkdir(parents=True)
    Image.new("RGB", (32, 32), color="white").save(tmp_path / "frame.png")
    args = {
        "shots": [
            {"id": "one", "mode": "i2v", "prompt": "Synthetic smoke", "start_image": "frame.png"}
        ],
        "project": "ca99f6ef-dddf-48ed-9b78-f1887a5a3c7a",
        "profile": "fixture",
        "out_dir": str(tmp_path / "outputs"),
        "state_path": str(tmp_path / "state.json"),
        "model": "omni_flash",
        "aspect": "9:16",
        "duration": 10,
        "resolution": "720p",
        "dry_run": True,
    }
    async with stdio_client(_params(tmp_path, no_spend=False)) as (read, write):
        async with ClientSession(read, write, read_timeout_seconds=30) as client:
            await client.initialize()
            tools = {tool.name: tool for tool in (await client.list_tools()).tools}
            assert SPEND_TOOLS <= set(tools)
            assert "project" in tools["gflow_download_media"].input_schema["properties"]
            result = await client.call_tool("gflow_generate_video_batch", args)
            assert not result.is_error, result
            blocks = [item.text for item in result.content if item.type == "text"]
            data = json.loads(blocks[0])
            assert data["dry_run"] is True
            assert data["completed"] == []
            assert data["not_started"] == ["one"]
            assert data["files"] == []
            assert "Synthetic smoke" not in blocks[0]
    assert not (tmp_path / "state.json").exists()
    assert not (tmp_path / "outputs").exists()
    assert not any((tmp_path / "home" / "profile_fixture").iterdir())
