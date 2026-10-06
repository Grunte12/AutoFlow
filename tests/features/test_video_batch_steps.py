"""Offline BDD bindings for video batch preflight (no live generation claim)."""

from __future__ import annotations

import asyncio
import base64
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from pytest_bdd import given, scenarios, then, when

from gflow_cli.errors import ConfigurationError
from gflow_cli.services.video_batch import run_video_batch

scenarios("video_batch.feature")


@pytest.fixture
def batch_case(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    client = MagicMock(side_effect=AssertionError("browser must not launch"))
    monkeypatch.setattr("gflow_cli.services.video_batch.FlowApiClient", client)
    return {"path": tmp_path, "client": client}


@given("a video manifest containing two supplied local-image shots")
def manifest(batch_case: dict[str, Any]) -> None:
    path = batch_case["path"]
    (path / "frame.png").write_bytes(
        base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII="
        )
    )
    batch_case["manifest"] = {
        "project_id": "ca99f6ef-dddf-48ed-9b78-f1887a5a3c7a",
        "shots": [
            {"id": name, "mode": "i2v", "prompt": "hold the frame", "start_image": "frame.png"}
            for name in ("one", "two")
        ],
    }


@given("the later shot has an empty prompt")
def bad_prompt(batch_case: dict[str, Any]) -> None:
    batch_case["manifest"]["shots"][1]["prompt"] = " "


@when("I dry run the video batch")
def dry_run(batch_case: dict[str, Any]) -> None:
    path = batch_case["path"]
    try:
        batch_case["result"] = asyncio.run(
            run_video_batch(
                batch_case["manifest"],
                base_dir=path,
                profile="test",
                profile_dir=path / "profile",
                out_dir=path / "out",
                dry_run=True,
            )
        )
    except ConfigurationError as exc:
        batch_case["error"] = exc


@then("all shots are reported as not started")
def all_unstarted(batch_case: dict[str, Any]) -> None:
    assert batch_case["result"]["not_started"] == ["one", "two"]


@then("preflight rejects the manifest")
def rejected(batch_case: dict[str, Any]) -> None:
    assert isinstance(batch_case["error"], ConfigurationError)


@then("no browser client is constructed")
def no_browser(batch_case: dict[str, Any]) -> None:
    batch_case["client"].assert_not_called()
