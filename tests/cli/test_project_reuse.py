from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from click.testing import CliRunner

from gflow_cli import cli_video
from gflow_cli.cli_project import project
from gflow_cli.services.project_context import ProjectBinding, save_binding

PROJECT = "11111111-1111-4111-8111-111111111111"


@pytest.mark.parametrize("mode", ["t2v", "r2v"])
async def test_video_runner_reuses_project_before_implicit_title(tmp_path: Path, mode: str) -> None:
    save_binding(tmp_path, ProjectBinding(project=PROJECT))
    kwargs = dict(
        profile_name="test", profile_dir=tmp_path, prompt="scene", aspect="9:16", out_dir=None
    )
    with patch.object(cli_video, "_generate_and_report", new_callable=AsyncMock) as generate:
        if mode == "t2v":
            await cli_video._run_t2v(**kwargs)
        else:
            await cli_video._run_r2v(**kwargs, refs=(str(tmp_path / "reference.png"),))
    assert generate.await_args.kwargs["project_id"] == PROJECT


def test_cli_context_is_offline(tmp_path: Path) -> None:
    save_binding(tmp_path, ProjectBinding(project=PROJECT))
    with (
        patch("gflow_cli.cli_project._resolve_profile", return_value="test"),
        patch("gflow_cli.cli_project._make_provider_dir", return_value=tmp_path),
        patch("gflow_cli.cli_project.FlowApiClient") as browser,
    ):
        result = CliRunner().invoke(project, ["context", "--json"])
    assert result.exit_code == 0
    assert PROJECT in result.output
    browser.assert_not_called()
