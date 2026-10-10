"""Journal existing-Character image changes; replay never repeats an upload."""

from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, NoReturn, cast
from uuid import UUID

from gflow_cli.api.client import validate_image_bytes, validate_image_file
from gflow_cli.data.models import OperationKind, OperationRecord, OperationStatus, ProjectRecord
from gflow_cli.errors import ConfigurationError, WireFormatError

if TYPE_CHECKING:
    from pathlib import Path

    from gflow_cli.api.client import FlowApiClient
    from gflow_cli.data.recorder import OperationRecorder

_COMMAND = "character update-images"
_REMEDIATION = (
    "Inspect this Character and the operation journal. Do not repeat an uncertain image update."
)


def _refuse(detail: str) -> NoReturn:
    raise ConfigurationError(detail, remediation_hint=_REMEDIATION)


async def character_update_images(
    client: FlowApiClient,
    recorder: OperationRecorder,
    *,
    profile_name: str,
    profile_dir: Path,
    project_id: str,
    entity_id: str,
    operation_id: str,
    portrait: Path | None = None,
    full_body: Path | None = None,
) -> dict[str, Any]:
    """Replace requested slots, preserving metadata and every omitted slot.

    Source bytes are frozen before mutation. STARTED intent precedes uploads;
    each acknowledged binding is checkpointed. On replay, only a complete
    checkpoint plus exact fresh state can succeed, never a second upload.
    """
    for value in (project_id, entity_id, operation_id):
        try:
            if str(UUID(value)) != value:
                raise ValueError
        except (ValueError, TypeError, AttributeError):
            _refuse("Character update identifiers must be canonical UUIDs.")
    if portrait is None and full_body is None:
        _refuse("Supply at least one Character image.")
    sources: dict[str, bytes] = {}
    for slot, path in (("portrait", portrait), ("full_body", full_body)):
        if path is not None:
            await validate_image_file(path)
            source = await asyncio.to_thread(path.read_bytes)
            validate_image_bytes(source)
            sources[slot] = source
    intent = {
        "format": "native-character-update-v1",
        "entity_id": entity_id,
        "source_hashes": {slot: hashlib.sha256(data).hexdigest() for slot, data in sources.items()},
    }
    repo = recorder.repository
    row = repo.store.conn.execute(
        "SELECT command, profile_name, flow_project_id, status, metadata_json "
        "FROM operations WHERE id = ?",
        (operation_id,),
    ).fetchone()
    if row is not None:
        try:
            raw: object = json.loads(row["metadata_json"] or "{}")
        except (ValueError, TypeError):
            _refuse("Character update journal metadata is invalid.")
        if not isinstance(raw, dict):
            _refuse("Character update journal metadata is invalid.")
        metadata = cast("dict[str, Any]", raw)
        if (
            row["command"] != _COMMAND
            or row["profile_name"] != profile_name
            or row["flow_project_id"] != project_id
            or any(metadata.get(key) != value for key, value in intent.items())
        ):
            _refuse("Operation UUID already identifies a different Character update.")
        expected = metadata.get("expected_state")
        if not isinstance(expected, dict):
            _refuse("Interrupted Character update lacks complete image checkpoints.")
        current = await client.read_character_image_state(project_id, entity_id)
        if current != expected:
            _refuse("Current Character images or metadata differ from the update checkpoint.")
        result = metadata.get("result")
        if not isinstance(result, dict):
            _refuse("Character update has no verified result checkpoint.")
        if row["status"] != OperationStatus.SUCCEEDED.value:
            if row["status"] != OperationStatus.STARTED.value:
                _refuse("Character update journal is not resumable.")
            _complete(recorder, operation_id, metadata)
        return cast("dict[str, Any]", result)

    # Read the precise target before recording intent; this must not create it.
    before = await client.read_character_image_state(project_id, entity_id)
    metadata: dict[str, Any] = {**intent, "before": before, "uploaded": {}}
    repo.upsert_profile(profile_name, profile_dir)
    if repo.get_project(profile_name, project_id) is None:
        repo.upsert_project(ProjectRecord(operation_id, profile_name, project_id, None, _COMMAND))
    record = OperationRecord(
        id=operation_id,
        profile_name=profile_name,
        flow_project_id=project_id,
        command=_COMMAND,
        mode=OperationKind.CHARACTER,
        status=OperationStatus.STARTED,
        flow_operation_id=None,
        flow_batch_id=None,
        prompt=None,
        prompt_hash=None,
        prompt_redacted=True,
        model=None,
        aspect_ratio=None,
        error_type=None,
        error_detail=None,
    )
    repo.insert_operation(record)
    repo.set_operation_metadata(operation_id, metadata)

    async def checkpoint(slot: str, binding: dict[str, str]) -> None:
        if slot not in sources or slot in metadata["uploaded"]:
            raise WireFormatError("Unexpected Character image checkpoint")
        metadata["uploaded"][slot] = binding
        repo.set_operation_metadata(operation_id, metadata)

    after = await client.replace_character_images(
        project_id=project_id,
        entity_id=entity_id,
        images=sources,
        before=before,
        checkpoint=checkpoint,
    )
    expected = {**before, "images": {**before["images"], **metadata["uploaded"]}}
    if set(metadata["uploaded"]) != set(sources) or after != expected:
        raise WireFormatError("Character image readback does not match the update checkpoints")
    result = {
        "status": "ok",
        "images": {
            slot: {**binding, "source_sha256": intent["source_hashes"][slot]}
            for slot, binding in metadata["uploaded"].items()
        },
    }
    metadata.update(expected_state=expected, result=result)
    repo.set_operation_metadata(operation_id, metadata)
    _complete(recorder, operation_id, metadata)
    return result


def _complete(recorder: OperationRecorder, operation_id: str, metadata: dict[str, Any]) -> None:
    recorder.repository.update_operation_metadata(
        operation_id,
        status=OperationStatus.SUCCEEDED,
        completed_at=datetime.now(UTC).isoformat(),
        prompt=None,
        prompt_hash=None,
        prompt_redacted=True,
        metadata_json=metadata,
    )
