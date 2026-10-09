"""Offline tests for native Character sheet import (no image generation)."""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import pytest

from gflow_cli.api.character import Character
from gflow_cli.api.transports import migrated_composer
from gflow_cli.api.transports import native_character_import as importer
from gflow_cli.api.transports.native_character import NativeCharacterReadback
from gflow_cli.errors import ConfigurationError, WireFormatError

PROJECT = "a0000000-0000-4000-8000-000000000001"
ENTITY = "b0000000-0000-4000-8000-000000000001"
OTHER_ENTITY = "b0000000-0000-4000-8000-000000000002"
WORKFLOW = "c0000000-0000-4000-8000-000000000001"
OTHER_WORKFLOW = "c0000000-0000-4000-8000-000000000002"
MEDIA = "d0000000-0000-4000-8000-000000000001"
OTHER_MEDIA = "d0000000-0000-4000-8000-000000000002"
NAME = "Momo"
PERSONALITY = "Quiet, curious, and kind."
SHEET_BYTES = b"\x89PNG\r\n\x1a\n\x00\x00\x00\x0d"


def _upload_payload(
    *,
    media_id: str = MEDIA,
    media_project_id: str = PROJECT,
    media_workflow_id: str | None = WORKFLOW,
    workflow_id: str = WORKFLOW,
    workflow_media_id: str = MEDIA,
    workflow_project_id: str = PROJECT,
    parent_entity_id: str | None = ENTITY,
) -> list[object]:
    media_row: list[object] = [media_id, media_project_id, media_workflow_id, None]
    workflow_row: list[object] = [
        workflow_id,
        None,
        None,
        [NAME, [1, 2], None, None, workflow_media_id],
        workflow_project_id,
        parent_entity_id,
    ]
    return [media_row, workflow_row]


def _readback(
    *,
    entity_id: str = ENTITY,
    project_id: str = PROJECT,
    display_name: str = NAME,
    media_id: str = MEDIA,
) -> NativeCharacterReadback:
    return NativeCharacterReadback(
        character=Character(
            entity_id=entity_id,
            display_name=display_name,
            project_id=project_id,
            workflow_ids=(WORKFLOW,),
            voice=None,
            personality=None,
            thumbnail_media_id=media_id,
        ),
        workflow_media_bindings=((WORKFLOW, media_id),),
    )


class _Response:
    url = "https://flow.google.com/_/AiSandboxAngularFrontend/data/batchexecute?rpcids=maseQ"
    status = 200

    def __init__(self, body: str = "upload reply") -> None:
        self.body = body

    async def text(self) -> str:
        return self.body


class _FileChooser:
    def __init__(self, page: _FakePage) -> None:
        self.page = page
        self.files: list[dict[str, Any]] = []

    async def set_files(self, payload: dict[str, Any]) -> None:
        self.files.append(payload)
        self.page.events.append("upload")
        await self.page.emit_response(_Response("upload reply"))


class _ChooserContext:
    def __init__(self, page: _FakePage) -> None:
        self.page = page
        self.value: asyncio.Future[_FileChooser] = asyncio.get_running_loop().create_future()

    async def __aenter__(self) -> _ChooserContext:
        return self

    async def __aexit__(self, *_: Any) -> None:
        chooser = _FileChooser(self.page)
        self.page.file_chooser = chooser
        self.value.set_result(chooser)


class _Locator:
    def __init__(self, page: _FakePage, selector: str) -> None:
        self.page = page
        self.selector = selector

    async def count(self) -> int:
        return self.page.counts.get(self.selector, 1)

    async def wait_for(self, **_: Any) -> None:
        self.page.events.append(f"wait:{self.selector}:{_.get('state')}")

    async def click(self, **_: Any) -> None:
        self.page.clicks.append(self.selector)
        self.page.events.append(f"click:{self.selector}")
        if '[role="menuitem"]' in self.selector:
            self.page.url = self.page.character_url
        elif self.selector.startswith("flow-character-edit-header"):
            self.page.saved_name = self.page.name_value
            self.page.saved_personality = self.page.personality_value
            self.page.done_clicked = True

    async def fill(self, value: str, **_: Any) -> None:
        self.page.events.append(f"fill:{self.selector}")
        if "name-input" in self.selector:
            self.page.name_value = value
        elif "personality-textarea" in self.selector:
            self.page.personality_value = value

    async def press(self, key: str) -> None:
        self.page.events.append(f"press:{self.selector}:{key}")
        if key == "Tab" and self.selector in {
            "flow-character-form input.name-input",
            "flow-character-form textarea.personality-textarea",
        }:
            if self.page.metadata_ack_mode != "missing":
                response = _Response(f"metadata reply:{json.dumps(self.page.metadata_payload())}")
                await self.page.emit_response(response)
                if (
                    self.page.metadata_ack_mode in {"exact", "no-refs"}
                    and self.page.name_value == self.page.requested_name
                    and self.page.personality_value == self.page.requested_personality
                ):
                    self.page.events.append("metadata-ack")

    async def input_value(self) -> str:
        if "name-input" in self.selector:
            return self.page.name_value
        if "personality-textarea" in self.selector:
            return self.page.personality_value
        raise AssertionError(f"unexpected input selector: {self.selector}")


class _FakePage:
    def __init__(self, *, name: str = "Existing name") -> None:
        self.character_url = f"https://flow.google.com/project/{PROJECT}/character/{ENTITY}"
        self.url = f"https://flow.google.com/project/{PROJECT}"
        self.name_value = name
        self.personality_value = "Existing personality"
        self.requested_name = NAME
        self.requested_personality: str | None = PERSONALITY
        self.metadata_ack_mode = "exact"
        self.saved_name: str | None = None
        self.saved_personality: str | None = None
        self.reloaded_name: str | None = None
        self.reloaded_personality: str | None = None
        self.done_clicked = False
        self.gotos: list[tuple[str, dict[str, Any]]] = []
        self.clicks: list[str] = []
        self.events: list[str] = []
        self.counts: dict[str, int] = {}
        self.handlers: list[Callable[[Any], Awaitable[None]]] = []
        self.chooser_count = 0
        self.file_chooser: _FileChooser | None = None

    def metadata_payload(self) -> list[list[Any]]:
        entity_id = OTHER_ENTITY if self.metadata_ack_mode == "mismatch" else ENTITY
        references = [] if self.metadata_ack_mode == "no-refs" else [[WORKFLOW]]
        character_info = [references, None, self.personality_value]
        return [[PROJECT, entity_id, None, [1, self.name_value, character_info]]]

    def locator(self, selector: str) -> _Locator:
        return _Locator(self, selector)

    async def goto(self, url: str, **kwargs: Any) -> None:
        self.gotos.append((url, kwargs))
        self.url = url
        if self.done_clicked:
            self.name_value = self.reloaded_name or self.saved_name or self.name_value
            self.personality_value = (
                self.reloaded_personality
                if self.reloaded_personality is not None
                else self.saved_personality or self.personality_value
            )

    async def wait_for_function(self, expression: str, **kwargs: Any) -> None:
        self.events.append(f"function:{expression}")
        self.events.append(f"function-arg:{kwargs.get('arg')}")

    def expect_file_chooser(self, **_: Any) -> _ChooserContext:
        self.chooser_count += 1
        return _ChooserContext(self)

    def on(self, event: str, handler: Callable[[Any], Awaitable[None]]) -> None:
        assert event == "response"
        self.handlers.append(handler)

    def remove_listener(self, event: str, handler: Callable[[Any], Awaitable[None]]) -> None:
        assert event == "response"
        self.handlers.remove(handler)

    async def emit_response(self, response: Any) -> None:
        for handler in tuple(self.handlers):
            await handler(response)


class _Readbacks:
    def __init__(self) -> None:
        self.existing: list[NativeCharacterReadback] = []
        self.verified = _readback()
        self.list_calls: list[tuple[Any, str]] = []
        self.verified_calls: list[tuple[Any, str, str]] = []
        self.verified_responses: list[NativeCharacterReadback | WireFormatError] | None = None

    async def list_characters(self, page: Any, project_id: str) -> list[NativeCharacterReadback]:
        self.list_calls.append((page, project_id))
        return self.existing

    async def read_verified(
        self, page: Any, project_id: str, entity_id: str
    ) -> NativeCharacterReadback:
        self.verified_calls.append((page, project_id, entity_id))
        page.events.append("verified-readback")
        if self.verified_responses is not None:
            response = self.verified_responses[len(self.verified_calls) - 1]
            if isinstance(response, WireFormatError):
                raise response
            return response
        return self.verified


@pytest.fixture
def readbacks(monkeypatch: pytest.MonkeyPatch) -> _Readbacks:
    harness = _Readbacks()
    upload_payload = _upload_payload()

    def parse_fixture_frames(body: str) -> list[tuple[str, object]]:
        if body == "upload reply":
            return [("maseQ", upload_payload)]
        if body.startswith("metadata reply:"):
            payload = json.loads(body.removeprefix("metadata reply:"))
            return [("rzMKMb", payload)]
        return []

    monkeypatch.setattr(importer, "read_native_characters", harness.list_characters)
    monkeypatch.setattr(importer, "read_verified_native_character", harness.read_verified)
    monkeypatch.setattr(importer, "parse_frames", parse_fixture_frames)
    monkeypatch.setattr(
        migrated_composer,
        "parse_frames",
        parse_fixture_frames,
    )
    return harness


def _sheet(tmp_path: Path) -> tuple[Path, bytes]:
    path = tmp_path / "original-sheet.png"
    path.write_bytes(SHEET_BYTES)
    return path, SHEET_BYTES


async def test_invalid_inputs_fail_before_any_page_gesture(tmp_path: Path) -> None:
    valid_sheet, _ = _sheet(tmp_path)
    cases: list[tuple[dict[str, Any], type[Exception]]] = [
        ({"project_id": "not-a-uuid"}, ValueError),
        ({"name": "  "}, ValueError),
        ({"sheet": tmp_path / "missing.png"}, FileNotFoundError),
    ]

    for overrides, expected_error in cases:
        page = _FakePage()
        kwargs: dict[str, Any] = {
            "project_id": PROJECT,
            "name": NAME,
            "sheet": valid_sheet,
            "on_entity_created": _noop_checkpoint,
        }
        kwargs.update(overrides)
        with pytest.raises(expected_error):
            await importer.import_native_character(page, **kwargs)  # type: ignore[arg-type]

        assert page.gotos == []
        assert page.clicks == []
        assert page.chooser_count == 0
        assert page.handlers == []


async def _noop_checkpoint(_entity_id: str) -> None:
    return None


async def test_create_uploads_original_and_checkpoints_before_metadata_save(
    tmp_path: Path,
    readbacks: _Readbacks,
) -> None:
    sheet, original_bytes = _sheet(tmp_path)
    page = _FakePage(name="")
    checkpoints: list[str] = []

    async def checkpoint(entity_id: str) -> None:
        checkpoints.append(entity_id)
        page.events.append(f"checkpoint:{entity_id}")

    result = await importer.import_native_character(
        page,  # type: ignore[arg-type]
        project_id=PROJECT,
        name=NAME,
        sheet=sheet,
        personality=PERSONALITY,
        on_entity_created=checkpoint,
    )

    assert isinstance(result, importer.NativeCharacterImportResult)
    assert result.readback.character.entity_id == ENTITY
    assert result.readback.character.project_id == PROJECT
    assert result.readback.character.display_name == NAME
    assert result.readback.character.personality == PERSONALITY
    assert result.readback.workflow_media_bindings == ((WORKFLOW, MEDIA),)
    assert result.source_sha256 == hashlib.sha256(original_bytes).hexdigest()
    assert checkpoints == [ENTITY]
    assert readbacks.list_calls == [(page, PROJECT)]
    assert readbacks.verified_calls == [(page, PROJECT, ENTITY)]
    assert page.file_chooser is not None
    assert page.file_chooser.files == [
        {"name": sheet.name, "mimeType": "image/png", "buffer": original_bytes}
    ]
    assert page.chooser_count == 1
    assert page.handlers == []
    assert any(event == f"checkpoint:{ENTITY}" for event in page.events)
    checkpoint_index = page.events.index(f"checkpoint:{ENTITY}")
    pending_tile_index = page.events.index(
        "wait:flow-character-edit-page flow-pending-tile:detached"
    )
    name_index = page.events.index("fill:flow-character-form input.name-input")
    metadata_ack_index = page.events.index("metadata-ack")
    done_index = page.events.index("click:flow-character-edit-header button.flow-button-secondary")
    upload_index = page.events.index("upload")
    assert upload_index < checkpoint_index < pending_tile_index < name_index
    assert name_index < metadata_ack_index < done_index
    assert not any("generate" in selector.lower() for selector in page.clicks)


async def test_duplicate_name_requires_explicit_entity_instead_of_reuse(
    tmp_path: Path,
    readbacks: _Readbacks,
) -> None:
    sheet, _ = _sheet(tmp_path)
    page = _FakePage(name="")
    readbacks.existing = [_readback(entity_id=OTHER_ENTITY, display_name=NAME)]

    with pytest.raises(ConfigurationError, match="inspect it and the operation journal"):
        await importer.import_native_character(
            page,  # type: ignore[arg-type]
            project_id=PROJECT,
            name=NAME,
            sheet=sheet,
            on_entity_created=_noop_checkpoint,
        )

    assert readbacks.list_calls == [(page, PROJECT)]
    assert page.gotos == []
    assert page.clicks == []
    assert page.chooser_count == 0


def test_parse_upload_reply_returns_exact_observed_bindings() -> None:
    assert importer._parse_upload_reply(_upload_payload(), PROJECT) == (MEDIA, WORKFLOW, ENTITY)


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        [_upload_payload()[0]],
        ["unrelated", _upload_payload()[1]],
        # Real UUIDs elsewhere do not compensate for an absent workflow binding.
        _upload_payload(media_workflow_id=None),
    ],
)
def test_parse_upload_reply_rejects_malformed_or_unattributable_shape(payload: object) -> None:
    with pytest.raises(WireFormatError):
        importer._parse_upload_reply(payload, PROJECT)


@pytest.mark.parametrize(
    "payload",
    [
        _upload_payload(media_project_id=OTHER_ENTITY),
        _upload_payload(workflow_project_id=OTHER_ENTITY),
    ],
)
def test_parse_upload_reply_rejects_foreign_project(payload: list[object]) -> None:
    with pytest.raises(WireFormatError):
        importer._parse_upload_reply(payload, PROJECT)


def test_parse_upload_reply_rejects_workflow_mismatch() -> None:
    with pytest.raises(WireFormatError):
        importer._parse_upload_reply(_upload_payload(media_workflow_id=OTHER_WORKFLOW), PROJECT)


def test_parse_upload_reply_rejects_media_mismatch() -> None:
    with pytest.raises(WireFormatError):
        importer._parse_upload_reply(_upload_payload(workflow_media_id=OTHER_MEDIA), PROJECT)


def test_parse_upload_reply_rejects_missing_parent_entity() -> None:
    with pytest.raises(WireFormatError):
        importer._parse_upload_reply(_upload_payload(parent_entity_id=None), PROJECT)


@pytest.mark.parametrize(
    "payload",
    [
        _upload_payload(media_id=PROJECT),
        _upload_payload(workflow_id=ENTITY),
        _upload_payload(parent_entity_id=MEDIA),
        _upload_payload(media_id="not-a-uuid"),
    ],
)
def test_parse_upload_reply_rejects_duplicate_or_noncanonical_ids(
    payload: list[object],
) -> None:
    with pytest.raises(WireFormatError):
        importer._parse_upload_reply(payload, PROJECT)


async def test_checkpoint_failure_stops_before_done_and_cleans_upload_listener(
    tmp_path: Path,
    readbacks: _Readbacks,
) -> None:
    sheet, _ = _sheet(tmp_path)
    page = _FakePage(name="")
    checkpoints: list[str] = []

    async def failing_checkpoint(entity_id: str) -> None:
        checkpoints.append(entity_id)
        raise RuntimeError("checkpoint persistence failed")

    with pytest.raises(RuntimeError, match="checkpoint persistence failed"):
        await importer.import_native_character(
            page,  # type: ignore[arg-type]
            project_id=PROJECT,
            name=NAME,
            sheet=sheet,
            on_entity_created=failing_checkpoint,
        )

    assert checkpoints == [ENTITY]
    assert not any(selector.startswith("flow-character-edit-header") for selector in page.clicks)
    assert not any(event.startswith("fill:") for event in page.events)
    assert page.handlers == []
    assert readbacks.verified_calls == []


async def test_verified_readback_must_bind_the_uploaded_media_to_the_exact_entity(
    tmp_path: Path,
    readbacks: _Readbacks,
) -> None:
    sheet, _ = _sheet(tmp_path)
    page = _FakePage(name="")
    readbacks.verified = _readback(media_id=OTHER_MEDIA)

    with pytest.raises(WireFormatError, match="not bound to the requested entity"):
        await importer.import_native_character(
            page,  # type: ignore[arg-type]
            project_id=PROJECT,
            name=NAME,
            sheet=sheet,
            on_entity_created=_noop_checkpoint,
        )

    assert readbacks.verified_calls == [(page, PROJECT, ENTITY)]
    assert page.handlers == []


@pytest.mark.parametrize("readback_media", [MEDIA, OTHER_MEDIA])
async def test_metadata_ack_without_image_refs_still_requires_exact_readback(
    tmp_path: Path,
    readbacks: _Readbacks,
    readback_media: str,
) -> None:
    sheet, _ = _sheet(tmp_path)
    page = _FakePage(name="")
    page.metadata_ack_mode = "no-refs"
    readbacks.verified = _readback(media_id=readback_media)

    if readback_media == MEDIA:
        result = await importer.import_native_character(
            page,  # type: ignore[arg-type]
            project_id=PROJECT,
            name=NAME,
            sheet=sheet,
            personality=PERSONALITY,
            on_entity_created=_noop_checkpoint,
        )
        assert result.readback.workflow_media_bindings == ((WORKFLOW, MEDIA),)
    else:
        with pytest.raises(WireFormatError, match="not bound to the requested entity"):
            await importer.import_native_character(
                page,  # type: ignore[arg-type]
                project_id=PROJECT,
                name=NAME,
                sheet=sheet,
                personality=PERSONALITY,
                on_entity_created=_noop_checkpoint,
            )

    done_index = page.events.index("click:flow-character-edit-header button.flow-button-secondary")
    assert "metadata-ack" in page.events
    assert page.events.index("metadata-ack") < done_index < page.events.index("verified-readback")
    assert readbacks.verified_calls == [(page, PROJECT, ENTITY)]
    assert page.chooser_count == 1
    assert page.file_chooser is not None and len(page.file_chooser.files) == 1


def _wire_format_error(reason: str) -> WireFormatError:
    return WireFormatError(
        f"unexpected native character response: {reason}",
        route="native:projectInitialData",
    )


def _skip_import_waits(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    waits: list[float] = []

    async def record_wait(seconds: float) -> None:
        waits.append(seconds)

    monkeypatch.setattr(importer.asyncio, "sleep", record_wait)
    return waits


async def test_transitional_readbacks_can_succeed_on_third_attempt_without_reupload(
    tmp_path: Path,
    readbacks: _Readbacks,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sheet, _ = _sheet(tmp_path)
    page = _FakePage(name="")
    readbacks.verified_responses = [
        _wire_format_error("character has no workflow references to verify"),
        _wire_format_error("referenced workflow is missing"),
        _readback(),
    ]
    waits = _skip_import_waits(monkeypatch)

    result = await importer.import_native_character(
        page,  # type: ignore[arg-type]
        project_id=PROJECT,
        name=NAME,
        sheet=sheet,
        personality=PERSONALITY,
        on_entity_created=_noop_checkpoint,
    )

    assert result.readback.workflow_media_bindings == ((WORKFLOW, MEDIA),)
    assert len(readbacks.verified_calls) == 3
    assert waits == [1, 1]
    assert page.chooser_count == 1
    assert page.file_chooser is not None and len(page.file_chooser.files) == 1


async def test_transitional_readbacks_fail_on_third_attempt_without_reupload(
    tmp_path: Path,
    readbacks: _Readbacks,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sheet, _ = _sheet(tmp_path)
    page = _FakePage(name="")
    final_error = _wire_format_error("referenced workflow is missing")
    readbacks.verified_responses = [
        _wire_format_error("character has no workflow references to verify"),
        _wire_format_error("referenced workflow is missing"),
        final_error,
    ]
    waits = _skip_import_waits(monkeypatch)

    with pytest.raises(WireFormatError, match="referenced workflow is missing"):
        await importer.import_native_character(
            page,  # type: ignore[arg-type]
            project_id=PROJECT,
            name=NAME,
            sheet=sheet,
            personality=PERSONALITY,
            on_entity_created=_noop_checkpoint,
        )

    assert len(readbacks.verified_calls) == 3
    assert waits == [1, 1]
    assert page.chooser_count == 1
    assert page.file_chooser is not None and len(page.file_chooser.files) == 1


async def test_stale_project_name_is_read_again_without_reupload(
    tmp_path: Path,
    readbacks: _Readbacks,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sheet, _ = _sheet(tmp_path)
    page = _FakePage(name="")
    readbacks.verified_responses = [_readback(display_name="Old name"), _readback()]
    waits = _skip_import_waits(monkeypatch)
    result = await importer.import_native_character(
        page,  # type: ignore[arg-type]
        project_id=PROJECT,
        name=NAME,
        sheet=sheet,
        personality=PERSONALITY,
        on_entity_created=_noop_checkpoint,
    )
    assert result.readback.character.display_name == NAME
    assert len(readbacks.verified_calls) == 2
    assert waits == [1]
    assert page.chooser_count == 1


@pytest.mark.parametrize(
    "reason",
    [
        "workflow parent entity does not match the character",
        "workflow project id does not match the requested project",
    ],
)
async def test_wrong_parent_or_project_readback_is_never_retried(
    tmp_path: Path,
    readbacks: _Readbacks,
    monkeypatch: pytest.MonkeyPatch,
    reason: str,
) -> None:
    sheet, _ = _sheet(tmp_path)
    page = _FakePage(name="")
    readbacks.verified_responses = [
        _wire_format_error("character has no workflow references to verify"),
        _wire_format_error(reason),
        _readback(),
    ]
    waits = _skip_import_waits(monkeypatch)

    with pytest.raises(WireFormatError, match=reason):
        await importer.import_native_character(
            page,  # type: ignore[arg-type]
            project_id=PROJECT,
            name=NAME,
            sheet=sheet,
            personality=PERSONALITY,
            on_entity_created=_noop_checkpoint,
        )

    assert len(readbacks.verified_calls) == 2
    assert waits == [1]
    assert page.chooser_count == 1
    assert page.file_chooser is not None and len(page.file_chooser.files) == 1


@pytest.mark.parametrize("mismatch", ["project-name", "personality"])
async def test_fresh_metadata_mismatch_is_not_reported_as_success(
    tmp_path: Path,
    readbacks: _Readbacks,
    mismatch: str,
) -> None:
    sheet, _ = _sheet(tmp_path)
    page = _FakePage(name="")
    if mismatch == "project-name":
        readbacks.verified = _readback(display_name="Stale name")
    else:
        page.reloaded_personality = "Stale personality"

    with pytest.raises(WireFormatError):
        await importer.import_native_character(
            page,  # type: ignore[arg-type]
            project_id=PROJECT,
            name=NAME,
            sheet=sheet,
            personality=PERSONALITY,
            on_entity_created=_noop_checkpoint,
        )

    assert page.done_clicked
    assert page.handlers == []


@pytest.mark.parametrize("ack_mode", ["mismatch", "missing"])
async def test_metadata_ack_must_match_before_done_and_uses_short_offline_wait(
    tmp_path: Path,
    readbacks: _Readbacks,
    monkeypatch: pytest.MonkeyPatch,
    ack_mode: str,
) -> None:
    sheet, _ = _sheet(tmp_path)
    page = _FakePage(name="")
    page.metadata_ack_mode = ack_mode
    original_wait_for = asyncio.wait_for

    async def short_wait_for(awaitable: Any, timeout: float | None = None) -> Any:
        if timeout == 30:
            timeout = 0.01
        return await original_wait_for(awaitable, timeout)

    monkeypatch.setattr(importer.asyncio, "wait_for", short_wait_for)

    with pytest.raises(WireFormatError, match="metadata acknowledgement did not arrive"):
        await importer.import_native_character(
            page,  # type: ignore[arg-type]
            project_id=PROJECT,
            name=NAME,
            sheet=sheet,
            personality=PERSONALITY,
            on_entity_created=_noop_checkpoint,
        )

    assert not page.done_clicked
    assert page.handlers == []
