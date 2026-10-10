"""Pure saved-Character R2V binding and exact null-ack job attribution."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, cast
from urllib.parse import parse_qs

from gflow_cli.api.transports.batchexecute import (
    GenerationRecord,
    _at,  # pyright: ignore[reportPrivateUsage] -- shared internal wire parser
    _is_record,  # pyright: ignore[reportPrivateUsage]
    _walk_lists,  # pyright: ignore[reportPrivateUsage]
    generation_record,
)
from gflow_cli.errors import WireFormatError


@dataclass(frozen=True)
class CharacterSubmission:
    project_id: str
    rich_prompt: object


def character_submission(
    post_data: str, project_id: str, entity_ids: tuple[str, ...], expected_prompt: str | None = None
) -> CharacterSubmission:
    """Validate the entity slots before the intercepted request is continued."""
    try:
        if not entity_ids or len(set(entity_ids)) != len(entity_ids):
            raise ValueError("empty or duplicate Character IDs")
        envelope = json.loads(parse_qs(post_data)["f.req"][0])
        rows = [row for group in envelope for row in group if row[0] == "MZZa6b"]
        if len(rows) != 1:
            raise ValueError("missing or ambiguous submit")
        payload: Any = json.loads(rows[0][1])
        spec = payload[0][0]
        if payload[1][5] != project_id or "_r2v_" not in spec[2] or spec[3] != 1:
            raise ValueError("project, mode or count mismatch")
        if spec[9] != [[entity] for entity in entity_ids]:
            raise ValueError("entity-reference slot mismatch")
        prompt = spec[0]
        chips = [
            node[2][0]
            for node in _walk_lists(prompt)
            if len(node) == 3
            and node[:2] == [None, None]
            and isinstance(node[2], list)
            and len(cast("list[Any]", node[2])) == 2
            and isinstance(node[2][0], str)
        ]
        if chips != list(entity_ids):
            raise ValueError("rich-prompt entity chips mismatch")
        if expected_prompt is not None:
            text = "".join(
                node[0]
                for node in _walk_lists(prompt)
                if len(node) == 1 and isinstance(node[0], str)
            ).strip()
            if text != expected_prompt.strip():
                raise ValueError("prompt text mismatch")
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise WireFormatError(
            "saved Character submit binding did not match; request blocked before billing",
            route="batchexecute:MZZa6b",
        ) from exc
    return CharacterSubmission(project_id, prompt)


def attributed_character_record(
    payload: object,
    submission: CharacterSubmission,
    baseline_media_ids: frozenset[str],
) -> GenerationRecord | None:
    """Adopt only a unique new VIDEO row with the exact submitted rich prompt."""
    rows = [
        node
        for node in _walk_lists(payload)
        if _is_record(node)
        and node[3] is None
        and node[1] == submission.project_id
        and node[0] not in baseline_media_ids
        and _at(node, 5, 6, 2, 0) == submission.rich_prompt
    ]
    identities = {tuple(node[:3]) for node in rows}
    if len(identities) > 1:
        raise WireFormatError(
            "ambiguous saved Character jobs; inspect existing Flow jobs, do not regenerate",
            route="batchexecute:jwpduf",
        )
    if not rows:
        return None
    return generation_record("jwpduf", rows[0], project_id=submission.project_id)
