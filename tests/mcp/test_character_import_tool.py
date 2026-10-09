from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gflow_cli.api.character import Character
from gflow_cli.api.transports.native_character import NativeCharacterReadback
from gflow_cli.mcp import tools as mcp_tools

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
    character = Character(
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
            character=character,
            workflow_media_bindings=((WORKFLOW, MEDIA),),
        ),
        source_sha256="b" * 64,
    )


def _client_context() -> tuple[MagicMock, AsyncMock]:
    client = AsyncMock()
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=client)
    context.__aexit__ = AsyncMock(return_value=False)
    return context, client


@pytest.mark.asyncio
async def test_character_import_returns_stable_ids_hash_and_no_local_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sheet = _sheet(tmp_path / "Momo.png")
    service = AsyncMock(return_value=_result())
    context, _client = _client_context()
    recorder = MagicMock()
    settings = MagicMock()
    settings.profile_subdir.return_value = tmp_path / "profile"
    settings.headless = True
    monkeypatch.setattr(mcp_tools, "_resolve_and_validate_profile", lambda _profile: "testprofile")
    monkeypatch.setattr(mcp_tools, "get_settings", lambda: settings)

    with (
        patch.object(mcp_tools, "FlowApiClient", return_value=context),
        patch("gflow_cli.data.recorder.OperationRecorder.open", return_value=recorder),
        patch("gflow_cli.services.character_import.character_import", new=service),
    ):
        result = await mcp_tools.gflow_character_import(
            project=PROJECT,
            name="Momo",
            sheet_path=str(sheet),
            operation_id=OPERATION,
            personality="gentle",
        )

    assert result["status"] == "ok"
    assert result["character"]["entity_id"] == ENTITY
    assert result["workflow_media_bindings"] == [{"workflow_id": WORKFLOW, "media_id": MEDIA}]
    assert result["source_sha256"] == "b" * 64
    assert str(sheet.resolve()) not in repr(result)
    assert "https://" not in repr(result)
    kwargs = service.await_args.kwargs
    assert kwargs["project_id"] == PROJECT
    assert kwargs["operation_id"] == OPERATION
    assert kwargs["sheet"] == sheet.resolve()
    assert kwargs["personality"] == "gentle"
    recorder.close.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("project", "operation"),
    [(PROJECT, "not-a-uuid"), ("not-a-uuid", OPERATION)],
)
async def test_character_import_rejects_noncanonical_ids_before_browser(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, project: str, operation: str
) -> None:
    sheet = _sheet(tmp_path / "Momo.png")
    monkeypatch.setattr(
        mcp_tools,
        "_resolve_and_validate_profile",
        lambda _profile: pytest.fail("profile resolution must follow input validation"),
    )
    with patch.object(mcp_tools, "FlowApiClient") as client_factory:
        result = await mcp_tools.gflow_character_import(
            project=project,
            name="Momo",
            sheet_path=str(sheet),
            operation_id=operation,
        )

    assert result["status"] == "error"
    assert result["error"]["status"] == 400
    client_factory.assert_not_called()


@pytest.mark.asyncio
async def test_character_import_rejects_invalid_image_before_profile_or_browser(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sheet = _sheet(tmp_path / "not-an-image.png", valid=False)
    monkeypatch.setattr(
        mcp_tools,
        "_resolve_and_validate_profile",
        lambda _profile: pytest.fail("profile resolution must follow image validation"),
    )
    with patch.object(mcp_tools, "FlowApiClient") as client_factory:
        result = await mcp_tools.gflow_character_import(
            project=PROJECT,
            name="Momo",
            sheet_path=str(sheet),
            operation_id=OPERATION,
        )

    assert result["status"] == "error"
    assert result["error"]["status"] == 400
    assert str(sheet.resolve()) not in repr(result)
    client_factory.assert_not_called()
