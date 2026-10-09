"""Only transport-owned positive refusals carry pre-submit proof."""

import json
from typing import Any

import pytest

from gflow_cli.errors import (
    EXIT_CODE_MAP,
    ConfigurationError,
    PreSubmitConfigurationError,
    is_retryable,
)


def test_presubmit_configuration_has_safe_structured_proof() -> None:
    error = PreSubmitConfigurationError(
        "The requested duration cannot be selected before generation.",
        setting="duration",
        requested_value=6,
        capability="unsupported",
    )
    problem = error.to_problem_details()
    assert problem["submission_state"] == "not_submitted"
    assert problem["stage"] == "configuration"
    assert problem["setting"] == "duration"
    assert problem["requested_value"] == 6
    assert problem["capability"] == "unsupported"
    assert problem["safe_next_action"] == "inspect_controls"
    assert isinstance(error, ConfigurationError)
    assert next(code for cls, code in EXIT_CODE_MAP.items() if isinstance(error, cls)) == 11
    assert is_retryable(error) is False


def test_ordinary_configuration_error_has_no_submission_proof() -> None:
    problem = ConfigurationError("Invalid configuration").to_problem_details()
    assert not {
        "submission_state",
        "stage",
        "setting",
        "requested_value",
        "capability",
        "safe_next_action",
    }.intersection(problem)


@pytest.mark.parametrize("value", [4, 6, 8, 10, 6.0])
def test_finite_numbers_remain_numbers(value: int | float) -> None:
    error = PreSubmitConfigurationError(setting="duration", requested_value=value)
    assert error.to_problem_details()["requested_value"] == value
    assert type(error.to_problem_details()["requested_value"]) is type(value)


@pytest.mark.parametrize(
    ("setting", "value"),
    [("model", "veo-lite"), ("model", "omni-flash"), ("references", "local_images")],
)
def test_known_enums_are_allowed(setting: str, value: str) -> None:
    error = PreSubmitConfigurationError(setting=setting, requested_value=value)
    assert error.to_problem_details()["requested_value"] == value


@pytest.mark.parametrize(
    ("setting", "value"),
    [("model", 6), ("model", "unknown-model"), ("references", "veo-lite")],
)
def test_values_must_match_the_setting_allowlist(setting: str, value: int | str) -> None:
    with pytest.raises(ValueError):
        PreSubmitConfigurationError(setting=setting, requested_value=value)


def test_presubmit_error_does_not_enable_incident_capture() -> None:
    from gflow_cli.config import Settings
    from gflow_cli.diagnostics import IncidentRecorder

    recorder = IncidentRecorder(Settings(incident_capture=True, _env_file=None))
    error = PreSubmitConfigurationError(setting="duration", requested_value=6)
    assert recorder.should_capture(error) is False
    assert recorder.should_capture(ConfigurationError("Invalid configuration")) is False


@pytest.mark.parametrize(
    "value",
    [
        "private prompt text",
        "/Users/private/canonical.png",
        "https://example.com/image?token=secret",
        "Bearer secret",
        True,
        None,
        float("nan"),
        float("inf"),
        {"prompt": "secret"},
        ["secret"],
    ],
)
def test_raw_or_nonprimitive_requested_values_are_rejected(value: Any) -> None:
    with pytest.raises(ValueError) as raised:
        PreSubmitConfigurationError(setting="duration", requested_value=value)
    assert "secret" not in str(raised.value)
    assert "/Users/" not in str(raised.value)
    assert "https://" not in str(raised.value)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("setting", "prompt"),
        ("setting", "https://example.com?secret"),
        ("capability", "supported"),
        ("capability", "secret"),
        ("safe_next_action", "retry"),
        ("safe_next_action", "/Users/private/secret"),
        ("submission_state", "submitted"),
        ("stage", "secret"),
        ("retryable", True),
    ],
)
def test_invalid_safe_fields_cannot_be_emitted(field: str, value: Any) -> None:
    arguments: dict[str, Any] = {"setting": "duration", "requested_value": 6, field: value}
    with pytest.raises((ValueError, TypeError)):
        PreSubmitConfigurationError(**arguments)


def test_safe_fields_do_not_reflect_raw_details() -> None:
    error = PreSubmitConfigurationError(
        "private prompt /Users/private/image.png https://example.com?token=secret",
        setting="references",
        requested_value=2,
    )
    problem = error.to_problem_details()
    safe_fields = {
        key: problem[key]
        for key in (
            "submission_state",
            "stage",
            "setting",
            "requested_value",
            "capability",
            "safe_next_action",
        )
    }
    encoded = json.dumps(safe_fields)
    assert "private" not in encoded
    assert "secret" not in encoded
    assert "https://" not in encoded
    assert "/Users/" not in encoded
