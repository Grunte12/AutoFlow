"""Idempotent service orchestration for original-sheet Character import."""

from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, NoReturn, cast

from gflow_cli.api.transports.native_character import NativeCharacterReadback
from gflow_cli.api.transports.native_character_import import NativeCharacterImportResult
from gflow_cli.data.models import (
    OperationKind,
    OperationRecord,
    OperationStatus,
    ProjectRecord,
)
from gflow_cli.data.redaction import prompt_fields
from gflow_cli.errors import ConfigurationError, DataIntegrityError, WireFormatError

if TYPE_CHECKING:
    from pathlib import Path

    from gflow_cli.api.client import FlowApiClient
    from gflow_cli.data.recorder import OperationRecorder

_COMMAND = "character import"
_ROUTE = "characterImport"
_METADATA_FORMAT = "native-character-import-v1"
_UNCERTAIN_REMEDIATION = (
    "Inspect the native Character list for this project and reconcile the checkpointed "
    "entity before retrying. Do not repeat the import while its binding state is uncertain."
)


@dataclass(frozen=True)
class _Journal:
    profile_name: str
    project_id: str | None
    command: str | None
    mode: str
    status: str
    prompt_hash: str | None
    metadata: dict[str, object]


def _configuration(detail: str, remediation_hint: str = _UNCERTAIN_REMEDIATION) -> NoReturn:
    raise ConfigurationError(detail=detail, route=_ROUTE, remediation_hint=remediation_hint)


def _canonical_uuid(value: object, field: str) -> str:
    if not isinstance(value, str):
        _configuration(f"Character import {field} must be a canonical UUID.")
    try:
        canonical = str(uuid.UUID(value))
    except (ValueError, AttributeError, TypeError):
        _configuration(f"Character import {field} must be a canonical UUID.")
    if value != canonical:
        _configuration(f"Character import {field} must be a canonical UUID.")
    return canonical


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _load_metadata(raw: object) -> dict[str, object]:
    if not isinstance(raw, str) or not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    if not isinstance(parsed, dict):
        return {}
    return cast("dict[str, object]", parsed)


def _load_journal(recorder: OperationRecorder, operation_id: str) -> _Journal | None:
    row = recorder.repository.store.conn.execute(
        "SELECT profile_name, flow_project_id, command, mode, status, prompt_hash, "
        "metadata_json FROM operations WHERE id = ?",
        (operation_id,),
    ).fetchone()
    if row is None:
        return None
    return _Journal(
        profile_name=str(row["profile_name"]),
        project_id=str(row["flow_project_id"]) if row["flow_project_id"] is not None else None,
        command=str(row["command"]) if row["command"] is not None else None,
        mode=str(row["mode"]),
        status=str(row["status"]),
        prompt_hash=str(row["prompt_hash"]) if row["prompt_hash"] is not None else None,
        metadata=_load_metadata(row["metadata_json"]),
    )


def _identity_metadata(
    *, name: str, source_sha256: str, personality_hash: str | None
) -> dict[str, object]:
    return {
        "format": _METADATA_FORMAT,
        "name": name,
        "source_sha256": source_sha256,
        "personality_hash": personality_hash,
        "entity_id": None,
    }


def _validate_same_key(
    journal: _Journal,
    *,
    profile_name: str,
    project_id: str,
    name: str,
    source_sha256: str,
    personality_hash: str | None,
) -> None:
    metadata = journal.metadata
    if (
        journal.command != _COMMAND
        or journal.mode != OperationKind.CHARACTER.value
        or journal.profile_name != profile_name
        or journal.project_id != project_id
        or metadata.get("format") != _METADATA_FORMAT
        or metadata.get("name") != name
        or metadata.get("source_sha256") != source_sha256
        or metadata.get("personality_hash") != personality_hash
        or journal.prompt_hash != personality_hash
    ):
        _configuration(
            "This operation UUID already identifies a different import request.",
            "Inspect the native Character list and prior operation before choosing a new "
            "operation UUID; changing the key must not be used to bypass an uncertain import.",
        )


def _stored_bindings(metadata: dict[str, object]) -> tuple[tuple[str, str], ...] | None:
    raw_value = metadata.get("workflow_media_bindings")
    if not isinstance(raw_value, list) or not raw_value:
        return None
    raw = cast("list[object]", raw_value)
    bindings: list[tuple[str, str]] = []
    for raw_item in raw:
        if not isinstance(raw_item, list):
            return None
        item = cast("list[object]", raw_item)
        if len(item) != 2:
            return None
        workflow_id, media_id = item
        if not isinstance(workflow_id, str) or not isinstance(media_id, str):
            return None
        try:
            workflow_id = _canonical_uuid(workflow_id, "journal workflow id")
            media_id = _canonical_uuid(media_id, "journal media id")
        except ConfigurationError:
            return None
        bindings.append((workflow_id, media_id))
    return tuple(bindings)


def _entity_id(metadata: dict[str, object]) -> str | None:
    raw = metadata.get("entity_id")
    if not isinstance(raw, str):
        return None
    try:
        return _canonical_uuid(raw, "journal entity id")
    except ConfigurationError:
        return None


def _readback_matches(
    readback: NativeCharacterReadback,
    *,
    project_id: str,
    entity_id: str,
    name: str,
    bindings: tuple[tuple[str, str], ...],
) -> bool:
    character = readback.character
    return (
        character.project_id == project_id
        and character.entity_id == entity_id
        and character.display_name == name
        and character.workflow_ids == tuple(workflow for workflow, _ in bindings)
        and readback.workflow_media_bindings == bindings
    )


def _binding_metadata(
    metadata: dict[str, object],
    *,
    entity_id: str,
    bindings: tuple[tuple[str, str], ...],
) -> dict[str, object]:
    result = dict(metadata)
    result["entity_id"] = entity_id
    result["workflow_media_bindings"] = [[workflow, media] for workflow, media in bindings]
    return result


def _completed_at() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _complete(
    recorder: OperationRecorder,
    *,
    operation_id: str,
    personality: str | None,
    metadata: dict[str, object],
) -> None:
    prompt = prompt_fields(personality, mode=recorder.prompt_mode)
    recorder.repository.update_operation_metadata(
        operation_id,
        status=OperationStatus.SUCCEEDED,
        completed_at=_completed_at(),
        prompt=prompt.prompt,
        prompt_hash=prompt.prompt_hash,
        prompt_redacted=prompt.prompt_redacted,
        metadata_json=metadata,
    )


async def _remote_readback(
    client: FlowApiClient, project_id: str, entity_id: str
) -> NativeCharacterReadback:
    return await client.get_character_import_readback(project_id, entity_id)


async def _reconcile_known_bindings(
    client: FlowApiClient,
    recorder: OperationRecorder,
    *,
    operation_id: str,
    project_id: str,
    entity_id: str,
    name: str,
    bindings: tuple[tuple[str, str], ...],
    personality: str | None,
    source_sha256: str,
    metadata: dict[str, object],
    finalize: bool,
) -> NativeCharacterImportResult:
    try:
        readback = await _remote_readback(client, project_id, entity_id)
    except Exception as exc:  # noqa: BLE001 - reconciliation must never restart an upload
        raise ConfigurationError(
            detail=(
                f"Character import operation could not verify checkpointed entity {entity_id}."
            ),
            route=_ROUTE,
            remediation_hint=_UNCERTAIN_REMEDIATION,
        ) from exc
    if not _readback_matches(
        readback,
        project_id=project_id,
        entity_id=entity_id,
        name=name,
        bindings=bindings,
    ):
        _configuration(
            "Character import operation does not match the journaled import for "
            f"entity {entity_id}."
        )
    if finalize:
        _complete(
            recorder,
            operation_id=operation_id,
            personality=personality,
            metadata=metadata,
        )
    return NativeCharacterImportResult(readback=readback, source_sha256=source_sha256)


async def _reconcile_unknown_bindings(
    client: FlowApiClient,
    *,
    project_id: str,
    entity_id: str,
) -> NoReturn:
    # Observe the exact checkpointed entity, but without a persisted upload media ID
    # there is no safe way to attribute its current image to this operation's source.
    try:
        await _remote_readback(client, project_id, entity_id)
    except Exception:  # noqa: BLE001 - either outcome requires manual reconciliation
        pass
    _configuration(
        f"Character import operation for entity {entity_id} has no journaled image binding."
    )


def _insert_started(
    recorder: OperationRecorder,
    *,
    profile_name: str,
    profile_dir: Path,
    project_id: str,
    operation_id: str,
    personality: str | None,
    metadata: dict[str, object],
) -> _Journal | None:
    repo = recorder.repository
    repo.upsert_profile(profile_name, profile_dir)
    if repo.get_project(profile_name, project_id) is None:
        repo.upsert_project(
            ProjectRecord(
                id=str(uuid.uuid4()),
                profile_name=profile_name,
                flow_project_id=project_id,
                title=None,
                source="character_import",
            )
        )
    prompt = prompt_fields(personality, mode=recorder.prompt_mode)
    record = OperationRecord(
        id=operation_id,
        profile_name=profile_name,
        flow_project_id=project_id,
        command=_COMMAND,
        mode=OperationKind.CHARACTER,
        status=OperationStatus.STARTED,
        flow_operation_id=None,
        flow_batch_id=None,
        prompt=prompt.prompt,
        prompt_hash=prompt.prompt_hash,
        prompt_redacted=prompt.prompt_redacted,
        model=None,
        aspect_ratio=None,
        error_type=None,
        error_detail=None,
    )
    try:
        repo.insert_operation(record)
    except DataIntegrityError:
        # A concurrent invocation may have claimed the caller's UUID first. Treat
        # only a row now present under this exact key as an idempotent replay.
        journal = _load_journal(recorder, operation_id)
        if journal is None:
            raise
        return journal
    repo.set_operation_metadata(operation_id, metadata)
    return None


async def character_import(
    client: FlowApiClient,
    recorder: OperationRecorder,
    *,
    profile_name: str,
    profile_dir: Path,
    project_id: str,
    name: str,
    sheet: Path,
    personality: str | None = None,
    operation_id: str,
) -> NativeCharacterImportResult:
    """Import original sheet bytes without generation, using a caller UUID key.

    STARTED and identity hashes are durably recorded before the client can mutate
    Flow. An interrupted operation is never retried as a fresh upload; replay only
    succeeds when a previously journaled entity and exact workflow/media bindings
    match current native readback.
    """
    operation_id = _canonical_uuid(operation_id, "operation id")
    project_id = _canonical_uuid(project_id, "project id")
    if not profile_name:
        _configuration("Character import profile name must not be empty.")
    if not name or name != name.strip():
        _configuration("Character import name must be nonempty without surrounding whitespace.")

    from gflow_cli.api.client import validate_image_file  # noqa: PLC0415

    await validate_image_file(sheet)
    if personality is None:
        source_sha256 = await asyncio.to_thread(_sha256_file, sheet)
        personality_hash = None
    else:
        source_sha256, personality_hash = await asyncio.gather(
            asyncio.to_thread(_sha256_file, sheet),
            asyncio.to_thread(_sha256_text, personality),
        )
    metadata = _identity_metadata(
        name=name,
        source_sha256=source_sha256,
        personality_hash=personality_hash,
    )

    journal = _load_journal(recorder, operation_id)
    if journal is not None:
        _validate_same_key(
            journal,
            profile_name=profile_name,
            project_id=project_id,
            name=name,
            source_sha256=source_sha256,
            personality_hash=personality_hash,
        )
    else:
        journal = _insert_started(
            recorder,
            profile_name=profile_name,
            profile_dir=profile_dir,
            project_id=project_id,
            operation_id=operation_id,
            personality=personality,
            metadata=metadata,
        )
        if journal is not None:
            _validate_same_key(
                journal,
                profile_name=profile_name,
                project_id=project_id,
                name=name,
                source_sha256=source_sha256,
                personality_hash=personality_hash,
            )
    if journal is not None:
        entity_id = _entity_id(journal.metadata)
        bindings = _stored_bindings(journal.metadata)
        if journal.status == OperationStatus.SUCCEEDED.value:
            if entity_id is None or bindings is None:
                _configuration("Completed Character import has no exact journaled binding.")
            return await _reconcile_known_bindings(
                client,
                recorder,
                operation_id=operation_id,
                project_id=project_id,
                entity_id=entity_id,
                name=name,
                bindings=bindings,
                personality=personality,
                source_sha256=source_sha256,
                metadata=journal.metadata,
                finalize=False,
            )
        if journal.status != OperationStatus.STARTED.value:
            _configuration("Character import operation is not in a resumable state.")
        if entity_id is None:
            _configuration(
                "Character import operation is STARTED with no checkpointed entity; "
                "refusing recreation."
            )
        if bindings is None:
            await _reconcile_unknown_bindings(client, project_id=project_id, entity_id=entity_id)
        return await _reconcile_known_bindings(
            client,
            recorder,
            operation_id=operation_id,
            project_id=project_id,
            entity_id=entity_id,
            name=name,
            bindings=bindings,
            personality=personality,
            source_sha256=source_sha256,
            metadata=journal.metadata,
            finalize=True,
        )

    repo = recorder.repository

    async def checkpoint_entity(entity_id: str) -> None:
        canonical = _canonical_uuid(entity_id, "entity id")
        prior = metadata.get("entity_id")
        if prior is not None and prior != canonical:
            raise WireFormatError("Character import entity checkpoint changed", route=_ROUTE)
        metadata["entity_id"] = canonical
        repo.set_operation_metadata(operation_id, metadata)

    result = await client.import_character_sheet(
        project_id=project_id,
        name=name,
        sheet=sheet,
        personality=personality,
        on_entity_created=checkpoint_entity,
    )
    if result.source_sha256 != source_sha256:
        raise WireFormatError(
            "Character source changed between validation and native upload",
            route=_ROUTE,
        )
    entity_id = _entity_id(metadata)
    bindings = result.readback.workflow_media_bindings
    if (
        entity_id is None
        or not bindings
        or not _readback_matches(
            result.readback,
            project_id=project_id,
            entity_id=entity_id,
            name=name,
            bindings=bindings,
        )
    ):
        raise WireFormatError(
            "Native Character import did not return the checkpointed exact binding",
            route=_ROUTE,
        )

    metadata = _binding_metadata(metadata, entity_id=entity_id, bindings=bindings)
    # Persist verified bindings while the operation is still STARTED. A crash in
    # the final status write can then reconcile safely without another upload.
    repo.set_operation_metadata(operation_id, metadata)
    _complete(
        recorder,
        operation_id=operation_id,
        personality=personality,
        metadata=metadata,
    )
    return result


__all__ = ["character_import"]
