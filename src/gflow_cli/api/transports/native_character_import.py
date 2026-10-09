"""Import an original Character sheet through Flow's native, non-generating form.

The caller persists intent before invoking this mutation and checkpoints the
entity ID through ``on_entity_created``. An interrupted upload is not retried by
this driver. Success requires fresh project bindings and metadata readback.
"""

from __future__ import annotations

import asyncio
import hashlib
import mimetypes
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, cast
from urllib.parse import urlsplit
from uuid import UUID

from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from gflow_cli.api.transports.batchexecute import parse_frames
from gflow_cli.api.transports.migrated_composer import FRAME_UPLOAD_S, TOOLBAR_ADD
from gflow_cli.api.transports.native_character import NativeCharacterReadback
from gflow_cli.api.transports.native_character_ui import (
    read_native_characters,
    read_verified_native_character,
)
from gflow_cli.errors import ConfigurationError, UiSelectorDriftError, WireFormatError

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from pathlib import Path

    from playwright.async_api import Locator, Page, Response

_FORM = "flow-character-form"
_NAME = f"{_FORM} input.name-input"
_PERSONALITY = f"{_FORM} textarea.personality-textarea"
_DONE = "flow-character-edit-header button.flow-button-secondary"
_HYDRATED = "() => (document.querySelector('input.name-input')?.value || '').length > 0"
_UNCERTAIN = (
    "Inspect the native Character and operation journal before retrying. "
    "Do not repeat an import whose image binding is uncertain."
)


@dataclass(frozen=True)
class NativeCharacterImportResult:
    readback: NativeCharacterReadback
    source_sha256: str


def _uuid(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("Character route identifiers must be canonical UUIDs")
    try:
        canonical = str(UUID(value))
    except (ValueError, AttributeError, TypeError) as exc:
        raise ValueError("Character route identifiers must be canonical UUIDs") from exc
    if value != canonical:
        raise ValueError("Character route identifiers must be canonical UUIDs")
    return canonical


async def _unique(page: Page, selector: str, control: str) -> Locator:
    locator = page.locator(selector)
    if await locator.count() != 1:
        raise UiSelectorDriftError(
            f"native Character {control} control is missing or ambiguous",
            route="native:characterImport",
            remediation_hint=(
                "Inspect the native Character form; do not repeat an uncertain import."
            ),
        )
    return locator


def _route_entity(url: str, project_id: str) -> str:
    parsed = urlsplit(url)
    parts = parsed.path.strip("/").split("/")
    if (
        parsed.scheme != "https"
        or parsed.hostname != "flow.google.com"
        or len(parts) != 4
        or parts[:3] != ["project", project_id, "character"]
    ):
        raise WireFormatError(
            "native Character import did not remain on the expected entity route",
            route="native:characterImport",
            remediation_hint=_UNCERTAIN,
        )
    return _uuid(parts[3])


def _parse_upload_reply(payload: object, project_id: str) -> tuple[str, str, str]:
    """Observed native maseQ reply: one media row and its parent-bound workflow.

    Validate the relationships, not the first UUID anywhere in the payload.
    Do not retain signed image URLs or response bodies.
    """
    try:
        if not isinstance(payload, list):
            raise ValueError
        rows = cast("list[object]", payload)
        if len(rows) != 2:
            raise ValueError
        if not isinstance(rows[0], list) or not isinstance(rows[1], list):
            raise ValueError
        media = cast("list[object]", rows[0])
        workflow = cast("list[object]", rows[1])
        if len(media) < 3 or len(workflow) < 6:
            raise ValueError
        media_id, media_project, workflow_id = media[:3]
        metadata = workflow[3]
        if (
            media_project != project_id
            or workflow[4] != project_id
            or workflow[0] != workflow_id
            or not isinstance(metadata, list)
            or len(cast("list[object]", metadata)) < 5
            or cast("list[object]", metadata)[4] != media_id
        ):
            raise ValueError
        result = (_uuid(media_id), _uuid(workflow_id), _uuid(workflow[5]))
        if len(set((*result, project_id))) != 4:
            raise ValueError
        return result
    except (ValueError, TypeError, AttributeError) as exc:
        raise WireFormatError(
            "Native Character upload returned no exact media/workflow/entity binding",
            route="native:characterImport",
            remediation_hint=_UNCERTAIN,
        ) from exc


async def import_native_character(
    page: Page,
    *,
    project_id: str,
    name: str,
    sheet: Path,
    personality: str | None = None,
    on_entity_created: Callable[[str], Awaitable[None]] | None = None,
) -> NativeCharacterImportResult:
    """Upload original bytes, save metadata, and verify; never press Generate.

    Replay/reconciliation belongs to the service journal, not a second upload.
    No automatic recreation or rollback deletion occurs on any exception.
    """
    from gflow_cli.api.client import (  # noqa: PLC0415
        validate_image_bytes,
        validate_image_file,
    )

    project_id = _uuid(project_id)
    if not name.strip() or name != name.strip():
        raise ValueError("Character name must be nonempty without surrounding whitespace")
    if on_entity_created is None:
        raise ValueError("Creating a Character requires an entity checkpoint callback")
    await validate_image_file(sheet)
    source = await asyncio.to_thread(sheet.read_bytes)
    validate_image_bytes(source)
    source_hash = hashlib.sha256(source).hexdigest()
    existing = await read_native_characters(page, project_id)
    if any(item.character.display_name == name for item in existing):
        raise ConfigurationError(
            "A Character with this name already exists; inspect it and the operation journal.",
            route="native:characterImport",
            remediation_hint=_UNCERTAIN,
        )
    await (await _unique(page, TOOLBAR_ADD, "add")).click(timeout=5_000)
    menu = await _unique(
        page, '[role="menuitem"]:has(mat-icon:text-is("account_circle"))', "create"
    )
    await menu.click(timeout=5_000)
    await page.locator("flow-character-page").wait_for(timeout=15_000)
    upload_selector = 'flow-character-page button:has(mat-icon:text-is("upload"))'

    uploaded: asyncio.Future[tuple[str, str, str]] = asyncio.get_running_loop().create_future()

    async def on_upload(response: Response) -> None:
        url = urlsplit(response.url)
        if (
            uploaded.done()
            or url.scheme != "https"
            or url.hostname != "flow.google.com"
            or not url.path.endswith("/data/batchexecute")
        ):
            return
        try:
            frames = parse_frames(await response.text())
            for rpc, payload in frames:
                if rpc == "maseQ" and not uploaded.done():
                    try:
                        if response.status != 200:
                            raise WireFormatError(
                                "Native Character upload did not return HTTP 200",
                                route="native:characterImport",
                                remediation_hint=_UNCERTAIN,
                            )
                        binding = _parse_upload_reply(payload, project_id)
                    except WireFormatError as exc:
                        uploaded.set_exception(exc)
                    else:
                        uploaded.set_result(binding)
        except Exception:  # noqa: BLE001 - unreadable background traffic is not upload proof
            return

    page.on("response", on_upload)
    try:
        upload = await _unique(page, upload_selector, "upload")
        async with page.expect_file_chooser(timeout=8_000) as choice:
            await upload.click(timeout=5_000)
        chooser = await choice.value
        await chooser.set_files(
            {
                "name": sheet.name,
                "mimeType": mimetypes.guess_type(sheet.name)[0] or "image/png",
                "buffer": source,
            }
        )
        media_id, workflow_id, entity_id = await asyncio.wait_for(uploaded, timeout=FRAME_UPLOAD_S)
        await on_entity_created(entity_id)
    except TimeoutError as exc:
        raise WireFormatError(
            "Native Character upload acknowledgement did not arrive in time",
            route="native:characterImport",
            remediation_hint=_UNCERTAIN,
        ) from exc
    finally:
        page.remove_listener("response", on_upload)
        if not uploaded.done():
            uploaded.cancel()
    await page.locator("flow-character-edit-page").wait_for(timeout=30_000)
    await page.wait_for_function(_HYDRATED, timeout=15_000)
    actual_entity = _route_entity(page.url, project_id)
    if actual_entity != entity_id:
        raise WireFormatError(
            "Character route does not match the upload's parent entity",
            route="native:characterImport",
            remediation_hint=_UNCERTAIN,
        )
    # The upload reply precedes image processing and its reference autosave.
    # Editing early races that autosave and can lose personality or image refs.
    await page.locator("flow-character-edit-page flow-pending-tile").wait_for(
        state="detached", timeout=45_000
    )
    saved = asyncio.Event()

    async def on_metadata(response: Response) -> None:
        url = urlsplit(response.url)
        if (
            url.scheme != "https"
            or url.hostname != "flow.google.com"
            or not url.path.endswith("/data/batchexecute")
        ):
            return
        try:
            for rpc, payload in parse_frames(await response.text()):
                if rpc != "rzMKMb" or response.status != 200 or not isinstance(payload, list):
                    continue
                for row in cast("list[object]", payload):
                    if not isinstance(row, list):
                        continue
                    values = cast("list[object]", row)
                    if len(values) < 4 or values[:2] != [project_id, entity_id]:
                        continue
                    info = values[3]
                    if not isinstance(info, list):
                        continue
                    fields = cast("list[object]", info)
                    if (
                        len(fields) < 3
                        or fields[0] != 1
                        or fields[1] != name
                        or not isinstance(fields[2], list)
                    ):
                        continue
                    character_info = cast("list[object]", fields[2])
                    # This acknowledges metadata, not the independently processed
                    # image reference. Exact image ownership is proved below by
                    # fresh project readback, never inferred from this response.
                    if personality is None or (
                        len(character_info) > 2 and character_info[2] == personality
                    ):
                        saved.set()
        except Exception:  # noqa: BLE001 - unreadable traffic is not saved metadata
            return

    page.on("response", on_metadata)
    try:
        field = await _unique(page, _NAME, "name")
        await field.fill(name)
        await field.press("Tab")
        if personality is not None:
            field = await _unique(page, _PERSONALITY, "personality")
            await field.fill(personality)
            await field.press("Tab")
        await asyncio.wait_for(saved.wait(), timeout=30)
    except TimeoutError as exc:
        raise WireFormatError(
            "Native Character metadata acknowledgement did not arrive in time",
            route="native:characterImport",
            remediation_hint=_UNCERTAIN,
        ) from exc
    finally:
        page.remove_listener("response", on_metadata)
    await (await _unique(page, _DONE, "save")).click(timeout=5_000)
    await page.locator("flow-prompt-box").wait_for(timeout=20_000)
    # Done may precede the image-reference autosave. Retry only these two
    # read-only transitional snapshots, never another upload or metadata write.
    readback: NativeCharacterReadback | None = None
    for attempt in range(3):
        try:
            readback = await read_verified_native_character(page, project_id, entity_id)
        except WireFormatError as exc:
            transitional = exc.detail in {
                "unexpected native character response: "
                "character has no workflow references to verify",
                "unexpected native character response: referenced workflow is missing",
            }
            if not transitional or attempt == 2:
                raise
        else:
            if readback.character.display_name == name:
                break
            if attempt == 2:
                raise WireFormatError(
                    "Character project metadata is stale",
                    route="native:characterImport",
                    remediation_hint=_UNCERTAIN,
                )
        await asyncio.sleep(1)
    if readback is None:
        raise WireFormatError(
            "Native Character image readback was not verified",
            route="native:characterImport",
            remediation_hint=_UNCERTAIN,
        )
    if readback.workflow_media_bindings != ((workflow_id, media_id),):
        raise WireFormatError(
            "The uploaded Character sheet is not bound to the requested entity",
            route="native:characterImport",
            remediation_hint=_UNCERTAIN,
        )
    target = f"https://flow.google.com/project/{project_id}/character/{entity_id}"
    await page.goto(target, wait_until="domcontentloaded", timeout=45_000)
    await page.wait_for_function(_HYDRATED, timeout=15_000)
    try:
        await page.wait_for_function(
            "expected => document.querySelector('input.name-input')?.value === expected.name "
            "&& (expected.personality === null || "
            "document.querySelector('textarea.personality-textarea')?.value "
            "=== expected.personality)",
            arg={"name": name, "personality": personality},
            timeout=15_000,
        )
    except PlaywrightTimeoutError as exc:
        raise WireFormatError(
            "Character metadata did not persist within the readback budget",
            route="native:characterImport",
            remediation_hint=_UNCERTAIN,
        ) from exc
    if await page.locator(_NAME).input_value() != name or (
        personality is not None and await page.locator(_PERSONALITY).input_value() != personality
    ):
        raise WireFormatError(
            "Character metadata did not persist",
            route="native:characterImport",
            remediation_hint=_UNCERTAIN,
        )
    if readback.character.display_name != name:
        raise WireFormatError(
            "Character project metadata is stale",
            route="native:characterImport",
            remediation_hint=_UNCERTAIN,
        )
    character = replace(readback.character, personality=personality)
    return NativeCharacterImportResult(replace(readback, character=character), source_hash)
