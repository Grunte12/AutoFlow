from __future__ import annotations

import copy
import json
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import pytest

from gflow_cli.data.recorder import OperationRecorder
from gflow_cli.data.repository import DataRepository
from gflow_cli.data.store import DataStore
from gflow_cli.errors import ConfigurationError
from gflow_cli.services.character_update import character_update_images

PROFILE = "default"
PROJECT = "a0000000-0000-4000-8000-000000000001"
ENTITY = "b0000000-0000-4000-8000-000000000001"
WORKFLOW_PORTRAIT = "c0000000-0000-4000-8000-000000000001"
MEDIA_PORTRAIT = "d0000000-0000-4000-8000-000000000001"
WORKFLOW_BODY = "c0000000-0000-4000-8000-000000000002"
MEDIA_BODY = "d0000000-0000-4000-8000-000000000002"
OPERATION = "e0000000-0000-4000-8000-000000000001"
OTHER_MEDIA = "d0000000-0000-4000-8000-000000000003"
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8


@pytest.fixture
def recorder(tmp_path: Path) -> Any:
    with DataStore.open(tmp_path / "gflow.db") as store:
        yield OperationRecorder(DataRepository(store), prompt_mode="redacted")


def _initial_state() -> dict[str, Any]:
    return {
        "project": PROJECT,
        "entity_id": ENTITY,
        "metadata_sha256": "a" * 64,
        "images": {
            "portrait": {"workflow_id": WORKFLOW_PORTRAIT, "media_id": MEDIA_PORTRAIT},
            "full_body": {"workflow_id": WORKFLOW_BODY, "media_id": MEDIA_BODY},
        },
    }


class _Client:
    def __init__(self) -> None:
        self.state = _initial_state()
        self.read_calls: list[tuple[str, str]] = []
        self.replace_calls: list[dict[str, Any]] = []
        self.fail_after_checkpoint: Exception | None = None

    async def read_character_image_state(self, project_id: str, entity_id: str) -> dict[str, Any]:
        self.read_calls.append((project_id, entity_id))
        return copy.deepcopy(self.state)

    async def replace_character_images(
        self,
        *,
        project_id: str,
        entity_id: str,
        images: dict[str, bytes],
        before: dict[str, Any],
        checkpoint: Callable[[str, dict[str, str]], Awaitable[None]],
    ) -> dict[str, Any]:
        self.replace_calls.append(
            {
                "project_id": project_id,
                "entity_id": entity_id,
                "images": dict(images),
                "before": copy.deepcopy(before),
            }
        )
        bindings = {
            "portrait": {"workflow_id": WORKFLOW_PORTRAIT, "media_id": OTHER_MEDIA},
            "full_body": {"workflow_id": WORKFLOW_BODY, "media_id": OTHER_MEDIA},
        }
        for slot in images:
            self.state["images"][slot] = bindings[slot]
            await checkpoint(slot, bindings[slot])
            if self.fail_after_checkpoint is not None:
                error = self.fail_after_checkpoint
                self.fail_after_checkpoint = None
                raise error
        return copy.deepcopy(self.state)


def _kwargs(tmp_path: Path, **overrides: Any) -> dict[str, Any]:
    result: dict[str, Any] = {
        "profile_name": PROFILE,
        "profile_dir": tmp_path / "profile",
        "project_id": PROJECT,
        "entity_id": ENTITY,
        "operation_id": OPERATION,
    }
    result.update(overrides)
    return result


def _image(tmp_path: Path, name: str, data: bytes = PNG_BYTES) -> Path:
    path = tmp_path / name
    path.write_bytes(data)
    return path


def _operation(recorder: OperationRecorder) -> Any:
    return recorder.repository.store.conn.execute(
        "SELECT status, metadata_json FROM operations WHERE id = ?", (OPERATION,)
    ).fetchone()


@pytest.mark.asyncio
async def test_portrait_only_replacement_preserves_omitted_full_body(
    tmp_path: Path, recorder: OperationRecorder
) -> None:
    portrait = _image(tmp_path, "portrait.png")
    client = _Client()
    original_body = copy.deepcopy(client.state["images"]["full_body"])

    result = await character_update_images(client, recorder, **_kwargs(tmp_path, portrait=portrait))  # type: ignore[arg-type]

    assert result["status"] == "ok"
    assert set(result["images"]) == {"portrait"}
    assert client.state["images"]["portrait"]["media_id"] == OTHER_MEDIA
    assert client.state["images"]["full_body"] == original_body
    assert len(client.replace_calls) == 1
    assert client.replace_calls[0]["images"] == {"portrait": PNG_BYTES}
    row = _operation(recorder)
    assert row is not None and row["status"] == "succeeded"
    expected_state = json.loads(row["metadata_json"])["expected_state"]
    assert expected_state["images"]["full_body"] == original_body


@pytest.mark.asyncio
async def test_both_images_are_replaced_and_returned_with_source_hashes(
    tmp_path: Path, recorder: OperationRecorder
) -> None:
    portrait = _image(tmp_path, "portrait.png")
    full_body = _image(tmp_path, "full-body.png", PNG_BYTES + b"body")
    client = _Client()

    result = await character_update_images(
        client,
        recorder,
        **_kwargs(tmp_path, portrait=portrait, full_body=full_body),
    )  # type: ignore[arg-type]

    assert set(result["images"]) == {"portrait", "full_body"}
    assert result["images"]["portrait"]["source_sha256"]
    assert result["images"]["full_body"]["source_sha256"]
    assert client.state["images"]["portrait"]["media_id"] == OTHER_MEDIA
    assert client.state["images"]["full_body"]["media_id"] == OTHER_MEDIA
    assert len(client.replace_calls) == 1


@pytest.mark.asyncio
async def test_same_key_replay_reads_exact_state_without_replacing_again(
    tmp_path: Path, recorder: OperationRecorder
) -> None:
    portrait = _image(tmp_path, "portrait.png")
    client = _Client()
    first = await character_update_images(client, recorder, **_kwargs(tmp_path, portrait=portrait))  # type: ignore[arg-type]
    client.read_calls.clear()

    replay = await character_update_images(client, recorder, **_kwargs(tmp_path, portrait=portrait))  # type: ignore[arg-type]

    assert replay == first
    assert client.read_calls == [(PROJECT, ENTITY)]
    assert len(client.replace_calls) == 1


@pytest.mark.asyncio
async def test_same_key_changed_source_is_refused_without_remote_access(
    tmp_path: Path, recorder: OperationRecorder
) -> None:
    portrait = _image(tmp_path, "portrait.png")
    changed = _image(tmp_path, "changed.png", PNG_BYTES + b"changed")
    client = _Client()
    await character_update_images(client, recorder, **_kwargs(tmp_path, portrait=portrait))  # type: ignore[arg-type]
    client.read_calls.clear()

    with pytest.raises(ConfigurationError, match="different Character update"):
        await character_update_images(client, recorder, **_kwargs(tmp_path, portrait=changed))  # type: ignore[arg-type]

    assert client.read_calls == []
    assert len(client.replace_calls) == 1


@pytest.mark.asyncio
async def test_interrupted_mutation_is_not_reuploaded_on_replay(
    tmp_path: Path, recorder: OperationRecorder
) -> None:
    portrait = _image(tmp_path, "portrait.png")
    client = _Client()
    client.fail_after_checkpoint = RuntimeError("interrupted update")

    with pytest.raises(RuntimeError, match="interrupted update"):
        await character_update_images(client, recorder, **_kwargs(tmp_path, portrait=portrait))  # type: ignore[arg-type]

    row = _operation(recorder)
    assert row is not None and row["status"] == "started"
    with pytest.raises(ConfigurationError, match="lacks complete image checkpoints"):
        await character_update_images(client, recorder, **_kwargs(tmp_path, portrait=portrait))  # type: ignore[arg-type]
    assert len(client.replace_calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("drift", ["metadata", "untouched_slot"])
async def test_replay_refuses_metadata_or_untouched_slot_drift(
    tmp_path: Path, recorder: OperationRecorder, drift: str
) -> None:
    portrait = _image(tmp_path, "portrait.png")
    client = _Client()
    await character_update_images(client, recorder, **_kwargs(tmp_path, portrait=portrait))  # type: ignore[arg-type]
    if drift == "metadata":
        client.state["metadata_sha256"] = "f" * 64
    else:
        client.state["images"]["full_body"]["media_id"] = OTHER_MEDIA

    with pytest.raises(ConfigurationError, match="differ from the update checkpoint"):
        await character_update_images(client, recorder, **_kwargs(tmp_path, portrait=portrait))  # type: ignore[arg-type]
    assert len(client.replace_calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("project_id", "entity_id", "operation_id"),
    [
        ("not-a-uuid", ENTITY, OPERATION),
        (PROJECT, "not-a-uuid", OPERATION),
        (PROJECT, ENTITY, "not-a-uuid"),
    ],
)
async def test_invalid_identifiers_are_rejected_before_client_access(
    tmp_path: Path,
    recorder: OperationRecorder,
    project_id: str,
    entity_id: str,
    operation_id: str,
) -> None:
    portrait = _image(tmp_path, "portrait.png")
    client = _Client()

    with pytest.raises(ConfigurationError, match="canonical UUID"):
        await character_update_images(
            client,
            recorder,
            **_kwargs(
                tmp_path,
                project_id=project_id,
                entity_id=entity_id,
                operation_id=operation_id,
                portrait=portrait,
            ),
        )  # type: ignore[arg-type]

    assert client.read_calls == []
    assert client.replace_calls == []
