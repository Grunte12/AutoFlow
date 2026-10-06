"""Offline MCP batch wiring; no browser or generation credits."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

from gflow_cli.mcp import tools


def test_batch_schema(mcp_server):
    schema = mcp_server._tool_manager._tools["gflow_generate_video_batch"].parameters
    assert {"shots", "project", "out_dir"} <= set(schema["required"])
    assert {"profile", "state_path", "dry_run", "model", "aspect", "duration", "resolution"} <= set(
        schema["properties"]
    )
    assert "wait" not in schema["properties"]


@pytest.mark.asyncio
async def test_batch_uses_shared_runner_and_resolved_profile(tmp_path):
    from gflow_cli.services import video_batch

    shots = [{"id": "one", "mode": "i2v", "prompt": "test", "start_image": "frame.png"}]
    settings = Mock()
    settings.profile_subdir.return_value = tmp_path / "profile"
    runner = AsyncMock(return_value={"status": "completed", "files": []})
    with (
        patch.object(video_batch, "prepare_video_batch") as prepare,
        patch.object(video_batch, "run_video_batch", runner),
        patch.object(tools, "_resolve_and_validate_profile", return_value="bound"),
        patch.object(tools, "get_settings", return_value=settings),
        patch.object(tools._rate_limiter, "acquire", AsyncMock(return_value=True)) as acquire,
    ):
        result = await tools.gflow_generate_video_batch(
            shots,
            "ca99f6ef-dddf-48ed-9b78-f1887a5a3c7a",
            str(tmp_path),
            model="veo_fast",
            state_path=str(tmp_path / "state.json"),
        )
    assert result["status"] == "completed"
    manifest = prepare.call_args.args[0]
    assert manifest == {
        "project_id": "ca99f6ef-dddf-48ed-9b78-f1887a5a3c7a",
        "shots": shots,
        "defaults": {"model": "veo_fast"},
    }
    acquire.assert_awaited_once_with(len(shots))
    assert runner.call_args.kwargs == {
        "base_dir": Path.cwd(),
        "profile": "bound",
        "profile_dir": tmp_path / "profile",
        "out_dir": tmp_path,
        "state_path": tmp_path / "state.json",
        "dry_run": False,
    }


@pytest.mark.asyncio
async def test_batch_rate_limited_before_runner(tmp_path):
    from gflow_cli.services import video_batch

    with (
        patch.object(video_batch, "prepare_video_batch"),
        patch.object(video_batch, "run_video_batch", AsyncMock()) as runner,
        patch.object(tools, "_resolve_and_validate_profile", return_value="bound"),
        patch.object(tools._rate_limiter, "acquire", AsyncMock(return_value=False)),
    ):
        result = await tools.gflow_generate_video_batch([{}], "project", str(tmp_path))
    assert result["status"] == "rate_limited"
    runner.assert_not_awaited()


@pytest.mark.asyncio
async def test_omni_duration_ten_preserved_by_native_mcp(tmp_path):
    from gflow_cli.services import video_batch

    runner = AsyncMock(return_value={"status": "completed", "files": []})
    with (
        patch.object(video_batch, "prepare_video_batch"),
        patch.object(video_batch, "run_video_batch", runner),
        patch.object(tools, "_resolve_and_validate_profile", return_value="bound"),
        patch.object(tools, "get_settings", return_value=Mock()),
        patch.object(tools._rate_limiter, "acquire", AsyncMock()),
    ):
        await tools.gflow_generate_video_batch(
            [{"id": "ten", "mode": "i2v", "prompt": "settings only", "start_image": "frame.png"}],
            "ca99f6ef-dddf-48ed-9b78-f1887a5a3c7a",
            str(tmp_path),
            dry_run=True,
            model="omni_flash",
            duration=10,
            resolution="720p",
            aspect="9:16",
        )
    assert runner.call_args.args[0]["defaults"] == {
        "model": "omni_flash",
        "duration": 10,
        "resolution": "720p",
        "aspect": "9:16",
    }


@pytest.mark.asyncio
async def test_dry_run_does_not_consume_rate_tokens(tmp_path):
    from gflow_cli.services import video_batch

    with (
        patch.object(video_batch, "prepare_video_batch"),
        patch.object(video_batch, "run_video_batch", AsyncMock(return_value={"status": "dry_run"})),
        patch.object(tools, "_resolve_and_validate_profile", return_value="bound"),
        patch.object(tools, "get_settings", return_value=Mock()),
        patch.object(tools._rate_limiter, "acquire", AsyncMock()) as acquire,
    ):
        result = await tools.gflow_generate_video_batch(
            [{}], "project", str(tmp_path), dry_run=True
        )
    assert result["status"] == "dry_run"
    acquire.assert_not_awaited()


@pytest.mark.asyncio
async def test_bad_preflight_is_guarded_before_rate_limit_and_runner(tmp_path):
    from gflow_cli.errors import ConfigurationError
    from gflow_cli.services import video_batch

    with (
        patch.object(
            video_batch, "prepare_video_batch", side_effect=ConfigurationError("Invalid batch")
        ),
        patch.object(video_batch, "run_video_batch", AsyncMock()) as runner,
        patch.object(tools._rate_limiter, "acquire", AsyncMock()) as acquire,
    ):
        result = await tools.gflow_generate_video_batch([{}], "project", str(tmp_path))
    assert result["status"] == "error"
    assert isinstance(result["error"], dict)
    acquire.assert_not_awaited()
    runner.assert_not_awaited()


@pytest.mark.asyncio
async def test_same_resolved_profile_batches_are_serialized(tmp_path):
    from gflow_cli.services import video_batch

    started = asyncio.Event()
    finish = asyncio.Event()
    calls = 0

    async def run(*args, **kwargs):
        nonlocal calls
        calls += 1
        started.set()
        await finish.wait()
        return {"status": "completed"}

    with (
        patch.object(video_batch, "prepare_video_batch"),
        patch.object(video_batch, "run_video_batch", run),
        patch.object(tools, "_resolve_and_validate_profile", return_value="bound"),
        patch.object(tools, "get_settings", return_value=Mock()),
        patch.object(tools._rate_limiter, "acquire", AsyncMock(return_value=True)),
    ):
        first = asyncio.create_task(
            tools.gflow_generate_video_batch([{}], "project", str(tmp_path))
        )
        await started.wait()
        second = asyncio.create_task(
            tools.gflow_generate_video_batch([{}], "project", str(tmp_path))
        )
        await asyncio.sleep(0)
        assert calls == 1
        finish.set()
        await asyncio.gather(first, second)
    assert calls == 2
