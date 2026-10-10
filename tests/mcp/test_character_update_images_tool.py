from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gflow_cli.mcp import tools as mcp_tools

PROJECT = "a0000000-0000-4000-8000-000000000001"
ENTITY = "b0000000-0000-4000-8000-000000000001"
WORKFLOW_PORTRAIT = "c0000000-0000-4000-8000-000000000001"
MEDIA_PORTRAIT = "d0000000-0000-4000-8000-000000000001"
WORKFLOW_FULL_BODY = "c0000000-0000-4000-8000-000000000002"
MEDIA_FULL_BODY = "d0000000-0000-4000-8000-000000000002"
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


@pytest.mark.asyncio
async def test_character_update_images_returns_only_verified_image_bindings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    portrait = _image(tmp_path / "portrait.png")
    full_body = _image(tmp_path / "full-body.png")
    images = {
        "portrait": {
            "workflow_id": WORKFLOW_PORTRAIT,
            "media_id": MEDIA_PORTRAIT,
            "source_sha256": "a" * 64,
        },
        "full_body": {
            "workflow_id": WORKFLOW_FULL_BODY,
            "media_id": MEDIA_FULL_BODY,
            "source_sha256": "b" * 64,
        },
    }
    service = AsyncMock(return_value={"status": "ok", "images": images})
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
        patch.dict(
            sys.modules,
            {
                "gflow_cli.services.character_update": SimpleNamespace(
                    character_update_images=service
                )
            },
        ),
    ):
        result = await mcp_tools.gflow_character_update_images(
            project=PROJECT,
            entity_id=ENTITY,
            operation_id=OPERATION,
            portrait_path=str(portrait),
            full_body_path=str(full_body),
        )

    assert result == {
        "status": "ok",
        "project": PROJECT,
        "entity_id": ENTITY,
        "images": images,
    }
    assert str(portrait.resolve()) not in repr(result)
    assert str(full_body.resolve()) not in repr(result)
    assert "https://" not in repr(result)
    kwargs = service.await_args.kwargs
    assert kwargs["project_id"] == PROJECT
    assert kwargs["entity_id"] == ENTITY
    assert kwargs["operation_id"] == OPERATION
    assert kwargs["portrait"] == portrait.resolve()
    assert kwargs["full_body"] == full_body.resolve()
    recorder.close.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("project", "entity_id", "operation_id"),
    [
        ("not-a-uuid", ENTITY, OPERATION),
        (PROJECT, "not-a-uuid", OPERATION),
        (PROJECT, ENTITY, "not-a-uuid"),
    ],
)
async def test_character_update_images_rejects_noncanonical_ids_before_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    project: str,
    entity_id: str,
    operation_id: str,
) -> None:
    portrait = _image(tmp_path / "portrait.png")
    monkeypatch.setattr(
        mcp_tools,
        "_resolve_and_validate_profile",
        lambda _profile: pytest.fail("profile resolution must follow input validation"),
    )
    with patch.object(mcp_tools, "FlowApiClient") as client_factory:
        result = await mcp_tools.gflow_character_update_images(
            project=project,
            entity_id=entity_id,
            operation_id=operation_id,
            portrait_path=str(portrait),
            full_body_path=None,
        )

    assert result["status"] == "error"
    assert result["error"]["status"] == 400
    client_factory.assert_not_called()


@pytest.mark.asyncio
async def test_character_update_images_requires_at_least_one_image_before_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        mcp_tools,
        "_resolve_and_validate_profile",
        lambda _profile: pytest.fail("profile resolution must follow input validation"),
    )
    with patch.object(mcp_tools, "FlowApiClient") as client_factory:
        result = await mcp_tools.gflow_character_update_images(
            project=PROJECT,
            entity_id=ENTITY,
            operation_id=OPERATION,
            portrait_path=None,
            full_body_path=None,
        )

    assert result["status"] == "error"
    assert result["error"]["status"] == 400
    client_factory.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("image_field", ["portrait_path", "full_body_path"])
async def test_character_update_images_rejects_invalid_image_before_profile_or_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, image_field: str
) -> None:
    invalid = _image(tmp_path / "invalid.png", valid=False)
    monkeypatch.setattr(
        mcp_tools,
        "_resolve_and_validate_profile",
        lambda _profile: pytest.fail("profile resolution must follow image validation"),
    )
    with (
        patch.object(mcp_tools, "FlowApiClient") as client_factory,
        patch("gflow_cli.data.recorder.OperationRecorder.open") as recorder_open,
    ):
        result = await mcp_tools.gflow_character_update_images(
            project=PROJECT,
            entity_id=ENTITY,
            operation_id=OPERATION,
            **{image_field: str(invalid)},
        )

    assert result["status"] == "error"
    assert result["error"]["status"] == 400
    assert str(invalid.resolve()) not in repr(result)
    client_factory.assert_not_called()
    recorder_open.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("image_field", ["portrait_path", "full_body_path"])
async def test_character_update_images_rejects_missing_file_before_profile_or_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, image_field: str
) -> None:
    missing = tmp_path / "missing.png"
    monkeypatch.setattr(
        mcp_tools,
        "_resolve_and_validate_profile",
        lambda _profile: pytest.fail("profile resolution must follow image validation"),
    )
    with patch.object(mcp_tools, "FlowApiClient") as client_factory:
        result = await mcp_tools.gflow_character_update_images(
            project=PROJECT,
            entity_id=ENTITY,
            operation_id=OPERATION,
            **{image_field: str(missing)},
        )

    assert result["status"] == "error"
    assert result["error"]["status"] == 400
    client_factory.assert_not_called()
