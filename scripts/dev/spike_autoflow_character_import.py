"""Inspect native Character affordances; optional original-sheet upload, never Generate.

Pre-registered readings:
* A rendered native upload/menu affordance is a lead, not proof of import binding.
* An empty/missing selector does not prove the feature absent.
* Auth, lease or navigation failure is an external boundary; no relogin/retry.

Metadata only: no screenshot, labels, prompts, cookies, URLs or response bodies.
Use --project and the already configured --profile. Never click Generate.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _spike_common import build_client, resolve_profile_dir  # noqa: E402

from gflow_cli.api.client import validate_image_file  # noqa: E402
from gflow_cli.api.transports.batchexecute import parse_frames  # noqa: E402
from gflow_cli.api.transports.migrated_composer import TOOLBAR_ADD  # noqa: E402

INVENTORY_JS = """() => {
  const icons = [...document.querySelectorAll('mat-icon')]
    .map(e => (e.textContent || '').trim()).filter(t => /^[a-z0-9_]{2,40}$/.test(t));
  const counts = {};
  for (const icon of icons) counts[icon] = (counts[icon] || 0) + 1;
  return {icons: counts, textboxes: document.querySelectorAll(
    'textarea, [contenteditable=true], input.name-input').length,
    file_inputs: document.querySelectorAll('input[type=file]').length,
    inputs: [...document.querySelectorAll('input,textarea')].map(e => ({tag:e.tagName,
      type:e.getAttribute('type'), control:e.getAttribute('formcontrolname')})),
    custom_elements: [...new Set([...document.querySelectorAll('*')]
      .map(e => e.tagName.toLowerCase()).filter(t => /^(flow|mat)-[a-z-]+$/.test(t)))],
    character_tiles: document.querySelectorAll('flow-character-tile').length,
    menu_items: document.querySelectorAll('[role=menuitem]').length,
    personality_fields: document.querySelectorAll('textarea.personality-textarea').length};
}"""

FORM_STRUCTURE_JS = """() => ({
  fields: [...document.querySelectorAll('flow-character-form input, flow-character-form textarea')]
    .map(e => ({tag:e.tagName, classes:e.className, value_length:e.value.length})),
  footer_buttons: [...document.querySelectorAll('flow-edit-character-footer button')]
    .map(e => ({classes:e.className, disabled:e.disabled, type:e.type,
      icons:[...e.querySelectorAll('mat-icon')].map(i=>i.textContent.trim())})),
  form_buttons: [...document.querySelectorAll(
    'flow-character-form button, ' + 'flow-character-edit-header button')]
    .map(e => ({classes:e.className, disabled:e.disabled, type:e.type,
      icons:[...e.querySelectorAll('mat-icon')].map(i=>i.textContent.trim())})),
  image_ids:[...document.querySelectorAll('flow-character-image-preview img')]
    .map(e => {const m = (e.src || '').match(/([0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})/i);
      return m ? m[1] : null;})
})"""


async def inspect(
    profile: str,
    project: str,
    *,
    open_character: bool = False,
    sheet: Path | None = None,
    entity: str | None = None,
    name: str | None = None,
    personality: str | None = None,
    visible: bool = False,
) -> None:
    if sheet is not None:
        await validate_image_file(sheet)
    findings: dict[str, object] = {
        "operation": "character_metadata_update"
        if personality
        else "character_upload"
        if sheet
        else "inspect_only",
        "generation_submitted": False,
    }
    metadata_ack = asyncio.Event()
    upload_ack = asyncio.Event()
    rpcids: set[str] = set()
    wire_shapes: list[dict[str, object]] = []
    async with build_client(resolve_profile_dir(profile), headless=not visible) as client:
        page = await client._context.new_page()  # noqa: SLF001 - owned spike context

        def on_request(request: object) -> None:
            url = urlsplit(str(getattr(request, "url", "")))
            if "batchexecute" in url.path:
                for value in parse_qs(url.query).get("rpcids", []):
                    rpcids.update(v for v in value.split(",") if v.isalnum())
                raw = str(getattr(request, "post_data", "") or "")
                if personality:
                    decoded = parse_qs(raw).get("f.req", [""])[0]
                    findings.setdefault("metadata_requests", []).append(
                        {
                            "rpcids": parse_qs(url.query).get("rpcids", []),
                            "contains_personality": personality in decoded
                            or json.dumps(personality)[1:-1] in decoded,
                        }
                    )

        page.on("request", on_request)

        def safe_shape(value: object, depth: int = 0) -> object:
            if depth > 8:
                return "<nested>"
            if isinstance(value, list):
                return [safe_shape(v, depth + 1) for v in value[:60]]
            if isinstance(value, str):
                return (
                    value
                    if re.fullmatch(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", value)
                    else "<text>"
                )
            return value if value is None or type(value) in (bool, int, float) else "<object>"

        def matching_records(value: object, path: tuple[int, ...] = ()) -> list[dict[str, object]]:
            if not isinstance(value, list):
                return []
            if entity is not None and entity in value:
                return [{"path": list(path), "shape": safe_shape(value)}]
            return [
                record
                for i, child in enumerate(value)
                for record in matching_records(child, (*path, i))
            ]

        async def on_response(response: object) -> None:
            if "batchexecute" not in str(getattr(response, "url", "")):
                return
            expected_upload = "maseQ" in parse_qs(urlsplit(response.url).query).get("rpcids", [])
            body = await response.text()
            frames = parse_frames(body)
            if expected_upload:
                findings["upload_response"] = {"status": response.status, "bytes": len(body),
                                               "frame_count": len(frames)}
                upload_ack.set()
            for rid, payload in frames:
                if rid == "maseQ":
                    findings["upload_shape"] = safe_shape(payload)
                if rid == "rzMKMb" and personality and isinstance(payload, list):
                    for row in payload:
                        if (
                            isinstance(row, list)
                            and len(row) > 3
                            and row[1] == entity
                            and isinstance(row[3], list)
                            and len(row[3]) > 2
                            and isinstance(row[3][2], list)
                            and len(row[3][2]) > 2
                            and row[3][2][2] == personality
                        ):
                            metadata_ack.set()
                if (
                    rid == "Zzl0ze"
                    and isinstance(payload, list)
                    and len(payload) > 5
                    and isinstance(payload[5], list)
                ):
                    findings["native_entities"] = [
                        {
                            "shape": safe_shape(row),
                            "is_goofy": isinstance(row, list)
                            and len(row) > 3
                            and isinstance(row[3], list)
                            and len(row[3]) > 1
                            and row[3][1] == "Goofy",
                        }
                        for row in payload[5][:20]
                    ]
                records = matching_records(payload)
                if records and len(wire_shapes) < 8:
                    wire_shapes.append({"rpcid": rid, "records": records[:4]})

        page.on("response", on_response)
        try:
            target = f"https://flow.google.com/project/{project}"
            if entity is not None:
                target += f"/character/{entity}"
            await page.goto(target, wait_until="domcontentloaded", timeout=45000)
            await page.locator(
                "flow-character-edit-page" if entity else "flow-prompt-box"
            ).wait_for(timeout=20000)
            if entity:
                await page.wait_for_function(
                    "() => (document.querySelector('input.name-input')?.value || '').length > 0",
                    timeout=15000,
                )
            findings["host"] = urlsplit(page.url).hostname
            findings["before"] = await page.evaluate(INVENTORY_JS)
            if entity:
                findings["form_structure"] = await page.evaluate(FORM_STRUCTURE_JS)
                if sheet is not None:
                    upload = page.locator(
                        'flow-character-edit-page button:has(mat-icon:text-is("upload"))'
                    )
                    findings["recovery_upload_matches"] = await upload.count()
                    if await upload.count() != 1:
                        raise RuntimeError("ambiguous recovery upload control")
                    async with page.expect_file_chooser(timeout=8000) as chooser:
                        await upload.click(timeout=5000)
                    await (await chooser.value).set_files(sheet)
                    await page.wait_for_timeout(3000)
                    findings["after_recovery_upload"] = await page.evaluate(FORM_STRUCTURE_JS)
                if name is not None and personality is not None:
                    await page.locator("flow-character-form input.name-input").fill(name)
                    await page.locator("textarea.personality-textarea").fill(personality)
                    await page.locator("textarea.personality-textarea").press("Tab")
                    try:
                        await asyncio.wait_for(metadata_ack.wait(), timeout=10)
                        findings["metadata_ack_verified"] = True
                    except TimeoutError:
                        findings["metadata_ack_verified"] = False
                    done = page.locator("flow-character-edit-header button.flow-button-secondary")
                    if await done.count() != 1:
                        raise RuntimeError("ambiguous native character save control")
                    await done.click(timeout=5000)
                    await page.locator("flow-prompt-box").wait_for(timeout=15000)
                    await page.wait_for_timeout(3000)
                    await page.goto(target, wait_until="domcontentloaded", timeout=45000)
                    await page.locator("flow-character-edit-page").wait_for(timeout=15000)
                    await page.wait_for_function(
                        "() => (document.querySelector('input.name-input')?.value || '')"
                        ".length > 0",
                        timeout=15000,
                    )
                    await page.reload(wait_until="domcontentloaded", timeout=45000)
                    await page.wait_for_function(
                        "() => (document.querySelector('input.name-input')?.value || '')"
                        ".length > 0",
                        timeout=15000,
                    )
                    findings["name_readback"] = (
                        await page.locator("input.name-input").input_value() == name
                    )
                    findings["personality_readback"] = (
                        await page.locator("textarea.personality-textarea").input_value()
                        == personality
                    )
                    findings["saved_form"] = await page.evaluate(FORM_STRUCTURE_JS)
            add = page.locator(TOOLBAR_ADD)
            findings["toolbar_matches"] = await add.count()
            if entity is None and await add.count() == 1:
                await add.click(timeout=5000)
                await page.locator('[role="menuitem"]').first.wait_for(timeout=5000)
                findings["menu"] = await page.evaluate(INVENTORY_JS)
                if open_character:
                    character = page.locator(
                        '[role="menuitem"]:has(mat-icon:text-is("account_circle"))'
                    )
                    findings["character_menu_matches"] = await character.count()
                    if await character.count() == 1:
                        await character.click(timeout=5000)
                        await page.locator("flow-character-page").wait_for(timeout=10000)
                        findings["character_editor"] = await page.evaluate(INVENTORY_JS)
                        if sheet is not None:
                            upload = page.locator(
                                'flow-character-page button:has(mat-icon:text-is("upload"))'
                            )
                            findings["character_upload_matches"] = await upload.count()
                            if await upload.count() == 1:
                                async with page.expect_file_chooser(timeout=8000) as chooser:
                                    await upload.click(timeout=5000)
                                await (await chooser.value).set_files(sheet)
                                await asyncio.wait_for(upload_ack.wait(), timeout=45)
                                await page.locator("flow-character-edit-page").wait_for(
                                    timeout=45_000
                                )
                                await page.wait_for_function(
                                    "() => (document.querySelector('input.name-input')?.value || '')"  # noqa: E501
                                    ".length > 0",
                                    timeout=15_000,
                                )
                                findings["after_upload"] = await page.evaluate(INVENTORY_JS)
                                if name is not None:
                                    await page.locator("flow-character-form input.name-input").fill(
                                        name
                                    )
                                    await page.locator(
                                        "flow-character-form input.name-input"
                                    ).press("Tab")
                        route = urlsplit(page.url).path.split("/")
                        if "character" in route:
                            findings["entity_id"] = route[route.index("character") + 1]
                else:
                    await page.keyboard.press("Escape")
            findings["rpcids"] = sorted(rpcids)
            await page.wait_for_timeout(1500)
            findings["wire_shapes"] = wire_shapes
        except Exception as exc:
            findings["failure_class"] = type(exc).__name__
            findings["after_failure"] = await page.evaluate(INVENTORY_JS)
            route = urlsplit(page.url).path.split("/")
            if "character" in route and len(route) > route.index("character") + 1:
                findings["entity_id"] = route[route.index("character") + 1]
        finally:
            await page.close()
    print(json.dumps(findings, sort_keys=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--project", required=True)
    parser.add_argument(
        "--open-character",
        action="store_true",
        help="Enter native Character creation; may create an empty entity, never media.",
    )
    parser.add_argument(
        "--sheet",
        type=Path,
        help="Upload an original sheet through the native upload control; never Generate.",
    )
    parser.add_argument(
        "--entity", help="Read back an existing native Character; no creation/upload."
    )
    parser.add_argument("--name")
    parser.add_argument("--personality")
    parser.add_argument(
        "--visible",
        action="store_true",
        help="Opt in to a visible inspection browser; default is headless.",
    )
    args = parser.parse_args()
    if args.sheet is not None and not (args.open_character or args.entity):
        parser.error("--sheet requires --open-character or --entity")
    asyncio.run(
        inspect(
            args.profile,
            args.project,
            open_character=args.open_character,
            sheet=args.sheet,
            entity=args.entity,
            name=args.name,
            personality=args.personality,
            visible=args.visible,
        )
    )
