"""Offline contract tests for the no-credit Character picker parity probe."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from scripts.dev.character_picker_parity import (
    compare_generation_specs,
    field_equality,
    observe_request,
    rich_prompt_checks,
    summarize_prompt,
    validate_input,
)


def test_full_spec_only_allows_uuid_slots_measured_varying_in_native_replay() -> None:
    native = [
        None,
        ["media"],
        "model",
        1,
        [3, 5],
        [None] * 4
        + ["11111111-1111-4111-8111-111111111111", "22222222-2222-4222-8222-222222222222"],
    ]
    replay = copy.deepcopy(native)
    replay[5][4] = "33333333-3333-4333-8333-333333333333"
    replay[5][5] = "44444444-4444-4444-8444-444444444444"
    production = copy.deepcopy(replay)
    production[5][4] = "55555555-5555-4555-8555-555555555555"
    result = compare_generation_specs(native, production, replay)
    assert result["all_nonvarying_fields_equal"]
    assert result["production_difference_paths"] == [[5, 4], [5, 5]]
    assert not result["exact_native_production_equal"]
    production[4] = [3, 4]
    assert not compare_generation_specs(native, production, replay)["all_nonvarying_fields_equal"]
    assert not compare_generation_specs(native, production, native)["all_nonvarying_fields_equal"]
    assert not compare_generation_specs(native, [], replay)["all_nonvarying_fields_equal"]
    production = copy.deepcopy(replay)
    production[5][4] = "not-a-uuid"
    assert not compare_generation_specs(native, production, replay)["all_nonvarying_fields_equal"]


def test_observer_accepts_binary_traffic_and_counts_writes() -> None:
    report = {"generation_dispatched": 0, "mutation_dispatched": 0}
    observe_request(
        SimpleNamespace(url="https://example.test/telemetry", post_data_buffer=b"\xff\x8e"), report
    )
    assert report == {"generation_dispatched": 0, "mutation_dispatched": 0}
    observe_request(
        SimpleNamespace(url="https://example.test/data/batchexecute", post_data_buffer=b"MZZa6b"),
        report,
    )
    observe_request(
        SimpleNamespace(url="https://example.test/upload", post_data_buffer=b"\xff"), report
    )
    assert report == {"generation_dispatched": 1, "mutation_dispatched": 1}


def test_input_requires_explicit_existing_refs() -> None:
    raw = {
        "project_id": "11111111-1111-4111-8111-111111111111",
        "prompt": "private prompt fixture",
        "media": [{"id": "22222222-2222-4222-8222-222222222222", "picker_name": "scene.png"}],
        "characters": [{"id": "33333333-3333-4333-8333-333333333333", "name": "Test Character"}],
    }
    parsed = validate_input(raw)
    assert parsed["model_value"].value == "omni_flash"
    assert parsed["aspect_value"].value == "portrait"
    with pytest.raises(ValueError, match="nonempty"):
        validate_input({**raw, "prompt": "  "})
    with pytest.raises(ValueError, match="project_id"):
        validate_input({**raw, "project_id": "private-id"})


def test_prompt_source_resolves_without_copying_text_into_input(tmp_path: Path) -> None:
    source = tmp_path / "request.json"
    source.write_text(json.dumps({"arguments": {"prompt": "external private text"}}))
    raw = {
        "project_id": "11111111-1111-4111-8111-111111111111",
        "prompt_source": {"path": str(source), "keys": ["arguments", "prompt"]},
        "media": [{"id": "22222222-2222-4222-8222-222222222222", "picker_name": "scene.png"}],
        "characters": [{"id": "33333333-3333-4333-8333-333333333333", "name": "Test Character"}],
    }
    assert validate_input(raw)["prompt"] == "external private text"
    assert "prompt" not in raw


def test_wire_comparison_is_order_sensitive_and_prompt_redacted() -> None:
    left: dict[str, Any] = {
        "rich_prompt": [["a", "b"]],
        "media_ids": ["m1", "m2"],
        "model": "abra_r2v_10s",
        "count": 1,
        "entity_ids": ["e1"],
        "project_id": "p",
    }
    assert all(field_equality(left, dict(left)).values())
    assert not field_equality(left, {**left, "media_ids": ["m2", "m1"]})["media_ids"]
    summarized = summarize_prompt([["safe prompt content"]], media_names={}, entity_names={})
    assert "safe prompt content" not in json.dumps(summarized)
    assert summarized[0][0]["text_length"] == len("safe prompt content")
    # Unknown numeric wire enums must still compare exactly, not be dropped.
    assert summarize_prompt([3, [5]], media_names={}, entity_names={}) != summarize_prompt(
        [3, [4]], media_names={}, entity_names={}
    )


def test_rich_prompt_checks_ordered_media_characters_and_text() -> None:
    rich = [
        None,
        None,
        [
            [
                [None, [["m1", "scene.png"]]],
                ["  "],
                [None, None, ["e1", "Momo"]],
                [" hello"],
            ]
        ],
    ]
    result = rich_prompt_checks(
        rich,
        media=[{"id": "m1", "picker_name": "scene.png"}],
        characters=[{"id": "e1", "name": "Momo"}],
        prompt="hello",
    )
    assert result["media_order_matches"] and result["character_order_matches"]
    assert result["prompt_text_matches"]
    changed = rich_prompt_checks(
        rich,
        media=[{"id": "wrong", "picker_name": "scene.png"}],
        characters=[{"id": "e1", "name": "Momo"}],
        prompt="hello",
    )
    assert not changed["media_order_matches"]
