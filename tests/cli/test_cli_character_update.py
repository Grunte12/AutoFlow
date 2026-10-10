from __future__ import annotations

import inspect
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner

from gflow_cli.cli_character import character
from gflow_cli.mcp import tools as mcp_tools

PROJECT = "a0000000-0000-4000-8000-000000000001"
ENTITY = "b0000000-0000-4000-8000-000000000001"
OPERATION = "e0000000-0000-4000-8000-000000000001"


def _image(path: Path, *, valid: bool = True) -> Path:
    header = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\x00" if valid else b"not an image"
    path.write_bytes(header)
    return path


def _client_context() -> tuple[MagicMock, AsyncMock]:
    client = AsyncMock()
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=client)
    context.__aexit__ = AsyncMock(return_value=False)
    return context, client


def test_character_update_images_json_uses_shared_service_without_exposing_paths(
    tmp_path: Path,
) -> None:
    portrait = _image(tmp_path / "portrait.png")
    full_body = _image(tmp_path / "full-body.png")
    images = {
        "portrait": {
            "workflow_id": "c0000000-0000-4000-8000-000000000001",
            "media_id": "d0000000-0000-4000-8000-000000000001",
            "source_sha256": "a" * 64,
        },
        "full_body": {
            "workflow_id": "c0000000-0000-4000-8000-000000000002",
            "media_id": "d0000000-0000-4000-8000-000000000002",
            "source_sha256": "b" * 64,
        },
    }
    service = AsyncMock(return_value={"status": "ok", "images": images})
    recorder = MagicMock()
    settings = SimpleNamespace(headless=True)
    context, _client = _client_context()

    with (
        patch("gflow_cli.cli_character.get_settings", return_value=settings),
        patch("gflow_cli.cli_character._resolve_profile", return_value="testprofile"),
        patch("gflow_cli.cli_character._make_provider_dir", return_value=tmp_path / "profile"),
        patch("gflow_cli.cli_character.FlowApiClient", return_value=context),
        patch("gflow_cli.cli_character.OperationRecorder.open", return_value=recorder),
        patch("gflow_cli.services.character_update.character_update_images", new=service),
    ):
        result = CliRunner().invoke(
            character,
            [
                "update-images",
                "--project",
                PROJECT,
                "--entity-id",
                ENTITY,
                "--operation-id",
                OPERATION,
                "--portrait",
                str(portrait),
                "--full-body",
                str(full_body),
                "--profile",
                "testprofile",
                "--json",
            ],
        )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload == {
        "status": "ok",
        "project": PROJECT,
        "entity_id": ENTITY,
        "images": images,
    }
    assert str(portrait.resolve()) not in result.output
    assert str(full_body.resolve()) not in result.output
    kwargs = service.await_args.kwargs
    assert kwargs["profile_name"] == "testprofile"
    assert kwargs["project_id"] == PROJECT
    assert kwargs["entity_id"] == ENTITY
    assert kwargs["operation_id"] == OPERATION
    assert kwargs["portrait"] == portrait.resolve()
    assert kwargs["full_body"] == full_body.resolve()
    recorder.close.assert_called_once()


def test_character_update_images_requires_one_slot_before_profile_or_client() -> None:
    with (
        patch("gflow_cli.cli_character._resolve_profile") as resolve_profile,
        patch("gflow_cli.cli_character.FlowApiClient") as client_factory,
    ):
        result = CliRunner().invoke(
            character,
            [
                "update-images",
                "--project",
                PROJECT,
                "--entity-id",
                ENTITY,
                "--operation-id",
                OPERATION,
            ],
        )

    assert result.exit_code == 2
    assert "Provide --portrait and/or --full-body" in result.output
    resolve_profile.assert_not_called()
    client_factory.assert_not_called()


@pytest.mark.parametrize(
    ("entity_id", "image_valid", "expected"),
    [
        ("not-a-uuid", True, "canonical UUID"),
        (ENTITY, False, "supported image"),
    ],
)
def test_character_update_images_rejects_bad_id_or_file_before_profile_and_client(
    tmp_path: Path,
    entity_id: str,
    image_valid: bool,
    expected: str,
) -> None:
    portrait = _image(tmp_path / "portrait.png", valid=image_valid)
    with (
        patch("gflow_cli.cli_character._resolve_profile") as resolve_profile,
        patch("gflow_cli.cli_character.FlowApiClient") as client_factory,
    ):
        result = CliRunner().invoke(
            character,
            [
                "update-images",
                "--project",
                PROJECT,
                "--entity-id",
                entity_id,
                "--operation-id",
                OPERATION,
                "--portrait",
                str(portrait),
            ],
        )

    assert result.exit_code == 2
    assert expected in result.output
    resolve_profile.assert_not_called()
    client_factory.assert_not_called()


def test_character_update_images_cli_options_have_mcp_counterparts() -> None:
    command = character.commands["update-images"]
    cli_params = {param.name for param in command.params if param.name}
    tool_params = set(inspect.signature(mcp_tools.gflow_character_update_images).parameters)
    cli_to_mcp = {
        "project_id": "project",
        "entity_id": "entity_id",
        "operation_id": "operation_id",
        "portrait_path": "portrait_path",
        "full_body_path": "full_body_path",
        "profile": "profile",
    }

    assert set(cli_to_mcp) <= cli_params
    assert set(cli_to_mcp.values()) <= tool_params
    assert "as_json" in cli_params  # output formatting is a CLI-only option
