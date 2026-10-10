from __future__ import annotations

import copy
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest

from gflow_cli.api.transports import native_character_update
from gflow_cli.api.transports.native_character_update import (
    parse_character_image_state,
    replace_character_images,
)
from gflow_cli.errors import ConfigurationError, WireFormatError

PROJECT = "a0000000-0000-4000-8000-000000000001"
OTHER_PROJECT = "a0000000-0000-4000-8000-000000000002"
ENTITY = "b0000000-0000-4000-8000-000000000001"
OTHER_ENTITY = "b0000000-0000-4000-8000-000000000002"
PORTRAIT_WORKFLOW = "c0000000-0000-4000-8000-000000000001"
BODY_WORKFLOW = "c0000000-0000-4000-8000-000000000002"
OTHER_WORKFLOW = "c0000000-0000-4000-8000-000000000003"
PORTRAIT_MEDIA = "d0000000-0000-4000-8000-000000000001"
BODY_MEDIA = "d0000000-0000-4000-8000-000000000002"
OTHER_MEDIA = "d0000000-0000-4000-8000-000000000003"
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8
JPEG_BYTES = b"\xff\xd8\xff" + b"\x00" * 9


def _workflow(
    workflow_id: str,
    media_id: str,
    *,
    project_id: str = PROJECT,
    parent_entity_id: str = ENTITY,
) -> list[Any]:
    return [
        workflow_id,
        None,
        None,
        ["character image", [1, 2], None, None, media_id, None, [3, 4]],
        project_id,
        parent_entity_id,
    ]


def _entity(
    image_refs: object,
    *,
    project_id: str = PROJECT,
    entity_id: str = ENTITY,
    name: str = "Momo",
    voice: object = "Aoede",
    personality: object = "gentle",
    extra: object = "stable-extra-metadata",
) -> list[Any]:
    return [
        project_id,
        entity_id,
        None,
        [1, name, [image_refs, voice, personality, extra]],
        None,
        [1086, 1448],
        [1, 2],
        [3, 4],
    ]


def _payload(
    image_refs: object,
    *,
    workflows: list[Any] | None = None,
    entity: list[Any] | None = None,
    entities: list[Any] | None = None,
) -> list[Any]:
    if workflows is None:
        refs = image_refs if isinstance(image_refs, list) else []
        workflow_ids = []
        for ref in refs:
            if isinstance(ref, list) and ref and isinstance(ref[0], str):
                workflow_ids.append(ref[0])
        media = {
            PORTRAIT_WORKFLOW: PORTRAIT_MEDIA,
            BODY_WORKFLOW: BODY_MEDIA,
            OTHER_WORKFLOW: OTHER_MEDIA,
        }
        workflows = [_workflow(workflow_id, media[workflow_id]) for workflow_id in workflow_ids]
    selected_entities = entities or [entity or _entity(image_refs)]
    return [None, workflows, None, None, None, selected_entities]


def _state(payload: object) -> dict[str, Any]:
    return parse_character_image_state(payload, PROJECT, ENTITY)


def test_parser_maps_portrait_and_empty_body_slot() -> None:
    state = _state(_payload([[PORTRAIT_WORKFLOW], []]))

    assert state["project"] == PROJECT
    assert state["entity_id"] == ENTITY
    assert len(state["metadata_sha256"]) == 64
    assert state["images"] == {
        "portrait": {"workflow_id": PORTRAIT_WORKFLOW, "media_id": PORTRAIT_MEDIA},
        "full_body": None,
    }


def test_parser_maps_both_slots() -> None:
    state = _state(_payload([[PORTRAIT_WORKFLOW], [BODY_WORKFLOW]]))

    assert state["images"] == {
        "portrait": {"workflow_id": PORTRAIT_WORKFLOW, "media_id": PORTRAIT_MEDIA},
        "full_body": {"workflow_id": BODY_WORKFLOW, "media_id": BODY_MEDIA},
    }


def test_parser_maps_body_only_placeholder() -> None:
    state = _state(_payload([None, [BODY_WORKFLOW]]))

    assert state["images"] == {
        "portrait": None,
        "full_body": {"workflow_id": BODY_WORKFLOW, "media_id": BODY_MEDIA},
    }


@pytest.mark.parametrize("image_refs", [[], [None, None], [[], None]])
def test_parser_accepts_both_slots_empty(image_refs: object) -> None:
    state = _state(_payload(image_refs))

    assert state["images"] == {"portrait": None, "full_body": None}


def test_image_reference_changes_do_not_change_metadata_fingerprint() -> None:
    before = _state(_payload([[PORTRAIT_WORKFLOW], []]))
    after = _state(_payload([[OTHER_WORKFLOW], [BODY_WORKFLOW]]))

    assert before["metadata_sha256"] == after["metadata_sha256"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("name", "Renamed"),
        ("voice", "Charon"),
        ("personality", "brave"),
    ],
)
def test_metadata_fingerprint_changes_when_character_metadata_changes(
    field: str, value: str
) -> None:
    baseline = _state(_payload([[PORTRAIT_WORKFLOW], []]))
    entity = _entity(
        [[PORTRAIT_WORKFLOW]],
        **{field: value},
    )
    changed = _state(_payload([[PORTRAIT_WORKFLOW]], entity=entity))

    assert baseline["metadata_sha256"] != changed["metadata_sha256"]


@pytest.mark.parametrize(
    "payload",
    [
        _payload(
            [[PORTRAIT_WORKFLOW]],
            workflows=[_workflow(PORTRAIT_WORKFLOW, PORTRAIT_MEDIA, project_id=OTHER_PROJECT)],
        ),
        _payload(
            [[PORTRAIT_WORKFLOW]],
            workflows=[_workflow(PORTRAIT_WORKFLOW, PORTRAIT_MEDIA, parent_entity_id=OTHER_ENTITY)],
        ),
        _payload([[PORTRAIT_WORKFLOW]], workflows=[]),
        _payload(
            [[PORTRAIT_WORKFLOW]],
            workflows=[
                _workflow(PORTRAIT_WORKFLOW, PORTRAIT_MEDIA),
                _workflow(PORTRAIT_WORKFLOW, OTHER_MEDIA),
            ],
        ),
        _payload([[PORTRAIT_WORKFLOW], [PORTRAIT_WORKFLOW]]),
        _payload([[PORTRAIT_WORKFLOW], [BODY_WORKFLOW], [OTHER_WORKFLOW]]),
        _payload("not-an-array"),
        _payload(
            [["not-a-uuid"]],
            workflows=[_workflow("not-a-uuid", PORTRAIT_MEDIA)],
        ),
        _payload(
            [[PORTRAIT_WORKFLOW]],
            workflows=[_workflow(PORTRAIT_WORKFLOW, "not-a-uuid")],
        ),
        _payload(
            [[PORTRAIT_WORKFLOW]],
            entities=[_entity([[PORTRAIT_WORKFLOW]]), _entity([[PORTRAIT_WORKFLOW]])],
        ),
        _payload(
            [[PORTRAIT_WORKFLOW]],
            entity=_entity([[PORTRAIT_WORKFLOW]], project_id=OTHER_PROJECT),
        ),
    ],
    ids=[
        "foreign-project-workflow",
        "foreign-parent-entity",
        "missing-workflow",
        "duplicate-workflow-row",
        "duplicate-slot-reference",
        "too-many-slots",
        "invalid-reference-container",
        "invalid-workflow-uuid",
        "invalid-media-uuid",
        "duplicate-character-entity",
        "foreign-character-project",
    ],
)
def test_parser_rejects_ambiguous_or_malformed_native_state(payload: object) -> None:
    with pytest.raises(WireFormatError):
        _state(payload)


@pytest.mark.parametrize(
    ("project_id", "entity_id"),
    [("not-a-uuid", ENTITY), (PROJECT, "not-a-uuid")],
)
def test_parser_rejects_noncanonical_requested_identifiers(project_id: str, entity_id: str) -> None:
    with pytest.raises(WireFormatError):
        parse_character_image_state(_payload([[], []]), project_id, entity_id)


class _Button:
    def __init__(self, clicked: list[int] | None = None, index: int | None = None) -> None:
        self.clicked = clicked
        self.index = index

    async def click(self, **_: Any) -> None:
        if self.clicked is not None and self.index is not None:
            self.clicked.append(self.index)

    async def wait_for(self, **_: Any) -> None:
        return None


class _Slots:
    def __init__(self, clicked: list[int]) -> None:
        self.clicked = clicked

    async def count(self) -> int:
        return 2

    def nth(self, index: int) -> _Button:
        return _Button(self.clicked, index)


class _Page:
    def __init__(self) -> None:
        self.url = "about:blank"
        self.navigations: list[str] = []
        self.clicked_slots: list[int] = []

    async def goto(self, url: str, **_: Any) -> None:
        self.url = url
        self.navigations.append(url)

    async def wait_for_function(self, *_: Any, **__: Any) -> None:
        return None

    def locator(self, selector: str) -> Any:
        if selector == "flow-slot-chip-button button":
            return _Slots(self.clicked_slots)
        return _Button()


def _native_state() -> dict[str, Any]:
    return {
        "project": PROJECT,
        "entity_id": ENTITY,
        "metadata_sha256": "a" * 64,
        "images": {
            "portrait": {"workflow_id": PORTRAIT_WORKFLOW, "media_id": PORTRAIT_MEDIA},
            "full_body": {"workflow_id": BODY_WORKFLOW, "media_id": BODY_MEDIA},
        },
    }


def _prepare_driver_mocks(
    monkeypatch: pytest.MonkeyPatch,
    *,
    before: dict[str, Any] | None = None,
) -> tuple[_Page, AsyncMock, AsyncMock, AsyncMock, list[tuple[str, dict[str, str]]]]:
    page = _Page()
    current = before or _native_state()
    read = AsyncMock(side_effect=lambda *_: current)
    clear = AsyncMock()
    checkpoints: list[tuple[str, dict[str, str]]] = []
    bindings = {
        "portrait": {"workflow_id": OTHER_WORKFLOW, "media_id": OTHER_MEDIA},
        "full_body": {"workflow_id": BODY_WORKFLOW, "media_id": OTHER_MEDIA},
    }

    async def upload(_page: Any, _project: str, _entity: str, source: bytes) -> dict[str, str]:
        slot = "portrait" if source == PNG_BYTES else "full_body"
        current["images"][slot] = bindings[slot]
        return bindings[slot]

    async def checkpoint(slot: str, binding: dict[str, str]) -> None:
        checkpoints.append((slot, binding))

    monkeypatch.setattr(native_character_update, "read_character_image_state", read)
    monkeypatch.setattr(native_character_update, "_clear_slot", clear)
    upload_mock = AsyncMock(side_effect=upload)
    monkeypatch.setattr(native_character_update, "_upload_slot", upload_mock)
    monkeypatch.setattr(
        native_character_update,
        "unique_character_control",
        AsyncMock(return_value=_Button()),
    )
    return page, read, clear, upload_mock, checkpoints


@pytest.mark.asyncio
async def test_driver_rejects_invalid_images_and_slots_before_navigation() -> None:
    page = _Page()
    before = _native_state()
    checkpoint = AsyncMock()

    with pytest.raises(ValueError):
        await replace_character_images(
            page,  # type: ignore[arg-type]
            project_id=PROJECT,
            entity_id=ENTITY,
            images={"portrait": b"not an image"},
            before=before,
            checkpoint=checkpoint,
        )
    with pytest.raises(ValueError):
        await replace_character_images(
            page,  # type: ignore[arg-type]
            project_id=PROJECT,
            entity_id=ENTITY,
            images={"unknown": PNG_BYTES},
            before=before,
            checkpoint=checkpoint,
        )

    assert page.navigations == []
    checkpoint.assert_not_called()


@pytest.mark.asyncio
async def test_driver_refuses_before_state_drift_before_clear_or_upload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page, read, clear, upload, _checkpoints = _prepare_driver_mocks(monkeypatch)
    before = _native_state()
    drifted = _native_state()
    drifted["images"]["portrait"]["media_id"] = OTHER_MEDIA
    read.side_effect = [drifted]

    with pytest.raises(ConfigurationError, match="changed before image replacement"):
        await replace_character_images(
            page,  # type: ignore[arg-type]
            project_id=PROJECT,
            entity_id=ENTITY,
            images={"portrait": PNG_BYTES},
            before=before,
            checkpoint=AsyncMock(),
        )

    assert page.navigations == []
    clear.assert_not_called()
    upload.assert_not_called()


@pytest.mark.asyncio
async def test_driver_maps_both_slots_checkpoints_and_verifies_fresh_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page, read, clear, upload, checkpoints = _prepare_driver_mocks(monkeypatch)
    before = _native_state()
    result = await replace_character_images(
        page,  # type: ignore[arg-type]
        project_id=PROJECT,
        entity_id=ENTITY,
        images={"portrait": PNG_BYTES, "full_body": JPEG_BYTES},
        before=before,
        checkpoint=AsyncMock(side_effect=lambda slot, binding: checkpoints.append((slot, binding))),
    )

    assert page.clicked_slots == [0, 1]
    assert len(page.navigations) == 2
    assert [call.args[3] for call in clear.await_args_list] == ["portrait", "full_body"]
    assert [call.args[3] for call in upload.await_args_list] == [PNG_BYTES, JPEG_BYTES]
    assert [slot for slot, _binding in checkpoints] == ["portrait", "full_body"]
    assert result["images"] == {
        "portrait": {"workflow_id": OTHER_WORKFLOW, "media_id": OTHER_MEDIA},
        "full_body": {"workflow_id": BODY_WORKFLOW, "media_id": OTHER_MEDIA},
    }
    assert read.await_count == 3  # initial state plus a fresh post-save read per slot


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["clear", "upload"])
async def test_driver_fails_missing_ack_without_retrying_mutation(
    monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    page, _read, clear, upload, _checkpoints = _prepare_driver_mocks(monkeypatch)
    if failure == "clear":
        clear.side_effect = WireFormatError("clear acknowledgement missing")
    else:
        upload.side_effect = WireFormatError("upload acknowledgement missing")

    with pytest.raises(WireFormatError, match="acknowledgement missing"):
        await replace_character_images(
            page,  # type: ignore[arg-type]
            project_id=PROJECT,
            entity_id=ENTITY,
            images={"portrait": PNG_BYTES},
            before=_native_state(),
            checkpoint=AsyncMock(),
        )

    assert len(page.navigations) == 1
    assert clear.await_count == 1
    assert upload.await_count == (0 if failure == "clear" else 1)


@pytest.mark.asyncio
async def test_driver_refuses_metadata_drift_after_upload_without_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page, read, clear, upload, _checkpoints = _prepare_driver_mocks(monkeypatch)
    before = _native_state()
    changed = _native_state()
    changed["images"]["portrait"] = {"workflow_id": OTHER_WORKFLOW, "media_id": OTHER_MEDIA}
    changed["metadata_sha256"] = "f" * 64
    read.side_effect = [before, changed]

    with pytest.raises(WireFormatError, match="metadata did not persist"):
        await replace_character_images(
            page,  # type: ignore[arg-type]
            project_id=PROJECT,
            entity_id=ENTITY,
            images={"portrait": PNG_BYTES},
            before=before,
            checkpoint=AsyncMock(),
        )

    assert clear.await_count == 1
    assert upload.await_count == 1
    assert read.await_count == 2
    assert len(page.navigations) == 1


class _ClearPage:
    def __init__(self) -> None:
        self.frame = SimpleNamespace(hover=AsyncMock())
        self.confirm = SimpleNamespace(
            wait_for=AsyncMock(),
            count=AsyncMock(return_value=1),
            click=AsyncMock(),
        )
        self.dialog = SimpleNamespace(
            wait_for=AsyncMock(),
            locator=Mock(return_value=self.confirm),
        )
        self.upload = SimpleNamespace(wait_for=AsyncMock())

    def locator(self, selector: str) -> Any:
        if selector.endswith(".image-frame"):
            return self.frame
        if selector == "mat-dialog-container":
            return self.dialog
        return self.upload


def _prepare_clear_mocks(
    monkeypatch: pytest.MonkeyPatch,
    reads: list[dict[str, Any]],
) -> tuple[_ClearPage, AsyncMock, AsyncMock, AsyncMock]:
    page = _ClearPage()
    read = AsyncMock(side_effect=reads)
    clear_control = SimpleNamespace(click=AsyncMock())
    open_slot = AsyncMock()
    monkeypatch.setattr(native_character_update, "read_character_image_state", read)
    monkeypatch.setattr(native_character_update, "_open_slot", open_slot)
    monkeypatch.setattr(
        native_character_update,
        "unique_character_control",
        AsyncMock(return_value=clear_control),
    )
    return page, read, clear_control.click, open_slot


@pytest.mark.asyncio
async def test_clear_slot_succeeds_only_after_exact_empty_slot_readback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    before = _native_state()
    expected = copy.deepcopy(before)
    expected["images"]["portrait"] = None
    page, read, clear_click, open_slot = _prepare_clear_mocks(monkeypatch, [expected])

    await native_character_update._clear_slot(page, PROJECT, ENTITY, "portrait", before)  # type: ignore[arg-type]

    page.frame.hover.assert_awaited_once()
    page.dialog.wait_for.assert_awaited_once()
    page.confirm.count.assert_awaited_once()
    page.confirm.click.assert_awaited_once()
    page.upload.wait_for.assert_awaited_once()
    clear_click.assert_awaited_once()
    assert read.await_count == 1
    open_slot.assert_awaited_once_with(page, PROJECT, ENTITY, "portrait")


@pytest.mark.asyncio
async def test_clear_slot_reconciles_old_snapshot_then_exact_empty_without_second_click(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    before = _native_state()
    expected = copy.deepcopy(before)
    expected["images"]["full_body"] = None
    page, read, clear_click, open_slot = _prepare_clear_mocks(monkeypatch, [before, expected])
    sleep = AsyncMock()
    monkeypatch.setattr(native_character_update.asyncio, "sleep", sleep)

    await native_character_update._clear_slot(page, PROJECT, ENTITY, "full_body", before)  # type: ignore[arg-type]

    clear_click.assert_awaited_once()
    page.confirm.click.assert_awaited_once()
    assert read.await_count == 2
    sleep.assert_awaited_once_with(1)
    open_slot.assert_awaited_once_with(page, PROJECT, ENTITY, "full_body")


@pytest.mark.asyncio
@pytest.mark.parametrize("drift", ["other_slot", "metadata"])
async def test_clear_slot_refuses_other_slot_or_metadata_drift_without_reopen(
    monkeypatch: pytest.MonkeyPatch, drift: str
) -> None:
    before = _native_state()
    expected = copy.deepcopy(before)
    expected["images"]["portrait"] = None
    changed = copy.deepcopy(expected)
    if drift == "other_slot":
        changed["images"]["full_body"]["media_id"] = OTHER_MEDIA
    else:
        changed["metadata_sha256"] = "f" * 64
    page, read, clear_click, open_slot = _prepare_clear_mocks(monkeypatch, [changed])

    with pytest.raises(WireFormatError, match="slot clear did not persist exactly"):
        await native_character_update._clear_slot(page, PROJECT, ENTITY, "portrait", before)  # type: ignore[arg-type]

    clear_click.assert_awaited_once()
    page.confirm.click.assert_awaited_once()
    assert read.await_count == 1
    open_slot.assert_not_awaited()


@pytest.mark.asyncio
async def test_clear_slot_waits_for_hydrated_confirmation_before_counting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    before = _native_state()
    expected = copy.deepcopy(before)
    expected["images"]["full_body"] = None
    page, read, clear_click, open_slot = _prepare_clear_mocks(monkeypatch, [expected])
    hydrated = False

    async def hydrate_confirmation(**kwargs: Any) -> None:
        nonlocal hydrated
        assert kwargs == {"timeout": 5_000}
        hydrated = True

    async def confirmation_count() -> int:
        return 1 if hydrated else 0

    page.confirm.wait_for.side_effect = hydrate_confirmation
    page.confirm.count.side_effect = confirmation_count

    await native_character_update._clear_slot(
        page,
        PROJECT,
        ENTITY,
        "full_body",
        before,  # type: ignore[arg-type]
    )

    page.confirm.wait_for.assert_awaited_once_with(timeout=5_000)
    page.confirm.count.assert_awaited_once()
    page.confirm.click.assert_awaited_once()
    assert read.await_count == 1
    clear_click.assert_awaited_once()
    open_slot.assert_awaited_once_with(page, PROJECT, ENTITY, "full_body")


@pytest.mark.asyncio
async def test_clear_slot_refuses_unchanged_state_after_three_reads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    before = _native_state()
    page, read, clear_click, open_slot = _prepare_clear_mocks(
        monkeypatch, [copy.deepcopy(before) for _ in range(3)]
    )
    sleep = AsyncMock()
    monkeypatch.setattr(native_character_update.asyncio, "sleep", sleep)

    with pytest.raises(WireFormatError, match="slot clear did not persist exactly"):
        await native_character_update._clear_slot(page, PROJECT, ENTITY, "portrait", before)  # type: ignore[arg-type]

    clear_click.assert_awaited_once()
    page.confirm.click.assert_awaited_once()
    assert read.await_count == 3
    assert sleep.await_count == 2
    open_slot.assert_not_awaited()
