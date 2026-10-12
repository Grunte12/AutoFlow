from __future__ import annotations

from typing import Any

import pytest

from gflow_cli.api.transports.native_character import (
    NativeCharacterReadback,
    parse_native_characters,
    parse_verified_native_character,
)
from gflow_cli.errors import WireFormatError

PROJECT = "a0000000-0000-4000-8000-000000000001"
OTHER_PROJECT = "a0000000-0000-4000-8000-000000000002"
ENTITY = "b0000000-0000-4000-8000-000000000001"
OTHER_ENTITY = "b0000000-0000-4000-8000-000000000002"
WORKFLOW = "c0000000-0000-4000-8000-000000000001"
OTHER_WORKFLOW = "c0000000-0000-4000-8000-000000000002"
MEDIA = "d0000000-0000-4000-8000-000000000001"
OTHER_MEDIA = "d0000000-0000-4000-8000-000000000002"


def _entity(
    *,
    project_id: str = PROJECT,
    entity_id: str = ENTITY,
    name: str = "Momo",
    workflow_ids: tuple[str, ...] = (WORKFLOW,),
    thumbnail_id: str | None = MEDIA,
    personality: Any = None,
    include_personality: bool = True,
) -> list[Any]:
    """A sanitized native entity row matching the captured positional schema."""
    image_references = [[workflow_id] for workflow_id in workflow_ids]
    character_info = [1, name, [image_references, None]]
    if include_personality:
        character_info[2].append(personality)
    return [project_id, entity_id, None, character_info, thumbnail_id, [1086, 1448], [1, 2], [3, 4]]


def _empty_entity(*, entity_id: str = OTHER_ENTITY, name: str = "Empty verification") -> list[Any]:
    """An observed valid Character row with no character-info image references."""
    return [PROJECT, entity_id, None, [1, name, []], None, [1086, 1448], [1, 2], [3, 4]]


def _workflow(
    workflow_id: str = WORKFLOW,
    *,
    project_id: str = PROJECT,
    parent_entity_id: str = ENTITY,
    media_id: str = MEDIA,
) -> list[Any]:
    return [
        workflow_id,
        None,
        None,
        ["portrait", [1, 2], None, None, media_id, None, [3, 4]],
        project_id,
        parent_entity_id,
    ]


def _payload(*, entities: list[Any] | None = None, workflows: list[Any] | None = None) -> list[Any]:
    workflow_rows = [_workflow()] if workflows is None else workflows
    entity_rows = [_entity()] if entities is None else entities
    payload: list[Any] = [None, workflow_rows, None, None, None, entity_rows]
    return payload


def test_native_character_parser_returns_only_stable_character_fields() -> None:
    payload = _payload()
    payload[5][0][2] = "https://media.invalid/?token=fixture-token"
    payload[1][0][3][0] = "PRIVATE_PROMPT_SENTINEL"
    parsed = parse_native_characters(payload, PROJECT)

    assert len(parsed) == 1
    assert isinstance(parsed[0], NativeCharacterReadback)
    assert parsed[0].character.entity_id == ENTITY
    assert parsed[0].character.project_id == PROJECT
    assert parsed[0].character.display_name == "Momo"
    assert parsed[0].character.workflow_ids == (WORKFLOW,)
    assert parsed[0].character.thumbnail_media_id == MEDIA
    assert parsed[0].character.voice is None
    assert parsed[0].character.personality is None
    assert parsed[0].workflow_media_bindings == ((WORKFLOW, MEDIA),)
    serialized = repr(parsed)
    assert "PRIVATE_PROMPT_SENTINEL" not in serialized
    assert "fixture-token" not in serialized


def test_native_character_exposes_verified_portrait_and_body_slots() -> None:
    payload = _payload(
        entities=[_entity(workflow_ids=(WORKFLOW, OTHER_WORKFLOW))],
        workflows=[_workflow(), _workflow(OTHER_WORKFLOW, media_id=OTHER_MEDIA)],
    )
    character = parse_native_characters(payload, PROJECT)[0].character
    assert character.images == {
        "portrait": {"workflow_id": WORKFLOW, "media_id": MEDIA},
        "full_body": {"workflow_id": OTHER_WORKFLOW, "media_id": OTHER_MEDIA},
    }


def test_native_character_does_not_claim_unverified_image_slots() -> None:
    character = parse_native_characters(_payload(workflows=[]), PROJECT)[0].character
    assert character.images is None


@pytest.mark.parametrize("personality", ["Warm and observant", "敏锐、温柔 🐈", ""])
def test_native_character_parser_preserves_personality(personality: str) -> None:
    parsed = parse_native_characters(_payload(entities=[_entity(personality=personality)]), PROJECT)

    assert parsed[0].character.personality == personality


@pytest.mark.parametrize("personality", [None, pytest.param("missing", id="missing")])
def test_native_character_parser_keeps_absent_personality_none(personality: str | None) -> None:
    entity = (
        _entity(include_personality=False)
        if personality == "missing"
        else _entity(personality=personality)
    )

    assert (
        parse_native_characters(_payload(entities=[entity]), PROJECT)[0].character.personality
        is None
    )


@pytest.mark.parametrize("personality", [[], {"secret": "PRIVATE_PERSONALITY_SENTINEL"}, 17, True])
def test_native_character_parser_rejects_malformed_personality(personality: Any) -> None:
    with pytest.raises(WireFormatError) as exc_info:
        parse_native_characters(_payload(entities=[_entity(personality=personality)]), PROJECT)
    assert "PRIVATE_PERSONALITY_SENTINEL" not in str(exc_info.value)


def test_verified_parser_returns_exact_workflow_media_pair() -> None:
    parsed = parse_verified_native_character(_payload(), PROJECT, ENTITY)

    assert parsed.character.entity_id == ENTITY
    assert parsed.workflow_media_bindings == ((WORKFLOW, MEDIA),)


def test_verified_parser_preserves_personality() -> None:
    parsed = parse_verified_native_character(
        _payload(entities=[_entity(personality="敏锐、温柔 🐈")]), PROJECT, ENTITY
    )

    assert parsed.character.personality == "敏锐、温柔 🐈"


def test_missing_referenced_workflow_is_not_verified() -> None:
    with pytest.raises(WireFormatError):
        parse_verified_native_character(_payload(workflows=[]), PROJECT, ENTITY)


def test_wrong_parent_entity_is_rejected() -> None:
    with pytest.raises(WireFormatError):
        parse_verified_native_character(
            _payload(workflows=[_workflow(parent_entity_id=OTHER_ENTITY)]), PROJECT, ENTITY
        )


def test_foreign_project_entity_is_rejected() -> None:
    with pytest.raises(WireFormatError):
        parse_native_characters(_payload(entities=[_entity(project_id=OTHER_PROJECT)]), PROJECT)


def test_foreign_project_workflow_is_rejected() -> None:
    with pytest.raises(WireFormatError):
        parse_verified_native_character(
            _payload(workflows=[_workflow(project_id=OTHER_PROJECT)]), PROJECT, ENTITY
        )


def test_malformed_native_payload_is_rejected() -> None:
    with pytest.raises(WireFormatError):
        parse_native_characters([None, [], None, None, None], PROJECT)


def test_duplicate_entity_ids_are_rejected() -> None:
    with pytest.raises(WireFormatError):
        parse_native_characters(_payload(entities=[_entity(), _entity(name="Copy")]), PROJECT)


def test_duplicate_workflow_ids_are_ambiguous() -> None:
    with pytest.raises(WireFormatError):
        parse_verified_native_character(
            _payload(workflows=[_workflow(), _workflow(media_id=OTHER_MEDIA)]), PROJECT, ENTITY
        )


def test_empty_references_are_listable_but_not_verified() -> None:
    payload = _payload(entities=[_empty_entity()])
    parsed = parse_native_characters(payload, PROJECT)

    assert len(parsed) == 1
    assert parsed[0].character.workflow_ids == ()
    assert parsed[0].workflow_media_bindings == ()
    with pytest.raises(WireFormatError):
        parse_verified_native_character(payload, PROJECT, OTHER_ENTITY)


def test_exact_character_verification_ignores_unrelated_empty_character() -> None:
    parsed = parse_verified_native_character(
        _payload(entities=[_entity(), _empty_entity()]), PROJECT, ENTITY
    )

    assert parsed.character.entity_id == ENTITY
    assert parsed.workflow_media_bindings == ((WORKFLOW, MEDIA),)


def test_duplicate_references_are_rejected() -> None:
    with pytest.raises(WireFormatError):
        parse_native_characters(
            _payload(entities=[_entity(workflow_ids=(WORKFLOW, WORKFLOW))]), PROJECT
        )


def test_noncanonical_ids_are_rejected() -> None:
    with pytest.raises(WireFormatError):
        parse_native_characters(_payload(entities=[_entity(entity_id="not-a-uuid")]), PROJECT)
