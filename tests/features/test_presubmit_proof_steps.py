from typing import Any

from pytest_bdd import given, scenarios, then, when

from gflow_cli.errors import (
    ConfigurationError,
    GFlowError,
    PreSubmitConfigurationError,
    ProblemDetails,
)

scenarios("presubmit_proof.feature")

SerializedSurfaces = tuple[ProblemDetails, dict[str, Any]]


@given("a positively witnessed duration refusal", target_fixture="error")
def refusal() -> PreSubmitConfigurationError:
    return PreSubmitConfigurationError(setting="duration", requested_value=10)


@given("an ordinary configuration error", target_fixture="error")
def ordinary() -> ConfigurationError:
    return ConfigurationError("ordinary")


@when("the error is serialized for CLI and MCP", target_fixture="surfaces")
def serialize(error: GFlowError) -> SerializedSurfaces:
    from gflow_cli.mcp.tools import _gflow_error_dict

    return error.to_problem_details(), _gflow_error_dict(error)


@then("both surfaces say the request was not submitted")
def proven(surfaces: SerializedSurfaces) -> None:
    cli, mcp = surfaces
    assert cli["submission_state"] == "not_submitted"
    assert cli["stage"] == "configuration"
    assert cli["setting"] == "duration"
    assert cli["requested_value"] == 10
    assert cli["capability"] == "unverified"
    assert cli["safe_next_action"] == "inspect_controls"
    assert {key: mcp[key] for key in cli} == cli
    assert mcp["retryable"] is False


@then("the CLI keeps exit code 11")
def exit_compatible(error: GFlowError) -> None:
    from gflow_cli._cli_helpers import _exit_code_for

    assert _exit_code_for(error) == 11


@then("neither surface claims a pre-submit proof")
def uncertain(surfaces: SerializedSurfaces) -> None:
    proof_fields = {
        "submission_state",
        "stage",
        "setting",
        "requested_value",
        "capability",
        "safe_next_action",
    }
    assert all(proof_fields.isdisjoint(surface) for surface in surfaces)
