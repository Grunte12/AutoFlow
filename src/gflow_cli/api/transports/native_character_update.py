"""Replace existing native Character slots without creating or generating media.

Observed Flow UI maps portrait to reference index 0 and body to index 1.
Its preview delete gesture invokes clear_character_reference_slot (not media
deletion). Every mutation is single-shot; only fresh readbacks may be retried.
"""

from __future__ import annotations

import asyncio
import copy
import hashlib
import json
from typing import TYPE_CHECKING, Any, cast
from urllib.parse import urlsplit

from gflow_cli.api.transports.batchexecute import parse_frames
from gflow_cli.api.transports.migrated_composer import FRAME_UPLOAD_S
from gflow_cli.api.transports.native_character_import import (
    CHARACTER_DONE,
    CHARACTER_HYDRATED,
    canonical_character_uuid,
    character_route_entity,
    parse_character_upload_binding,
    unique_character_control,
)
from gflow_cli.api.transports.native_character_ui import read_native_project_payload
from gflow_cli.errors import ConfigurationError, WireFormatError

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from playwright.async_api import Page, Response

_SLOTS = {"portrait": 0, "full_body": 1}
_PREVIEW = "flow-character-image-preview"
_UPLOAD = f'{_PREVIEW} button:has(mat-icon:text-is("upload"))'
_CLEAR = f'{_PREVIEW} button:has(mat-icon:text-is("delete"))'
_REMEDIATION = "Inspect the Character and operation journal; do not repeat an uncertain update."


def _invalid() -> WireFormatError:
    return WireFormatError(
        "Native Character image state is missing, ambiguous or foreign-owned",
        route="native:characterUpdate",
        remediation_hint=_REMEDIATION,
    )


def _metadata_hash(info: list[Any]) -> str:
    stable = copy.deepcopy(info)
    stable[2][0] = []
    return hashlib.sha256(
        json.dumps(stable, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _wire_list(value: object) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError("Expected a native array")
    return cast("list[Any]", value)


def parse_character_image_state(payload: object, project_id: str, entity_id: str) -> dict[str, Any]:
    """Admit only exact entity/slot/workflow/media relationships; omit URLs."""
    try:
        canonical_character_uuid(project_id)
        canonical_character_uuid(entity_id)
        rows = _wire_list(payload)
        if len(rows) < 6:
            raise ValueError
        entities = [_wire_list(r) for r in _wire_list(rows[5])]
        matches = [r for r in entities if len(r) > 1 and r[1] == entity_id]
        if len(matches) != 1:
            raise ValueError
        entity = matches[0]
        if len(entity) < 4 or entity[0] != project_id:
            raise ValueError
        info = _wire_list(entity[3])
        if len(info) < 3 or info[0] != 1 or not isinstance(info[1], str) or not info[1]:
            raise ValueError
        character_info = _wire_list(info[2])
        references = _wire_list(character_info[0])
        if len(references) > 2:
            raise ValueError
        images: dict[str, Any] = {}
        used: set[str] = set()
        for slot, index in _SLOTS.items():
            reference = references[index] if index < len(references) else None
            if reference is None or reference == []:
                images[slot] = None
                continue
            reference = _wire_list(reference)
            if len(reference) != 1:
                raise ValueError
            workflow_id = canonical_character_uuid(reference[0])
            if workflow_id in used:
                raise ValueError
            used.add(workflow_id)
            all_workflows = [_wire_list(r) for r in _wire_list(rows[1])]
            workflows = [r for r in all_workflows if r and r[0] == workflow_id]
            if len(workflows) != 1:
                raise ValueError
            workflow = workflows[0]
            if len(workflow) < 6 or workflow[4:6] != [project_id, entity_id]:
                raise ValueError
            workflow_metadata = _wire_list(workflow[3])
            media_id = canonical_character_uuid(workflow_metadata[4])
            if len({project_id, entity_id, workflow_id, media_id}) != 4:
                raise ValueError
            images[slot] = {"workflow_id": workflow_id, "media_id": media_id}
        return {
            "project": project_id,
            "entity_id": entity_id,
            "metadata_sha256": _metadata_hash(info),
            "images": images,
        }
    except (ValueError, TypeError, IndexError, KeyError) as exc:
        raise _invalid() from exc


async def read_character_image_state(page: Page, project_id: str, entity_id: str) -> dict[str, Any]:
    payload = await read_native_project_payload(page, project_id, timeout_s=30)
    return parse_character_image_state(payload, project_id, entity_id)


def _flow_response(response: Response) -> bool:
    url = urlsplit(response.url)
    return (
        url.scheme == "https"
        and url.hostname == "flow.google.com"
        and url.path.endswith("/data/batchexecute")
        and response.status == 200
    )


async def _open_slot(page: Page, project_id: str, entity_id: str, slot: str) -> None:
    await page.goto(
        f"https://flow.google.com/project/{project_id}/character/{entity_id}",
        wait_until="domcontentloaded",
        timeout=45_000,
    )
    await page.wait_for_function(CHARACTER_HYDRATED, timeout=20_000)
    if character_route_entity(page.url, project_id) != entity_id:
        raise _invalid()
    slots = page.locator("flow-slot-chip-button button")
    if await slots.count() != 2:
        raise ConfigurationError("Character slot controls are missing or ambiguous")
    await slots.nth(_SLOTS[slot]).click(timeout=5_000)


async def _clear_slot(
    page: Page, project_id: str, entity_id: str, slot: str, before: dict[str, Any]
) -> None:
    await page.locator(f"{_PREVIEW} .image-frame").hover(timeout=5_000)
    await (await unique_character_control(page, _CLEAR, "clear reference")).click(timeout=5_000)
    dialog = page.locator("mat-dialog-container")
    await dialog.wait_for(timeout=5_000)
    confirm = dialog.locator("button.flow-button-primary")
    await confirm.wait_for(timeout=5_000)
    if await confirm.count() != 1:
        raise ConfigurationError("Character reference-clear confirmation is ambiguous")
    await confirm.click(timeout=5_000)
    await page.locator(_UPLOAD).wait_for(timeout=15_000)
    # Clear uses a dedicated RPC, not the metadata-save RPC. Its optimistic
    # empty preview is insufficient: fresh project readback must prove that
    # exactly this slot was detached before any upload is permitted.
    expected = copy.deepcopy(before)
    expected["images"][slot] = None
    for attempt in range(3):
        current = await read_character_image_state(page, project_id, entity_id)
        if current == expected:
            await _open_slot(page, project_id, entity_id, slot)
            return
        if current != before or attempt == 2:
            raise WireFormatError(
                "Character slot clear did not persist exactly", remediation_hint=_REMEDIATION
            )
        await asyncio.sleep(1)


async def _upload_slot(
    page: Page, project_id: str, entity_id: str, source: bytes
) -> dict[str, str]:
    uploaded: asyncio.Future[tuple[str, str, str]] = asyncio.get_running_loop().create_future()

    async def on_upload(response: Response) -> None:
        if uploaded.done() or not _flow_response(response):
            return
        try:
            frames = parse_frames(await response.text())
        except Exception:  # noqa: BLE001 - background traffic is not upload proof
            return
        for rpc, payload in frames:
            if rpc != "maseQ" or uploaded.done():
                continue
            try:
                binding = parse_character_upload_binding(payload, project_id)
                if binding[2] != entity_id:
                    raise _invalid()
            except WireFormatError as exc:
                uploaded.set_exception(exc)
            else:
                uploaded.set_result(binding)

    page.on("response", on_upload)
    try:
        async with page.expect_file_chooser(timeout=8_000) as choice:
            await (await unique_character_control(page, _UPLOAD, "upload")).click(timeout=5_000)
        chooser = await choice.value
        # The frozen validated bytes, not a mutable path, are sent to Flow.
        if source.startswith(b"\x89PNG"):
            mime, extension = "image/png", "png"
        elif source.startswith(b"\xff\xd8\xff"):
            mime, extension = "image/jpeg", "jpg"
        elif source.startswith(b"RIFF"):
            mime, extension = "image/webp", "webp"
        else:
            mime, extension = "image/gif", "gif"
        await chooser.set_files(
            {"name": f"character.{extension}", "mimeType": mime, "buffer": source}
        )
        media_id, workflow_id, _ = await asyncio.wait_for(uploaded, timeout=FRAME_UPLOAD_S)
        return {"workflow_id": workflow_id, "media_id": media_id}
    except TimeoutError as exc:
        raise WireFormatError(
            "Character upload acknowledgement did not arrive", remediation_hint=_REMEDIATION
        ) from exc
    finally:
        page.remove_listener("response", on_upload)
        if not uploaded.done():
            uploaded.cancel()


async def replace_character_images(
    page: Page,
    *,
    project_id: str,
    entity_id: str,
    images: dict[str, bytes],
    before: dict[str, Any],
    checkpoint: Callable[[str, dict[str, str]], Awaitable[None]],
) -> dict[str, Any]:
    from gflow_cli.api.client import validate_image_bytes  # noqa: PLC0415

    canonical_character_uuid(project_id)
    canonical_character_uuid(entity_id)
    if not images or not set(images) <= _SLOTS.keys():
        raise ValueError("Supply portrait and/or full_body bytes")
    for source in images.values():
        validate_image_bytes(source)
    current = await read_character_image_state(page, project_id, entity_id)
    if current != before:
        raise ConfigurationError("Character changed before image replacement; no images uploaded")
    expected = copy.deepcopy(before)
    for slot, source in images.items():
        await _open_slot(page, project_id, entity_id, slot)
        if expected["images"][slot] is not None:
            await _clear_slot(page, project_id, entity_id, slot, expected)
        binding = await _upload_slot(page, project_id, entity_id, source)
        await checkpoint(slot, binding)
        expected["images"][slot] = binding
        await page.locator("flow-character-edit-page flow-pending-tile").wait_for(
            state="detached", timeout=45_000
        )
        await (await unique_character_control(page, CHARACTER_DONE, "save")).click(timeout=5_000)
        await page.locator("flow-prompt-box").wait_for(timeout=20_000)
        for attempt in range(3):
            current = await read_character_image_state(page, project_id, entity_id)
            if current == expected:
                break
            if current["metadata_sha256"] != expected["metadata_sha256"] or attempt == 2:
                raise WireFormatError(
                    "Character slot or metadata did not persist exactly",
                    remediation_hint=_REMEDIATION,
                )
            await asyncio.sleep(1)
    return current
