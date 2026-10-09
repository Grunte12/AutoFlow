"""Idempotency and recovery tests for native Character sheet import."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import pytest

from gflow_cli.api.character import Character
from gflow_cli.api.transports.native_character import NativeCharacterReadback
from gflow_cli.api.transports.native_character_import import NativeCharacterImportResult
from gflow_cli.data.recorder import OperationRecorder
from gflow_cli.data.repository import DataRepository
from gflow_cli.data.store import DataStore
from gflow_cli.errors import ConfigurationError
from gflow_cli.services.character_import import character_import

PROFILE = "default"
PROJECT = "a0000000-0000-4000-8000-000000000001"
OTHER_PROJECT = "a0000000-0000-4000-8000-000000000002"
ENTITY = "b0000000-0000-4000-8000-000000000001"
WORKFLOW = "c0000000-0000-4000-8000-000000000001"
MEDIA = "d0000000-0000-4000-8000-000000000001"
OTHER_MEDIA = "d0000000-0000-4000-8000-000000000002"
OPERATION = "e0000000-0000-4000-8000-000000000001"
NAME = "Momo"
PERSONALITY = "PRIVATE_PERSONALITY_SENTINEL"
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8


@pytest.fixture
def recorder(tmp_path: Path) -> Any:
    with DataStore.open(tmp_path / "gflow.db") as store:
        yield OperationRecorder(DataRepository(store), prompt_mode="redacted")


def _readback(
    *,
    entity_id: str = ENTITY,
    project_id: str = PROJECT,
    name: str = NAME,
    bindings: tuple[tuple[str, str], ...] = ((WORKFLOW, MEDIA),),
) -> NativeCharacterReadback:
    return NativeCharacterReadback(
        character=Character(
            entity_id=entity_id,
            display_name=name,
            project_id=project_id,
            workflow_ids=tuple(workflow for workflow, _ in bindings),
            voice=None,
            personality=None,
            thumbnail_media_id=bindings[0][1] if bindings else None,
        ),
        workflow_media_bindings=bindings,
    )


class _Client:
    def __init__(self) -> None:
        self.import_result = NativeCharacterImportResult(
            readback=_readback(),
            source_sha256=hashlib.sha256(PNG_BYTES).hexdigest(),
        )
        self.remote_readback = _readback()
        self.import_calls: list[dict[str, Any]] = []
        self.read_calls: list[tuple[str, str]] = []
        self.before_import: Callable[[], None] | None = None
        self.fail_import: Exception | None = None
        self.checkpoint = True

    async def import_character_sheet(
        self,
        *,
        project_id: str,
        name: str,
        sheet: Path,
        personality: str | None,
        on_entity_created: Callable[[str], Awaitable[None]],
    ) -> NativeCharacterImportResult:
        self.import_calls.append(
            {
                "project_id": project_id,
                "name": name,
                "sheet": sheet,
                "personality": personality,
            }
        )
        if self.before_import is not None:
            self.before_import()
        if self.checkpoint:
            await on_entity_created(ENTITY)
        if self.fail_import is not None:
            raise self.fail_import
        return self.import_result

    async def get_character_import_readback(
        self, project_id: str, entity_id: str
    ) -> NativeCharacterReadback:
        self.read_calls.append((project_id, entity_id))
        return self.remote_readback


def _kwargs(tmp_path: Path, sheet_path: Path, **overrides: Any) -> dict[str, Any]:
    result: dict[str, Any] = {
        "profile_name": PROFILE,
        "profile_dir": tmp_path / "profile",
        "project_id": PROJECT,
        "name": NAME,
        "sheet": sheet_path,
        "personality": PERSONALITY,
        "operation_id": OPERATION,
    }
    result.update(overrides)
    return result


def _journal(recorder: OperationRecorder, operation_id: str = OPERATION) -> Any:
    return recorder.repository.store.conn.execute(
        "SELECT id, profile_name, flow_project_id, command, mode, status, prompt, "
        "prompt_hash, prompt_redacted, metadata_json FROM operations WHERE id = ?",
        (operation_id,),
    ).fetchone()


def _sheet(tmp_path: Path) -> Path:
    path = tmp_path / "original sheet.png"
    path.write_bytes(PNG_BYTES)
    return path


@pytest.mark.asyncio
async def test_import_records_started_and_identity_hashes_before_browser_mutation(
    tmp_path: Path, recorder: OperationRecorder
) -> None:
    sheet = _sheet(tmp_path)
    client: Any = _Client()

    def assert_started_before_mutation() -> None:
        row = _journal(recorder)
        assert row is not None
        assert row["status"] == "started"
        assert row["command"] == "character import"
        assert row["mode"] == "character"
        metadata = json.loads(row["metadata_json"])
        assert metadata["source_sha256"] == hashlib.sha256(PNG_BYTES).hexdigest()
        assert metadata["personality_hash"] == hashlib.sha256(PERSONALITY.encode()).hexdigest()
        assert PERSONALITY not in row["metadata_json"]

    client.before_import = assert_started_before_mutation

    result = await character_import(client, recorder, **_kwargs(tmp_path, sheet))  # type: ignore[arg-type]

    assert result.readback == client.import_result.readback
    assert result.source_sha256 == client.import_result.source_sha256
    assert len(client.import_calls) == 1
    row = _journal(recorder)
    assert row is not None
    assert row["status"] == "succeeded"
    assert row["prompt"] is None
    assert row["prompt_redacted"] == 1
    metadata = json.loads(row["metadata_json"])
    assert metadata["entity_id"] == ENTITY
    assert metadata["workflow_media_bindings"] == [[WORKFLOW, MEDIA]]
    assert PERSONALITY not in row["metadata_json"]


@pytest.mark.asyncio
async def test_succeeded_replay_verifies_exact_binding_without_upload(
    tmp_path: Path, recorder: OperationRecorder
) -> None:
    sheet = _sheet(tmp_path)
    client: Any = _Client()

    first = await character_import(client, recorder, **_kwargs(tmp_path, sheet))  # type: ignore[arg-type]
    client.import_calls.clear()

    replay = await character_import(client, recorder, **_kwargs(tmp_path, sheet))  # type: ignore[arg-type]

    assert client.import_calls == []
    assert client.read_calls == [(PROJECT, ENTITY)]
    assert replay.source_sha256 == first.source_sha256
    assert replay.readback.workflow_media_bindings == ((WORKFLOW, MEDIA),)


@pytest.mark.asyncio
async def test_completed_replay_refuses_changed_remote_binding_without_upload(
    tmp_path: Path, recorder: OperationRecorder
) -> None:
    sheet = _sheet(tmp_path)
    client: Any = _Client()
    await character_import(client, recorder, **_kwargs(tmp_path, sheet))  # type: ignore[arg-type]
    client.import_calls.clear()
    client.remote_readback = _readback(bindings=((WORKFLOW, OTHER_MEDIA),))

    with pytest.raises(ConfigurationError, match="not match the journaled import"):
        await character_import(client, recorder, **_kwargs(tmp_path, sheet))  # type: ignore[arg-type]

    assert client.import_calls == []
    assert client.read_calls == [(PROJECT, ENTITY)]


@pytest.mark.asyncio
async def test_idempotency_key_rejects_changed_inputs_without_browser_mutation(
    tmp_path: Path, recorder: OperationRecorder
) -> None:
    sheet = _sheet(tmp_path)
    client: Any = _Client()
    await character_import(client, recorder, **_kwargs(tmp_path, sheet))  # type: ignore[arg-type]
    client.import_calls.clear()
    changed_sheet = tmp_path / "changed.png"
    changed_sheet.write_bytes(PNG_BYTES + b"changed")

    changed_inputs = [
        _kwargs(tmp_path, sheet, name="Another name"),
        _kwargs(tmp_path, sheet, personality="A different personality"),
        _kwargs(tmp_path, sheet, sheet=changed_sheet),
        _kwargs(tmp_path, sheet, project_id=OTHER_PROJECT),
        _kwargs(tmp_path, sheet, profile_name="other-profile"),
    ]
    for kwargs in changed_inputs:
        with pytest.raises(ConfigurationError, match="already identifies a different import"):
            await character_import(client, recorder, **kwargs)  # type: ignore[arg-type]

    assert client.import_calls == []
    assert client.read_calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("checkpoint", [False, True], ids=["no-entity", "entity-checkpointed"])
@pytest.mark.parametrize("changed_field", ["sheet", "name", "personality"])
async def test_started_replay_rejects_changed_identity_before_client_access(
    tmp_path: Path,
    recorder: OperationRecorder,
    checkpoint: bool,
    changed_field: str,
) -> None:
    sheet = _sheet(tmp_path)
    client: Any = _Client()
    client.checkpoint = checkpoint
    client.fail_import = RuntimeError("interrupted import")

    with pytest.raises(RuntimeError, match="interrupted import"):
        await character_import(client, recorder, **_kwargs(tmp_path, sheet))  # type: ignore[arg-type]

    started = _journal(recorder)
    assert started is not None and started["status"] == "started"
    original_metadata = json.loads(started["metadata_json"])
    assert (original_metadata["entity_id"] is not None) is checkpoint
    client.import_calls.clear()
    client.read_calls.clear()
    client.fail_import = None

    changed_kwargs = _kwargs(tmp_path, sheet)
    if changed_field == "sheet":
        changed_sheet = tmp_path / "changed.png"
        changed_sheet.write_bytes(PNG_BYTES + b"changed")
        changed_kwargs["sheet"] = changed_sheet
    elif changed_field == "name":
        changed_kwargs["name"] = "Another name"
    else:
        changed_kwargs["personality"] = "A different personality"

    with pytest.raises(ConfigurationError, match="already identifies a different import"):
        await character_import(client, recorder, **changed_kwargs)  # type: ignore[arg-type]

    assert client.import_calls == []
    assert client.read_calls == []
    final = _journal(recorder)
    assert final is not None and final["status"] == "started"
    assert json.loads(final["metadata_json"]) == original_metadata


@pytest.mark.asyncio
async def test_uncertain_started_without_entity_refuses_recreation(
    tmp_path: Path, recorder: OperationRecorder
) -> None:
    sheet = _sheet(tmp_path)
    client: Any = _Client()
    client.checkpoint = False
    client.fail_import = RuntimeError("uncertain upload")

    with pytest.raises(RuntimeError, match="uncertain upload"):
        await character_import(client, recorder, **_kwargs(tmp_path, sheet))  # type: ignore[arg-type]
    row = _journal(recorder)
    assert row is not None and row["status"] == "started"
    client.fail_import = None
    client.import_calls.clear()

    with pytest.raises(ConfigurationError, match="no checkpointed entity") as exc:
        await character_import(client, recorder, **_kwargs(tmp_path, sheet))  # type: ignore[arg-type]

    assert "native Character list" in exc.value.remediation_hint
    assert client.import_calls == []
    assert client.read_calls == []


@pytest.mark.asyncio
async def test_uncertain_started_entity_is_read_but_never_reuploaded_without_pairs(
    tmp_path: Path, recorder: OperationRecorder
) -> None:
    sheet = _sheet(tmp_path)
    client: Any = _Client()
    client.fail_import = RuntimeError("uncertain save")

    with pytest.raises(RuntimeError, match="uncertain save"):
        await character_import(client, recorder, **_kwargs(tmp_path, sheet))  # type: ignore[arg-type]
    row = _journal(recorder)
    assert row is not None and row["status"] == "started"
    assert json.loads(row["metadata_json"])["entity_id"] == ENTITY
    client.fail_import = None
    client.import_calls.clear()

    with pytest.raises(ConfigurationError, match=ENTITY) as exc:
        await character_import(client, recorder, **_kwargs(tmp_path, sheet))  # type: ignore[arg-type]

    assert "native Character list" in exc.value.remediation_hint
    assert client.read_calls == [(PROJECT, ENTITY)]
    assert client.import_calls == []
    row = _journal(recorder)
    assert row is not None and row["status"] == "started"


@pytest.mark.asyncio
async def test_started_with_binding_checkpoint_reconciles_without_upload(
    tmp_path: Path, recorder: OperationRecorder, monkeypatch: pytest.MonkeyPatch
) -> None:
    sheet = _sheet(tmp_path)
    client: Any = _Client()
    original_update = recorder.repository.update_operation_metadata

    def fail_final_update(*_: Any, **__: Any) -> None:
        raise RuntimeError("interrupted after binding checkpoint")

    monkeypatch.setattr(recorder.repository, "update_operation_metadata", fail_final_update)
    with pytest.raises(RuntimeError, match="interrupted after binding checkpoint"):
        await character_import(client, recorder, **_kwargs(tmp_path, sheet))  # type: ignore[arg-type]

    row = _journal(recorder)
    assert row is not None and row["status"] == "started"
    assert json.loads(row["metadata_json"])["workflow_media_bindings"] == [[WORKFLOW, MEDIA]]
    monkeypatch.setattr(recorder.repository, "update_operation_metadata", original_update)
    client.import_calls.clear()

    replay = await character_import(client, recorder, **_kwargs(tmp_path, sheet))  # type: ignore[arg-type]

    assert client.import_calls == []
    assert client.read_calls == [(PROJECT, ENTITY)]
    assert replay.readback.workflow_media_bindings == ((WORKFLOW, MEDIA),)
    assert _journal(recorder)["status"] == "succeeded"


@pytest.mark.asyncio
async def test_invalid_image_does_not_create_operation_or_call_client(
    tmp_path: Path, recorder: OperationRecorder
) -> None:
    invalid = tmp_path / "not-an-image.png"
    invalid.write_text("not an image", encoding="utf-8")
    client: Any = _Client()

    with pytest.raises(ValueError, match="supported image format"):
        await character_import(client, recorder, **_kwargs(tmp_path, invalid))  # type: ignore[arg-type]

    assert client.import_calls == []
    count = recorder.repository.store.conn.execute("SELECT COUNT(*) FROM operations").fetchone()[0]
    assert count == 0


@pytest.mark.asyncio
async def test_invalid_idempotency_key_is_rejected_before_file_access(
    tmp_path: Path, recorder: OperationRecorder
) -> None:
    missing_sheet = tmp_path / "missing.png"
    client: Any = _Client()

    with pytest.raises(ConfigurationError, match="canonical UUID"):
        await character_import(
            client,
            recorder,
            **_kwargs(tmp_path, missing_sheet, operation_id="not-a-uuid"),
        )  # type: ignore[arg-type]

    assert client.import_calls == []
    count = recorder.repository.store.conn.execute("SELECT COUNT(*) FROM operations").fetchone()[0]
    assert count == 0
