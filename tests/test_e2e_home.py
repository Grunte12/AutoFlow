"""Offline checks for explicit E2E home selection."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from gflow_cli import config
from tests.e2e import conftest as e2e_fixtures

_PROFILE_ENV = "GFLOW_CLI_E2E_PROFILE"
_E2E_HOME_ENV = "GFLOW_CLI_E2E_HOME"
_CLI_HOME_ENV = "GFLOW_CLI_HOME"


def _enter_profile_fixture(monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    return e2e_fixtures.e2e_profile_dir.__wrapped__(monkeypatch)


def _read_child_env(tmp_path: Path) -> dict[str, str]:
    env_fixture = e2e_fixtures.e2e_env.__wrapped__(tmp_path)
    env = next(env_fixture)
    env_fixture.close()
    return env


def test_missing_override_uses_normal_home_and_child_keeps_outputs_isolated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    profile_name = "safe-test-profile"
    normal_home = tmp_path / "normal-home"
    profile_dir = normal_home / f"profile_{profile_name}"
    profile_dir.mkdir(parents=True)
    isolated_home = tmp_path / "pytest-isolated-home"

    monkeypatch.delenv(_E2E_HOME_ENV, raising=False)
    monkeypatch.setenv(_PROFILE_ENV, profile_name)
    monkeypatch.setenv(_CLI_HOME_ENV, str(isolated_home))

    class NormalHomeSettings:
        def __init__(self, **kwargs: Any) -> None:
            assert kwargs == {"_env_file": None}
            # The fixture must drop pytest's home redirect before resolving defaults.
            assert _CLI_HOME_ENV not in os.environ
            self.home = normal_home

        def profile_subdir(self, name: str) -> Path:
            return self.home / f"profile_{name}"

    monkeypatch.setattr(config, "Settings", NormalHomeSettings)
    profile_fixture = _enter_profile_fixture(monkeypatch)
    try:
        assert next(profile_fixture) == profile_dir
        assert os.environ[_CLI_HOME_ENV] == str(normal_home)
    finally:
        profile_fixture.close()

    child_env = _read_child_env(tmp_path)
    assert _CLI_HOME_ENV not in child_env
    assert child_env["GFLOW_CLI_DB_PATH"] == str(tmp_path / "gflow.db")
    assert child_env["GFLOW_CLI_OUTPUT_DIR"] == str(tmp_path / "out")
    assert Path(child_env["GFLOW_CLI_DB_PATH"]).parent == tmp_path
    assert Path(child_env["GFLOW_CLI_OUTPUT_DIR"]).parent == tmp_path


def test_explicit_absolute_home_selects_profile_and_child_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    profile_name = "explicit-test-profile"
    home = (tmp_path / "authenticated-home").resolve()
    profile_dir = home / f"profile_{profile_name}"
    profile_dir.mkdir(parents=True)

    monkeypatch.setenv(_PROFILE_ENV, profile_name)
    monkeypatch.setenv(_E2E_HOME_ENV, str(home))
    monkeypatch.setenv(_CLI_HOME_ENV, str(tmp_path / "pytest-isolated-home"))

    profile_fixture = _enter_profile_fixture(monkeypatch)
    try:
        assert next(profile_fixture) == profile_dir
        assert os.environ[_CLI_HOME_ENV] == str(home)
    finally:
        profile_fixture.close()

    child_env = _read_child_env(tmp_path)
    assert child_env[_CLI_HOME_ENV] == str(home)
    assert child_env["GFLOW_CLI_PROFILE"] == profile_name
    assert child_env["GFLOW_CLI_DB_PATH"] == str(tmp_path / "gflow.db")
    assert child_env["GFLOW_CLI_OUTPUT_DIR"] == str(tmp_path / "out")
    assert Path(child_env["GFLOW_CLI_DB_PATH"]).parent == tmp_path
    assert Path(child_env["GFLOW_CLI_OUTPUT_DIR"]).parent == tmp_path
    assert Path(child_env["GFLOW_CLI_DB_PATH"]).parent != home
    assert Path(child_env["GFLOW_CLI_OUTPUT_DIR"]).parent != home


@pytest.mark.parametrize("invalid_kind", ["relative", "nonexistent"])
def test_invalid_explicit_home_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, invalid_kind: str
) -> None:
    if invalid_kind == "relative":
        invalid_home = "relative-auth-home"
    else:
        invalid_home = str(tmp_path / "does-not-exist")
    monkeypatch.setenv(_E2E_HOME_ENV, invalid_home)

    with pytest.raises(
        pytest.fail.Exception,
        match="GFLOW_CLI_E2E_HOME must be an existing absolute directory",
    ):
        e2e_fixtures._explicit_e2e_home()
