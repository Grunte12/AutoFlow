"""Pure parser for the native Flow character readback payload.

This parser intentionally reads only the observed positional fields. It does not
walk arbitrary UUID-looking values or retain prompts, URLs, or other wire data.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, NoReturn, cast
from uuid import UUID

from gflow_cli.api.character import Character
from gflow_cli.errors import WireFormatError

_ROUTE = "native:projectInitialData"
_CHARACTER_TYPE = 1


@dataclass(frozen=True)
class NativeCharacterReadback:
    """A stable Character DTO and its verified workflow-to-media bindings.

    An empty ``workflow_media_bindings`` tuple means no exact binding was
    established. Listing allows that unverified state; the verified parser
    below does not.
    """

    character: Character
    workflow_media_bindings: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class _CharacterFields:
    character: Character
    workflow_ids: tuple[str, ...]


def _invalid(reason: str) -> NoReturn:
    """Raise a safe format error without embedding any wire values."""
    raise WireFormatError(
        f"unexpected native character response: {reason}",
        route=_ROUTE,
        discovery={"format": "native-character-v1", "reason": reason},
        remediation_hint=(
            "Inspect the native Character and its operation journal. "
            "Do not repeat an uncertain import or generation."
        ),
    )


def _uuid(value: object, field: str) -> str:
    if not isinstance(value, str):
        _invalid(f"{field} must be a canonical UUID")
    try:
        canonical = str(UUID(value))
    except (ValueError, AttributeError):
        _invalid(f"{field} must be a canonical UUID")
    if value != canonical:
        _invalid(f"{field} must be a canonical UUID")
    return canonical


def _as_list(value: object, field: str) -> list[Any]:
    if not isinstance(value, list):
        _invalid(f"{field} must be an array")
    return cast("list[Any]", value)


def _workflow_index(raw_workflows: object) -> dict[str, list[list[Any]]]:
    workflows = _as_list(raw_workflows, "workflows slot 1")
    indexed: dict[str, list[list[Any]]] = {}
    for row in workflows:
        if not isinstance(row, list) or not row:
            _invalid("workflow row must be a nonempty array")
        row = cast("list[Any]", row)
        workflow_id = _uuid(row[0], "workflow id")
        indexed.setdefault(workflow_id, []).append(row)
    return indexed


def _character_fields(row: object, project_id: str) -> _CharacterFields | None:
    if not isinstance(row, list):
        _invalid("entity row must contain the observed character-info slot")
    row = cast("list[Any]", row)
    if len(row) < 4:
        _invalid("entity row must contain the observed character-info slot")

    entity_info = row[3]
    if not isinstance(entity_info, list) or not entity_info:
        _invalid("entity info must be a nonempty array")
    entity_info = cast("list[Any]", entity_info)
    entity_type = entity_info[0]
    if isinstance(entity_type, bool) or not isinstance(entity_type, int):
        _invalid("entity type must be an integer")
    if entity_type != _CHARACTER_TYPE:
        return None

    if len(row) < 5 or len(entity_info) < 3:
        _invalid("character row is missing a required positional field")
    entity_project = _uuid(row[0], "entity project id")
    if entity_project != project_id:
        _invalid("entity project id does not match the requested project")
    entity_id = _uuid(row[1], "entity id")

    display_name = entity_info[1]
    if not isinstance(display_name, str) or not display_name:
        _invalid("character display name must be a nonempty string")

    character_info = _as_list(entity_info[2], "character info")
    # Flow also returns valid empty Characters as character_info=[] (not [[]]).
    raw_references = _as_list(character_info[0], "image references") if character_info else []
    workflow_ids: list[str] = []
    for reference in raw_references:
        if not isinstance(reference, list) or not reference:
            _invalid("image reference must contain its workflow id")
        reference = cast("list[Any]", reference)
        workflow_ids.append(_uuid(reference[0], "image-reference workflow id"))
    if len(set(workflow_ids)) != len(workflow_ids):
        _invalid("character contains duplicate workflow references")

    thumbnail_raw = row[4]
    thumbnail_id = None if thumbnail_raw is None else _uuid(thumbnail_raw, "thumbnail media id")
    return _CharacterFields(
        character=Character(
            entity_id=entity_id,
            display_name=display_name,
            project_id=entity_project,
            workflow_ids=tuple(workflow_ids),
            voice=None,
            personality=None,
            thumbnail_media_id=thumbnail_id,
        ),
        workflow_ids=tuple(workflow_ids),
    )


def _resolve_bindings(
    character: _CharacterFields,
    workflow_index: dict[str, list[list[Any]]],
    project_id: str,
) -> tuple[tuple[str, str], ...]:
    pairs: list[tuple[str, str]] = []
    for workflow_id in character.workflow_ids:
        matches = workflow_index.get(workflow_id, [])
        if not matches:
            _invalid("referenced workflow is missing")
        if len(matches) != 1:
            _invalid("referenced workflow id is ambiguous")

        row = matches[0]
        if len(row) < 6:
            _invalid("workflow row is missing its project or parent-entity slot")
        metadata = _as_list(row[3], "workflow metadata")
        if len(metadata) < 5:
            _invalid("workflow metadata is missing its primary-media slot")
        workflow_project = _uuid(row[4], "workflow project id")
        parent_entity = _uuid(row[5], "workflow parent entity id")
        if workflow_project != project_id:
            _invalid("workflow project id does not match the requested project")
        if parent_entity != character.character.entity_id:
            _invalid("workflow parent entity does not match the character")
        media_id = _uuid(metadata[4], "workflow primary media id")
        pairs.append((workflow_id, media_id))
    return tuple(pairs)


def _parse(
    payload: object, project_id: str
) -> tuple[list[_CharacterFields], dict[str, list[list[Any]]], str]:
    requested_project = _uuid(project_id, "requested project id")
    root = _as_list(payload, "native payload")
    if len(root) <= 5:
        _invalid("native payload is missing workflows or entities slots")
    workflow_index = _workflow_index(root[1])
    entities = _as_list(root[5], "entities slot 5")

    characters: list[_CharacterFields] = []
    entity_ids: set[str] = set()
    for row in entities:
        fields = _character_fields(row, requested_project)
        if fields is None:
            continue
        if fields.character.entity_id in entity_ids:
            _invalid("duplicate character entity id")
        entity_ids.add(fields.character.entity_id)
        characters.append(fields)
    return characters, workflow_index, requested_project


def parse_native_characters(payload: object, project_id: str) -> list[NativeCharacterReadback]:
    """Parse native character entities, retaining only exact bindings when available.

    Characters with no references, or whose workflow binding cannot be proven,
    remain listable with an empty binding tuple. Use
    :func:`parse_verified_native_character` when a verified workflow/media pair
    is required.
    """
    characters, workflow_index, requested_project = _parse(payload, project_id)
    result: list[NativeCharacterReadback] = []
    for fields in characters:
        try:
            bindings = _resolve_bindings(fields, workflow_index, requested_project)
        except WireFormatError:
            bindings = ()
        result.append(NativeCharacterReadback(fields.character, bindings))
    return result


def parse_verified_native_character(
    payload: object, project_id: str, entity_id: str
) -> NativeCharacterReadback:
    """Return one character only when every workflow/media binding is exact."""
    requested_entity = _uuid(entity_id, "requested entity id")
    characters, workflow_index, requested_project = _parse(payload, project_id)
    matches = [item for item in characters if item.character.entity_id == requested_entity]
    if not matches:
        _invalid("requested character entity is missing")
    if len(matches) != 1:
        _invalid("requested character entity is ambiguous")
    character = matches[0]
    if not character.workflow_ids:
        _invalid("character has no workflow references to verify")
    bindings = _resolve_bindings(character, workflow_index, requested_project)
    if not bindings:
        _invalid("character has no verified workflow/media bindings")
    return NativeCharacterReadback(character.character, bindings)


__all__ = [
    "NativeCharacterReadback",
    "parse_native_characters",
    "parse_verified_native_character",
]
