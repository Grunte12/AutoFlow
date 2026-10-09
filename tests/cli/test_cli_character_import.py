from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner

from gflow_cli.api.character import Character
from gflow_cli.api.transports.native_character import NativeCharacterReadback
from gflow_cli.cli_character import character

PROJECT = "a0000000-0000-4000-8000-000000000001"
ENTITY = "b0000000-0000-4000-8000-000000000001"
WORKFLOW = "c0000000-0000-4000-8000-000000000001"
MEDIA = "d0000000-0000-4000-8000-000000000001"
OPERATION = "e0000000-0000-4000-8000-000000000001"


def _sheet(path: Path, *, valid: bool = True) -> Path:
    header = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\x00" if valid else b"not an image"
    path.write_bytes(header)
    return path


def _result() -> SimpleNamespace:
    character_dto = Character(
        entity_id=ENTITY,
        display_name="Momo",
        project_id=PROJECT,
        workflow_ids=(WORKFLOW,),
        voice=None,
        personality=None,
        thumbnail_media_id=MEDIA,
    )
    return SimpleNamespace(
        readback=NativeCharacterReadback(
            character=character_dto,
            workflow_media_bindings=((WORKFLOW, MEDIA),),
        ),
        source_sha256="a" * 64,
    )


def test_character_import_json_returns_only_stable_ids_and_source_hash(tmp_path: Path) -> None:
    sheet = _sheet(tmp_path / "Momo.png")
    recorder = MagicMock()
    result = _result()
    service = AsyncMock(return_value=result)
    with (
        patch("gflow_cli.cli_character.get_settings", return_value=SimpleNamespace(headless=True)),
        patch("gflow_cli.cli_character._resolve_profile", return_value="default"),
        patch("gflow_cli.cli_character._make_provider_dir", return_value=tmp_path / "profile"),
        patch("gflow_cli.cli_character.FlowApiClient") as client_factory,
        patch("gflow_cli.cli_character.OperationRecorder.open", return_value=recorder),
        patch("gflow_cli.services.character_import.character_import", new=service),
    ):
        client = AsyncMock()
        client_context = MagicMock()
        client_context.__aenter__ = AsyncMock(return_value=client)
        client_context.__aexit__ = AsyncMock(return_value=False)
        client_factory.return_value = client_context

        cli_result = CliRunner().invoke(
            character,
            [
                "import",
                "--project",
                PROJECT,
                "--name",
                "Momo",
                "--sheet",
                str(sheet),
                "--operation-id",
                OPERATION,
                "--personality",
                "gentle",
                "--json",
            ],
        )

    assert cli_result.exit_code == 0, cli_result.output
    output = json.loads(cli_result.output)
    assert output["status"] == "ok"
    assert output["character"]["entity_id"] == ENTITY
    assert output["workflow_media_bindings"] == [{"workflow_id": WORKFLOW, "media_id": MEDIA}]
    assert output["source_sha256"] == "a" * 64
    assert str(sheet.resolve()) not in cli_result.output

    kwargs = service.await_args.kwargs
    assert kwargs["profile_name"] == "default"
    assert kwargs["project_id"] == PROJECT
    assert kwargs["name"] == "Momo"
    assert kwargs["sheet"] == sheet.resolve()
    assert kwargs["personality"] == "gentle"
    assert kwargs["operation_id"] == OPERATION
    recorder.close.assert_called_once()


def test_character_import_requires_an_explicit_operation_id(tmp_path: Path) -> None:
    sheet = _sheet(tmp_path / "Momo.png")
    with patch("gflow_cli.cli_character.FlowApiClient") as client_factory:
        result = CliRunner().invoke(
            character,
            ["import", "--project", PROJECT, "--name", "Momo", "--sheet", str(sheet)],
        )

    assert result.exit_code == 2
    assert "--operation-id" in result.output
    client_factory.assert_not_called()


@pytest.mark.parametrize(
    ("project", "operation"),
    [("not-a-uuid", OPERATION), (PROJECT, "not-a-uuid")],
)
def test_character_import_rejects_bad_ids_before_browser_start(
    tmp_path: Path, project: str, operation: str
) -> None:
    sheet = _sheet(tmp_path / "Momo.png")
    with patch("gflow_cli.cli_character.FlowApiClient") as client_factory:
        result = CliRunner().invoke(
            character,
            [
                "import",
                "--project",
                project,
                "--name",
                "Momo",
                "--sheet",
                str(sheet),
                "--operation-id",
                operation,
            ],
        )

    assert result.exit_code == 2
    assert "canonical UUID" in result.output
    client_factory.assert_not_called()


def test_character_import_rejects_non_image_before_profile_start(tmp_path: Path) -> None:
    sheet = _sheet(tmp_path / "Momo.png", valid=False)
    with (
        patch("gflow_cli.cli_character._resolve_profile") as resolve_profile,
        patch("gflow_cli.cli_character.FlowApiClient") as client_factory,
    ):
        result = CliRunner().invoke(
            character,
            [
                "import",
                "--project",
                PROJECT,
                "--name",
                "Momo",
                "--sheet",
                str(sheet),
                "--operation-id",
                OPERATION,
            ],
        )

    assert result.exit_code == 2
    assert "supported image" in result.output
    resolve_profile.assert_not_called()
    client_factory.assert_not_called()
