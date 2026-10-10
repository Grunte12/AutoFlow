from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from gflow_cli.data.store import DataStore
from gflow_cli.mcp import tools
from gflow_cli.services.project_context import ProjectBinding, save_binding
from gflow_cli.worker.queue import QueueRepository

PROJECT = "11111111-1111-4111-8111-111111111111"
OTHER = "22222222-2222-4222-8222-222222222222"


@pytest.mark.parametrize("kind", ["t2i", "i2i", "t2v", "i2v", "r2v"])
async def test_queue_snapshots_project_before_rebinding(tmp_path: Path, kind: str) -> None:
    save_binding(tmp_path, ProjectBinding(project=PROJECT))
    settings = SimpleNamespace(
        profile_subdir=lambda _: tmp_path, resolved_db_path=lambda: tmp_path / "catalog.db"
    )
    with patch.object(tools, "get_settings", return_value=settings):
        result = await tools._run_generation_task(
            profile="test", task_type=kind, payload={"prompt": "scene"}, wait=False
        )
    save_binding(tmp_path, ProjectBinding(project=OTHER), replace=True)
    with DataStore.open(tmp_path / "catalog.db") as store:
        task = QueueRepository(store).get_task(result["task_id"])
    assert task is not None
    assert task.payload["project_id"] == PROJECT


async def test_context_is_offline_and_preserves_ids(tmp_path: Path) -> None:
    save_binding(tmp_path, ProjectBinding(project=PROJECT))
    with (
        patch.object(tools, "_resolve_and_validate_profile", return_value="test"),
        patch.object(
            tools, "get_settings", return_value=SimpleNamespace(profile_subdir=lambda _: tmp_path)
        ),
        patch.object(tools, "FlowApiClient") as browser,
    ):
        result = await tools.gflow_project_context(profile="test")
    assert result["binding"]["project"] == PROJECT
    assert result["source"] == "local_binding"
    browser.assert_not_called()


async def test_rename_uses_existing_cli_readback(tmp_path: Path) -> None:
    with (
        patch.object(tools, "_resolve_and_validate_profile", return_value="test"),
        patch.object(
            tools, "get_settings", return_value=SimpleNamespace(profile_subdir=lambda _: tmp_path)
        ),
        patch("gflow_cli.cli_project.run_rename_project", new_callable=AsyncMock) as rename,
    ):
        result = await tools.gflow_project_rename(PROJECT, "Brand", profile="test")
    rename.assert_awaited_once_with("test", tmp_path, PROJECT, "Brand")
    assert result["status"] == "ok"


@pytest.mark.parametrize("project,title", [("bad", "Brand"), (PROJECT, " ")])
async def test_rename_refuses_invalid_input_without_browser(project: str, title: str) -> None:
    with patch("gflow_cli.cli_project.run_rename_project", new_callable=AsyncMock) as rename:
        result = await tools.gflow_project_rename(project, title)
    assert result["status"] == "error"
    rename.assert_not_called()
