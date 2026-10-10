from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from gflow_cli.api.character import Character
from gflow_cli.errors import ConfigurationError
from gflow_cli.services.project_context import (
    ProjectBinding,
    bind_project,
    load_binding,
    resolve_project,
    save_binding,
)

PROJECT = "11111111-1111-4111-8111-111111111111"
OTHER = "22222222-2222-4222-8222-222222222222"


def test_missing_binding_keeps_old_behavior(tmp_path: Path) -> None:
    assert load_binding(tmp_path) is None
    assert resolve_project(tmp_path, None, None) is None


def test_round_trip_and_profile_isolation(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    binding = ProjectBinding(project=PROJECT)
    save_binding(first, binding)
    assert load_binding(first) == binding
    assert resolve_project(first, None, None) == PROJECT
    assert load_binding(second) is None


@pytest.mark.parametrize("explicit,title,expected", [(OTHER, None, OTHER), (None, "new", None)])
def test_explicit_request_wins(
    tmp_path: Path, explicit: str | None, title: str | None, expected: str | None
) -> None:
    save_binding(tmp_path, ProjectBinding(project=PROJECT))
    assert resolve_project(tmp_path, explicit, title) == expected


@pytest.mark.parametrize(
    "raw", ["{", '{"version":2,"project":"' + PROJECT + '"}', '{"version":1,"project":"../bad"}']
)
def test_malformed_binding_fails_closed(tmp_path: Path, raw: str) -> None:
    (tmp_path / ".gflow_project.json").write_text(raw)
    with pytest.raises(ConfigurationError):
        resolve_project(tmp_path, None, None)


def test_rebind_requires_explicit_replace(tmp_path: Path) -> None:
    original = ProjectBinding(project=PROJECT)
    save_binding(tmp_path, original)
    save_binding(tmp_path, original)
    with pytest.raises(ConfigurationError):
        save_binding(tmp_path, ProjectBinding(project=OTHER))
    assert load_binding(tmp_path) == original
    save_binding(tmp_path, ProjectBinding(project=OTHER), replace=True)
    assert resolve_project(tmp_path, None, None) == OTHER


def test_invalid_binding_never_writes(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        ProjectBinding(project="not-an-id")
    assert not (tmp_path / ".gflow_project.json").exists()


CHARACTER = Character(
    entity_id=OTHER,
    display_name="Hero",
    project_id=PROJECT,
    workflow_ids=("workflow",),
    voice=None,
    personality=None,
    thumbnail_media_id=None,
)


@pytest.mark.parametrize(
    "characters", [[], [CHARACTER, CHARACTER], [replace(CHARACTER, workflow_ids=())]]
)
async def test_invalid_character_selection_preserves_binding(tmp_path: Path, characters) -> None:
    original = ProjectBinding(project=PROJECT)
    save_binding(tmp_path, original)
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.list_characters.return_value = characters
    with patch("gflow_cli.services.project_context.FlowApiClient", return_value=client):
        with pytest.raises(ConfigurationError):
            await bind_project(tmp_path, PROJECT, ("Hero",), replace=True)
    assert load_binding(tmp_path) == original
    client.create_project.assert_not_called()


async def test_bind_only_selected_characters_without_creation(tmp_path: Path) -> None:
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.list_characters.return_value = [CHARACTER, replace(CHARACTER, display_name="Other")]
    with patch("gflow_cli.services.project_context.FlowApiClient", return_value=client):
        binding = await bind_project(tmp_path, PROJECT, ("Hero",))
    assert len(binding.characters) == 1
    assert binding.characters[0].name == "Hero"
    assert str(binding.characters[0].entity_id) == OTHER
    client.list_characters.assert_awaited_once_with(PROJECT)
    client.create_project.assert_not_called()
