"""Offline CLI wiring for the shared video batch runner."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from click.testing import CliRunner

from gflow_cli.cli_video import video


@pytest.mark.parametrize("status,exit_code", [("completed", 0), ("indeterminate", 1)])
def test_batch_passes_shared_inputs_and_emits_one_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    status: str,
    exit_code: int,
) -> None:
    path = tmp_path / "shots.json"
    path.write_text(json.dumps({"shots": []}), encoding="utf-8")
    monkeypatch.setattr("gflow_cli.cli_video_batch._resolve_profile", lambda p: p)
    monkeypatch.setattr("gflow_cli.cli_video_batch._make_provider_dir", lambda p: tmp_path)
    run = AsyncMock(
        return_value={
            "status": status,
            "completed": [],
            "files": [],
            "stopped": None,
            "next_action": "None.",
        }
    )
    monkeypatch.setattr("gflow_cli.cli_video_batch.run_video_batch", run)
    result = CliRunner().invoke(
        video,
        [
            "batch",
            str(path),
            "--profile",
            "test",
            "--out-dir",
            str(tmp_path / "out"),
            "--dry-run",
            "--json",
        ],
    )
    assert result.exit_code == exit_code, result.output
    assert json.loads(result.output)["status"] == status
    run.assert_awaited_once()
    assert run.await_args.kwargs["base_dir"] == tmp_path
    assert run.await_args.kwargs["profile"] == "test"
    assert run.await_args.kwargs["dry_run"] is True


def test_catalog_pending_warns_without_turning_completed_generation_into_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "shots.json"
    path.write_text(json.dumps({"shots": []}), encoding="utf-8")
    monkeypatch.setattr("gflow_cli.cli_video_batch._resolve_profile", lambda p: p)
    monkeypatch.setattr("gflow_cli.cli_video_batch._make_provider_dir", lambda p: tmp_path)
    run = AsyncMock(
        return_value={
            "status": "completed",
            "completed": ["one"],
            "files": [{"path": str(tmp_path / "one.mp4")}],
            "stopped": None,
            "catalog_pending": ["one"],
            "next_action": (
                "Retry this command to reconcile local catalog records; completed outputs "
                "remain saved and will not be regenerated."
            ),
        }
    )
    monkeypatch.setattr("gflow_cli.cli_video_batch.run_video_batch", run)

    result = CliRunner().invoke(video, ["batch", str(path)])

    assert result.exit_code == 0, result.output
    assert "Video batch: completed; 1 completed." in result.output
    assert "catalog records" in result.output
    assert "will not be regenerated" in result.output


def test_batch_bad_json_does_not_echo_prompt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("gflow_cli._cli_helpers.emit_error_event", lambda *a, **k: None)
    path = tmp_path / "shots.json"
    path.write_text('{"prompt":"private text', encoding="utf-8")
    result = CliRunner().invoke(video, ["batch", str(path), "--json"])
    assert result.exit_code == 11
    assert "private text" not in result.output
    assert json.loads(result.output)["status"] == "fail"
