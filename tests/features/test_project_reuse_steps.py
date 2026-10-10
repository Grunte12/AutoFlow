from pathlib import Path

from pytest_bdd import given, scenarios, then, when

from gflow_cli.errors import ConfigurationError
from gflow_cli.services.project_context import ProjectBinding, resolve_project, save_binding

scenarios("project_reuse.feature")
PROJECT = "11111111-1111-4111-8111-111111111111"


@given("an existing project is bound to this profile")
def bound(tmp_path: Path) -> None:
    save_binding(tmp_path, ProjectBinding(project=PROJECT))


@given("the profile binding is corrupted")
def corrupt(tmp_path: Path) -> None:
    (tmp_path / ".gflow_project.json").write_text("broken")


@when("a generation omits the project", target_fixture="routing")
def route(tmp_path: Path) -> object:
    try:
        return resolve_project(tmp_path, None, None)
    except ConfigurationError as exc:
        return exc


@then("the selected project is reused")
def reused(routing: object) -> None:
    assert routing == PROJECT


@then("routing fails before project creation")
def refused(routing: object) -> None:
    assert isinstance(routing, ConfigurationError)
