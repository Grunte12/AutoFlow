"""Offline safety gates: no browser and no credits spent by these tests."""

from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from gflow_cli.api.dto import GenerationCheckpoint
from gflow_cli.api.video import VideoResult, VideoStatus
from gflow_cli.data.models import AssetKind, AssetRecord
from gflow_cli.data.repository import DataRepository
from gflow_cli.data.store import DataStore
from gflow_cli.errors import ConfigurationError
from gflow_cli.services import video_batch

PROJECT = "ca99f6ef-dddf-48ed-9b78-f1887a5a3c7a"


@pytest.fixture
def manifest(tmp_path: Path) -> dict:
    # A real minimal PNG, not merely a renamed text file.
    import base64

    (tmp_path / "frame.png").write_bytes(
        base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII="
        )
    )
    return {
        "project_id": PROJECT,
        "shots": [
            {"id": "one", "mode": "i2v", "prompt": "one", "start_image": "frame.png"},
            {"id": "two", "mode": "r2v", "prompt": "two", "reference_images": ["frame.png"]},
        ],
    }


@pytest.fixture
def catalog_path(tmp_path: Path) -> Path:
    return tmp_path / "catalog.sqlite3"


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch, catalog_path: Path) -> SimpleNamespace:
    value = SimpleNamespace(
        model_dump=lambda **_: {},
        resolved_db_path=lambda: catalog_path,
    )
    monkeypatch.setattr(video_batch, "get_settings", lambda: value)
    return value


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, settings: SimpleNamespace) -> MagicMock:
    fake = MagicMock()
    fake.__aenter__ = AsyncMock(return_value=fake)
    fake.__aexit__ = AsyncMock(return_value=None)

    async def generate(**kwargs):
        kwargs["on_checkpoint"](GenerationCheckpoint(phase="submit_attempted"))
        kwargs["on_checkpoint"](GenerationCheckpoint(phase="remote_started", media_ids=("media",)))
        path = kwargs["out_dir"] / f"{kwargs['req'].mode.value}.mp4"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"video content")
        return VideoResult(
            VideoStatus(
                "media" if kwargs["req"].mode.value == "i2v" else "media-two",
                "MEDIA_GENERATION_STATUS_SUCCESSFUL",
            ),
            path,
            project_id=PROJECT,
        )

    fake.generate_video = AsyncMock(side_effect=generate)
    factory = MagicMock(return_value=fake)
    monkeypatch.setattr(video_batch, "FlowApiClient", factory)
    fake.factory = factory
    return fake


async def run(manifest, tmp_path, **kwargs):
    return await video_batch.run_video_batch(
        manifest,
        base_dir=tmp_path,
        profile="test",
        profile_dir=tmp_path / "profile",
        out_dir=tmp_path / "out",
        **kwargs,
    )


@pytest.mark.asyncio
@pytest.mark.skipif(os.name == "nt", reason="Creating symlinks may require Windows privileges")
async def test_symlinked_zero_byte_ledger_lock_is_rejected_before_generation(
    manifest, tmp_path, client
):
    state_path = tmp_path / "batch-state.json"
    empty_target = tmp_path / "empty-target"
    empty_target.write_bytes(b"")
    lock_path = state_path.with_suffix(state_path.suffix + ".lock")
    lock_path.symlink_to(empty_target)

    with pytest.raises(ConfigurationError, match="ledger lock"):
        await run(manifest, tmp_path, state_path=state_path)

    assert empty_target.read_bytes() == b""
    assert lock_path.is_symlink()
    client.factory.assert_not_called()


@pytest.mark.asyncio
async def test_hard_linked_zero_byte_ledger_lock_is_rejected_before_generation(
    manifest, tmp_path, client
):
    state_path = tmp_path / "batch-state.json"
    empty_target = tmp_path / "empty-target"
    empty_target.write_bytes(b"")
    lock_path = state_path.with_suffix(state_path.suffix + ".lock")
    os.link(empty_target, lock_path)

    with pytest.raises(ConfigurationError, match="ledger lock"):
        await run(manifest, tmp_path, state_path=state_path)

    assert empty_target.read_bytes() == b""
    assert lock_path.stat().st_nlink == 2
    client.factory.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="FIFOs are not supported on this platform")
async def test_fifo_ledger_lock_is_rejected_before_generation(manifest, tmp_path, client):
    state_path = tmp_path / "batch-state.json"
    lock_path = state_path.with_suffix(state_path.suffix + ".lock")
    os.mkfifo(lock_path)

    with pytest.raises(ConfigurationError, match="ledger lock"):
        await run(manifest, tmp_path, state_path=state_path)

    assert lock_path.is_fifo()
    client.factory.assert_not_called()


def test_existing_regular_ledger_lock_is_preserved(tmp_path):
    state_path = tmp_path / "batch-state.json"
    lock_path = state_path.with_suffix(state_path.suffix + ".lock")
    lock_path.write_bytes(b"existing lock")

    with video_batch._ledger_lock(state_path):
        assert lock_path.read_bytes() == b"existing lock"

    assert lock_path.read_bytes() == b"existing lock"


def _catalog_counts(path: Path, media_id: str = "media") -> tuple[int, int, int]:
    with DataStore.open(path) as store:
        asset_count = store.conn.execute(
            "SELECT COUNT(*) FROM assets WHERE profile_name = 'test' AND flow_media_id = ?",
            (media_id,),
        ).fetchone()[0]
        file_count = store.conn.execute(
            "SELECT COUNT(*) FROM local_files lf JOIN assets a ON a.id = lf.asset_id "
            "WHERE lf.profile_name = 'test' AND a.flow_media_id = ?",
            (media_id,),
        ).fetchone()[0]
        operation_count = store.conn.execute(
            "SELECT COUNT(*) FROM operations WHERE profile_name = 'test'"
        ).fetchone()[0]
    return int(asset_count), int(file_count), int(operation_count)


@pytest.mark.asyncio
async def test_one_context_shared_project_sequential(manifest, tmp_path, client):
    result = await run(manifest, tmp_path)
    assert result["status"] == "completed"
    assert result["completed"] == ["one", "two"]
    client.factory.assert_called_once()
    client.__aenter__.assert_awaited_once()
    assert [c.kwargs["project_id"] for c in client.generate_video.await_args_list] == [PROJECT] * 2
    assert all(c.kwargs["req"].count == 1 for c in client.generate_video.await_args_list)
    assert all(c.kwargs["req"].duration is None for c in client.generate_video.await_args_list)
    assert len(result["files"]) == 2
    assert result["credits_before"] is None
    assert result["credits_after"] is None
    assert result["credits_charged"] is None
    assert result["credits_reason"]


@pytest.mark.asyncio
async def test_success_records_observed_asset_and_local_file_only(
    manifest, tmp_path, client, settings
):
    manifest["shots"] = manifest["shots"][:1]

    result = await run(manifest, tmp_path)

    assert result["status"] == "completed"
    assert result["catalog_pending"] == []
    assert _catalog_counts(settings.resolved_db_path()) == (1, 1, 0)
    with DataStore.open(settings.resolved_db_path()) as store:
        asset = store.conn.execute(
            "SELECT flow_project_id, flow_workflow_id, model, duration_seconds "
            "FROM assets WHERE profile_name = 'test' AND flow_media_id = 'media'"
        ).fetchone()
        local_file = store.conn.execute(
            "SELECT path, bytes, sha256 FROM local_files WHERE profile_name = 'test'"
        ).fetchone()
    assert tuple(asset) == (PROJECT, None, None, None)
    assert local_file["path"] == result["files"][0]["path"]
    assert local_file["bytes"] == len(b"video content")
    assert local_file["sha256"] == result["files"][0]["sha256"]


@pytest.mark.asyncio
async def test_catalog_resume_preserves_existing_asset_metadata(
    manifest, tmp_path, client, settings
):
    manifest["shots"] = manifest["shots"][:1]
    with DataStore.open(settings.resolved_db_path()) as store:
        repo = DataRepository(store)
        repo.upsert_profile("test", tmp_path / "profile")
        repo.upsert_asset(
            AssetRecord(
                id="existing-asset",
                profile_name="test",
                flow_project_id=PROJECT,
                flow_media_id="media",
                flow_workflow_id="existing-workflow",
                flow_media_generation_id=None,
                kind=AssetKind.VIDEO,
                status="existing-status",
                model="existing-model",
                aspect_ratio="portrait",
                width=720,
                height=1280,
                duration_seconds=8.0,
                seed=42,
                metadata_json={"kept": True},
            )
        )

    result = await run(manifest, tmp_path)

    assert result["catalog_pending"] == []
    with DataStore.open(settings.resolved_db_path()) as store:
        row = store.conn.execute(
            "SELECT flow_project_id, flow_workflow_id, status, model, aspect_ratio, width, "
            "height, duration_seconds, seed, metadata_json FROM assets WHERE id = 'existing-asset'"
        ).fetchone()
    assert tuple(row) == (
        PROJECT,
        "existing-workflow",
        "existing-status",
        "existing-model",
        "portrait",
        720,
        1280,
        8.0,
        42,
        '{"kept": true}',
    )
    assert _catalog_counts(settings.resolved_db_path()) == (1, 1, 0)


@pytest.mark.asyncio
async def test_catalog_project_conflict_stays_pending_without_overwrite(
    manifest, tmp_path, client, settings
):
    manifest["shots"] = manifest["shots"][:1]
    with DataStore.open(settings.resolved_db_path()) as store:
        repo = DataRepository(store)
        repo.upsert_profile("test", tmp_path / "profile")
        repo.upsert_asset(
            AssetRecord(
                id="existing-asset",
                profile_name="test",
                flow_project_id="another-project",
                flow_media_id="media",
                flow_workflow_id=None,
                flow_media_generation_id=None,
                kind=AssetKind.VIDEO,
                status="existing-status",
                model=None,
                aspect_ratio=None,
                width=None,
                height=None,
                duration_seconds=None,
                seed=None,
                metadata_json={},
            )
        )

    result = await run(manifest, tmp_path)

    assert result["status"] == "completed"
    assert result["catalog_pending"] == ["one"]
    assert Path(result["files"][0]["path"]).is_file()
    with DataStore.open(settings.resolved_db_path()) as store:
        row = store.conn.execute(
            "SELECT flow_project_id, status FROM assets WHERE id = 'existing-asset'"
        ).fetchone()
        local_files = store.conn.execute("SELECT COUNT(*) FROM local_files").fetchone()[0]
    assert tuple(row) == ("another-project", "existing-status")
    assert local_files == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("terminal", ["failed", "success_without_output"])
async def test_failed_or_unvalidated_output_creates_no_catalog_rows(
    manifest, tmp_path, client, settings, terminal
):
    manifest["shots"] = manifest["shots"][:1]
    if terminal == "failed":
        failure = VideoResult(
            VideoStatus("media", "MEDIA_GENERATION_STATUS_FAILED"), None, project_id=PROJECT
        )
    else:
        failure = VideoResult(
            VideoStatus("media", "MEDIA_GENERATION_STATUS_SUCCESSFUL"), None, project_id=PROJECT
        )

    async def return_result(**_):
        return failure

    client.generate_video.side_effect = return_result

    result = await run(manifest, tmp_path)

    assert result["completed"] == []
    assert _catalog_counts(settings.resolved_db_path()) == (0, 0, 0)


@pytest.mark.asyncio
async def test_catalog_persistence_failure_keeps_completed_ledger_and_never_regenerates(
    manifest, tmp_path, client, settings, monkeypatch
):
    manifest["shots"] = manifest["shots"][:1]
    real_record = video_batch._record_completed_asset

    def fail_catalog(*_args, **_kwargs):
        raise OSError("catalog unavailable")

    monkeypatch.setattr(video_batch, "_record_completed_asset", fail_catalog, raising=False)
    first = await run(manifest, tmp_path)
    ledger = json.loads((tmp_path / "out/video-batch-state.json").read_text())
    assert first["completed"] == ["one"]
    assert first["catalog_pending"] == ["one"]
    assert ledger["shots"][0]["state"] == "completed"
    assert Path(first["files"][0]["path"]).is_file()

    client.factory.reset_mock()
    second = await run(manifest, tmp_path)

    assert second["completed"] == ["one"]
    assert second["catalog_pending"] == ["one"]
    client.factory.assert_not_called()

    monkeypatch.setattr(video_batch, "_record_completed_asset", real_record)
    third = await run(manifest, tmp_path)

    assert third["catalog_pending"] == []
    assert _catalog_counts(settings.resolved_db_path()) == (1, 1, 0)
    client.factory.assert_not_called()


@pytest.mark.asyncio
async def test_omni_i2v_ten_seconds_and_720p_reach_shared_client(manifest, tmp_path, client):
    manifest["shots"] = manifest["shots"][:1]
    manifest["defaults"] = {
        "model": "omni_flash",
        "duration": 10,
        "resolution": "720p",
        "aspect": "9:16",
    }
    result = await run(manifest, tmp_path)
    assert result["status"] == "completed"
    request = client.generate_video.await_args.kwargs["req"]
    assert request.duration == 10
    assert request.resolution == "720p"
    assert request.count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", ["prompt", "image", "count", "project", "unknown", "prompt_file"])
async def test_preflight_all_rows_before_browser(manifest, tmp_path, client, bad):
    row = manifest["shots"][1]
    if bad == "prompt":
        row["prompt"] = " "
    elif bad == "image":
        (tmp_path / "frame.png").write_text("not an image")
    elif bad == "count":
        row["count"] = 2
    elif bad == "project":
        manifest["project_id"] = "not-uuid"
    elif bad == "unknown":
        row["tool"] = "rewrite"
    else:
        row["prompt_file"] = "frame.png"
    with pytest.raises(ConfigurationError):
        await run(manifest, tmp_path)
    client.factory.assert_not_called()


@pytest.mark.asyncio
async def test_resume_skips_completed_and_checks_hash(manifest, tmp_path, client):
    settings = video_batch.get_settings()
    result = await run(manifest, tmp_path)
    before_one = _catalog_counts(settings.resolved_db_path(), "media")
    before_two = _catalog_counts(settings.resolved_db_path(), "media-two")
    client.factory.reset_mock()
    await run(manifest, tmp_path)
    client.factory.assert_not_called()
    assert _catalog_counts(settings.resolved_db_path(), "media") == before_one == (1, 1, 0)
    assert _catalog_counts(settings.resolved_db_path(), "media-two") == before_two == (1, 1, 0)
    Path(result["files"][0]["path"]).write_bytes(b"changed")
    with pytest.raises(ConfigurationError):
        await run(manifest, tmp_path)
    client.factory.assert_not_called()


@pytest.mark.asyncio
async def test_changed_prompt_rejects_resume(manifest, tmp_path, client):
    await run(manifest, tmp_path)
    manifest["shots"][1]["prompt"] = "changed"
    client.factory.reset_mock()
    with pytest.raises(ConfigurationError):
        await run(manifest, tmp_path)
    client.factory.assert_not_called()


@pytest.mark.asyncio
async def test_ambiguous_stops_remaining_and_rerun_cannot_spend(manifest, tmp_path, client):
    async def uncertain(**kwargs):
        kwargs["on_checkpoint"](GenerationCheckpoint(phase="submit_attempted"))
        kwargs["on_checkpoint"](
            GenerationCheckpoint(
                phase="remote_started",
                media_ids=(PROJECT,),
                operation_id=PROJECT,
                workflow_ids=(PROJECT,),
            )
        )
        raise TimeoutError("secret prompt https://signed.example")

    client.generate_video.side_effect = uncertain
    result = await run(manifest, tmp_path)
    assert result["status"] == "indeterminate"
    assert result["stopped"]["media_ids"] == [PROJECT]
    assert result["stopped"]["operation_id"] == PROJECT
    assert result["stopped"]["workflow_ids"] == [PROJECT]
    assert result["not_started"] == ["two"]
    assert "secret" not in json.dumps(result)
    assert client.generate_video.await_count == 1
    client.factory.reset_mock()
    again = await run(manifest, tmp_path)
    assert again["status"] == "indeterminate"
    client.factory.assert_not_called()


@pytest.mark.asyncio
async def test_partial_files_survive_later_ambiguity(manifest, tmp_path, client):
    good = client.generate_video.side_effect

    async def second_fails(**kwargs):
        if kwargs["req"].mode.value == "r2v":
            raise TimeoutError()
        return await good(**kwargs)

    client.generate_video.side_effect = second_fails
    result = await run(manifest, tmp_path)
    assert result["status"] == "indeterminate"
    assert result["completed"] == ["one"]
    assert len(result["files"]) == 1
    assert Path(result["files"][0]["path"]).exists()


@pytest.mark.asyncio
async def test_dry_run_does_not_launch_or_write_ledger(manifest, tmp_path, client):
    result = await run(manifest, tmp_path, dry_run=True)
    assert result["dry_run"] is True
    assert result["not_started"] == ["one", "two"]
    client.factory.assert_not_called()
    assert not (tmp_path / "out").exists()


@pytest.mark.asyncio
async def test_checkpoint_failure_prevents_transport_submit(
    manifest, tmp_path, client, monkeypatch
):
    real_save = video_batch._save_ledger
    spent = []

    def broken_checkpoint(path, ledger):
        if ledger["shots"][0]["state"] == "submit_attempted":
            raise OSError("disk full")
        real_save(path, ledger)

    async def generate(**kwargs):
        kwargs["on_checkpoint"](GenerationCheckpoint(phase="submit_attempted"))
        spent.append("submitted")

    monkeypatch.setattr(video_batch, "_save_ledger", broken_checkpoint)
    client.generate_video.side_effect = generate
    result = await run(manifest, tmp_path)
    assert result["status"] == "indeterminate"
    assert spent == []
    client.factory.reset_mock()
    await run(manifest, tmp_path)
    client.factory.assert_not_called()


@pytest.mark.asyncio
async def test_terminal_failure_returns_partial(manifest, tmp_path, client):
    good = client.generate_video.side_effect

    async def second_fails(**kwargs):
        if kwargs["req"].mode.value == "r2v":
            return VideoResult(VideoStatus("failed", "MEDIA_GENERATION_STATUS_FAILED"), None)
        return await good(**kwargs)

    client.generate_video.side_effect = second_fails
    result = await run(manifest, tmp_path)
    assert result["status"] == "partial"
    assert result["completed"] == ["one"]
    client.factory.reset_mock()
    assert (await run(manifest, tmp_path))["status"] == "partial"
    client.factory.assert_not_called()


@pytest.mark.asyncio
async def test_missing_completed_file_never_regenerates(manifest, tmp_path, client):
    result = await run(manifest, tmp_path)
    Path(result["files"][0]["path"]).unlink()
    client.factory.reset_mock()
    with pytest.raises(ConfigurationError):
        await run(manifest, tmp_path)
    client.factory.assert_not_called()


@pytest.mark.asyncio
async def test_prompt_file_contents_not_path_drive_resume(manifest, tmp_path, client):
    row = manifest["shots"][0]
    row.pop("prompt")
    row["prompt_file"] = "prompt.txt"
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("private prompt", encoding="utf-8")
    await run(manifest, tmp_path)
    ledger = (tmp_path / "out/video-batch-state.json").read_text()
    assert "private prompt" not in ledger
    prompt.write_text("changed prompt", encoding="utf-8")
    client.factory.reset_mock()
    with pytest.raises(ConfigurationError):
        await run(manifest, tmp_path)
    client.factory.assert_not_called()
