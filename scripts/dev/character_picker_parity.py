"""Credit-free comparison of native reference clicks and the production composer.

Requires an explicit JSON input and profile. It only mentions assets already in the
project. Uploads, Character edits, and generation submits are blocked. Equal wire
serialization proves the browser-client inputs match; it does not prove backend image use.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import sys
import traceback
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from gflow_cli import auth  # noqa: E402
from gflow_cli.api.client import FlowApiClient  # noqa: E402
from gflow_cli.api.transports.migrated_composer import (  # noqa: E402
    COMPOSER,
    MENTION_CHIP,
    PICKER_OPTION,
    SUBMIT_RPCS,
    MigratedComposer,
)
from gflow_cli.api.transports.native_character import parse_native_characters  # noqa: E402
from gflow_cli.api.transports.native_character_ui import read_native_project_payload  # noqa: E402
from gflow_cli.api.video import Aspect, GenerateVideoRequest, Mode, VideoModel  # noqa: E402
from gflow_cli.redaction import redact_sensitive_text  # noqa: E402

_MUTATION_NAMES = ("maseQ", "createEntity", "updateEntity", "clearCharacter", "deleteEntity")
_UUID = re.compile(r"^[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}$")
_STAGE = "startup"


def observe_request(req: Any, report: dict[str, Any]) -> None:
    """Count writes without UTF-8 decoding unrelated binary browser traffic."""
    url = str(req.url)
    body = (req.post_data_buffer or b"").decode("utf-8", errors="replace")
    if any(rpc in url or rpc in body for rpc in SUBMIT_RPCS) or "batchGenerate" in url:
        report["generation_dispatched"] += 1
    if any(name in url or name in body for name in _MUTATION_NAMES) or "upload" in url.lower():
        report["mutation_dispatched"] += 1


def spec_differences(left: Any, right: Any, path: tuple[int, ...] = ()) -> set[tuple[int, ...]]:
    """Retain every differing wire slot, including fields with unknown meaning."""
    if isinstance(left, list) and isinstance(right, list) and len(left) == len(right):
        return set().union(
            *(
                spec_differences(a, b, (*path, i))
                for i, (a, b) in enumerate(zip(left, right, strict=True))
            )
        )
    return set() if left == right else {path}


def compare_generation_specs(native: Any, production: Any, replay: Any) -> dict[str, Any]:
    """Allow only UUID variance positively measured by the repeated native control."""
    control = spec_differences(native, replay)
    changes = spec_differences(native, production)
    allowed = {(5, 4), (5, 5)}
    uuid_variance = control <= allowed and changes <= control
    if uuid_variance:
        for path in control | changes:
            for spec in (native, production, replay):
                value = spec[path[0]][path[1]]
                uuid_variance = (
                    uuid_variance and isinstance(value, str) and bool(_UUID.fullmatch(value))
                )
    return {
        "exact_native_production_equal": not changes,
        "native_replay_difference_paths": [list(p) for p in sorted(control)],
        "production_difference_paths": [list(p) for p in sorted(changes)],
        "all_nonvarying_fields_equal": uuid_variance,
        "unmapped_uuid_slots": [list(p) for p in sorted(control)],
        "uuid_semantics": "not decoded; variance measured in repeated native capture",
    }


BLOCK_JS = r"""() => {
  if (window.__characterParityInstalled) return;
  window.__characterParityInstalled = true;
  window.__characterParityBlocked = [];
  window.__characterParityBlockAll = false;
  const blocked = (u,b) => {
    const s=String(u)+' '+String(b||'');
    const writes = new RegExp(
      'batch(?:Async)?Generate|YhhmEf|eb1hJf|MZZa6b|nprQif|ogiZ0b|' +
      'maseQ|createEntity|updateEntity|' +
      'clearCharacter|deleteEntity|upload', 'i');
    return writes.test(s) ||
      (/data\/batchexecute/.test(s) && window.__characterParityBlockAll);
  };
  const reject = (u,b) => { if(window.__characterParityBlockAll && String(b||'').includes('MZZa6b'))
      window.__characterParityBlocked.push({kind:'submit',body:String(b||'')});
    else window.__characterParityBlocked.push({kind:'blocked'}); };
  const f=window.fetch;
  window.fetch=function(i,n) { const u=i?.url||i,b=n?.body||i?.body||null;
    if(blocked(u,b)){reject(u,b);return Promise.reject(new Error('parity probe blocked request'));}
    return f.apply(this,arguments); };
  const o=XMLHttpRequest.prototype.open,s=XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open=function(m,u){this.__cpUrl=u;return o.apply(this,arguments)};
  XMLHttpRequest.prototype.send=function(b){
    if(blocked(this.__cpUrl,b)){reject(this.__cpUrl,b);return;}
    return s.apply(this,arguments);
  };
  if(navigator.sendBeacon){
    const sb=navigator.sendBeacon.bind(navigator);
    navigator.sendBeacon=function(u,b){
      if(blocked(u,b)){reject(u,b);return true;}
      return sb(u,b);
    };
  }
}"""


def validate_input(raw: Any) -> dict[str, Any]:
    """Validate a caller-provided, private input document without opening a browser."""
    if not isinstance(raw, dict):
        raise ValueError("input must be a JSON object")
    project = raw.get("project_id")
    if not isinstance(project, str) or not _UUID.fullmatch(project):
        raise ValueError("project_id must be a UUID")
    prompt = raw.get("prompt")
    if prompt is None and isinstance(raw.get("prompt_source"), dict):
        source = raw["prompt_source"]
        source_path = Path(str(source.get("path", ""))).expanduser()
        keys = source.get("keys")
        if not source_path.is_absolute() or not source_path.is_file() or source_path.is_symlink():
            raise ValueError("prompt_source.path must be an absolute existing regular file")
        if not isinstance(keys, list) or not keys or not all(isinstance(key, str) for key in keys):
            raise ValueError("prompt_source.keys must be a nonempty JSON key path")
        source_data: Any = json.loads(source_path.read_text(encoding="utf-8"))
        for key in keys:
            if not isinstance(source_data, dict) or key not in source_data:
                raise ValueError("prompt_source key path was not found")
            source_data = source_data[key]
        prompt = source_data
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("prompt must be nonempty")
    media, characters = raw.get("media"), raw.get("characters")
    if not isinstance(media, list) or not media:
        raise ValueError("media must contain existing project references")
    if not isinstance(characters, list) or not characters:
        raise ValueError("characters must contain existing Character references")
    for collection, label_field in ((media, "picker_name"), (characters, "name")):
        for item in collection:
            if (
                not isinstance(item, dict)
                or not isinstance(item.get("id"), str)
                or not _UUID.fullmatch(item["id"])
            ):
                raise ValueError("every media and Character id must be a UUID")
            if not isinstance(item.get(label_field), str) or not item[label_field].strip():
                raise ValueError(f"every reference requires a nonempty {label_field}")
    if len({item["id"] for item in media}) != len(media):
        raise ValueError("media ids must be unique")
    if len({item["id"] for item in characters}) != len(characters):
        raise ValueError("Character ids must be unique")
    model = VideoModel.from_cli(raw.get("model", "omni_flash"))
    if model is None:
        raise ValueError("model is required")
    aspect = Aspect.from_cli(raw.get("aspect", "9:16"))
    duration = raw.get("duration", 10)
    count = raw.get("count", 1)
    resolution = raw.get("resolution", "720p")
    if not isinstance(duration, int) or not 1 <= duration <= 60:
        raise ValueError("duration must be an integer from 1 to 60")
    if not isinstance(count, int) or count < 1:
        raise ValueError("count must be a positive integer")
    if resolution not in (None, "720p", "1080p"):
        raise ValueError("resolution must be 720p, 1080p, or null")
    return {**raw, "prompt": prompt, "model_value": model, "aspect_value": aspect}


def field_equality(left: dict[str, Any], right: dict[str, Any]) -> dict[str, bool]:
    """Compare requested wire dimensions, including complete ordered rich prompt."""
    keys = ("rich_prompt", "media_ids", "model", "count", "entity_ids", "project_id")
    return {key: left.get(key) == right.get(key) for key in keys}


def rich_prompt_checks(
    node: Any,
    *,
    media: list[dict[str, str]],
    characters: list[dict[str, str]],
    prompt: str,
) -> dict[str, Any]:
    media_by_id = {item["id"]: item["picker_name"] for item in media}
    entities_by_id = {item["id"]: item["name"] for item in characters}
    found_media: list[dict[str, str]] = []
    found_entities: list[dict[str, str]] = []
    text_parts: list[str] = []

    def walk(value: Any) -> None:
        if not isinstance(value, list):
            return
        if len(value) == 1 and isinstance(value[0], str):
            text_parts.append(value[0])
        if (
            len(value) == 3
            and value[0] is None
            and value[1] is None
            and isinstance(value[2], list)
            and len(value[2]) == 2
            and isinstance(value[2][0], str)
            and isinstance(value[2][1], str)
        ):
            found_entities.append({"id": value[2][0], "name": value[2][1]})
        if (
            len(value) == 2
            and value[0] is None
            and isinstance(value[1], list)
            and len(value[1]) == 1
            and isinstance(value[1][0], list)
            and len(value[1][0]) == 2
            and isinstance(value[1][0][0], str)
        ):
            media_id, name = value[1][0]
            found_media.append({"id": media_id, "name": name})
        for child in value:
            walk(child)

    walk(node)
    actual_text = "".join(text_parts).strip()
    return {
        "media_mentions": found_media,
        "character_mentions": found_entities,
        "media_order_matches": found_media
        == [{"id": item["id"], "name": media_by_id[item["id"]]} for item in media],
        "character_order_matches": found_entities
        == [{"id": item["id"], "name": entities_by_id[item["id"]]} for item in characters],
        "prompt_text_matches": actual_text == prompt.strip(),
        "prompt_length": len(actual_text),
        "prompt_sha256": hashlib.sha256(actual_text.encode()).hexdigest(),
    }


def summarize_prompt(
    node: Any, *, media_names: dict[str, str], entity_names: dict[str, str]
) -> Any:
    """Retain ordered IDs/names and text hashes, while avoiding raw prompt output."""
    if isinstance(node, list):
        if len(node) == 2 and isinstance(node[0], str) and isinstance(node[1], str):
            if node[0] in media_names:
                return {
                    "kind": "media",
                    "id": node[0],
                    "name": node[1],
                    "name_matches_input": node[1] == media_names[node[0]],
                }
            if node[0] in entity_names:
                return {
                    "kind": "entity",
                    "id": node[0],
                    "name": node[1],
                    "name_matches_input": node[1] == entity_names[node[0]],
                }
        return [
            summarize_prompt(value, media_names=media_names, entity_names=entity_names)
            for value in node
        ]
    if isinstance(node, str):
        return {"text_length": len(node), "sha256": hashlib.sha256(node.encode()).hexdigest()}
    return node


async def _native_reference(
    page: Any, composer: MigratedComposer, item: dict[str, str], *, character: bool
) -> dict[str, Any] | None:
    global _STAGE
    before = len(await composer.read_chips(page))
    await page.evaluate(
        """sel => {
          const e=document.querySelector(sel);e.focus();const p=e.lastElementChild||e;
          const r=document.createRange();r.selectNodeContents(p);r.collapse(false);
          const s=getSelection();s.removeAllRanges();s.addRange(r);
        }""",
        COMPOSER,
    )
    await page.wait_for_timeout(200)
    await page.keyboard.type("@", delay=120)
    await page.wait_for_timeout(2200)
    await page.keyboard.type(item["name"] if character else item["picker_name"], delay=100)
    await page.wait_for_timeout(2500)
    label = item["name"] if character else item["picker_name"]
    options = page.locator(f"{PICKER_OPTION}:visible")
    matching = options.filter(has=page.get_by_text(label, exact=True))
    matches = await matching.count()
    if matches != 1:
        raise RuntimeError(
            f"native picker must expose one exact option for {label!r}; found {matches}"
        )
    await matching.click()
    detail_state: dict[str, Any] | None = None
    if character:
        _STAGE = "native_character_detail_name"
        add = page.locator(
            "flow-add-menu-popover-content button.detail-add-to-prompt-btn:visible"
        ).first
        await add.wait_for(state="visible", timeout=5000)
        try:
            await page.wait_for_function(
                """({sel,name}) => {
                  const add=[...document.querySelectorAll(sel)].find(e=>e.getClientRects().length);
                  const p=add?.closest('flow-add-menu-popover-content');
                  if(!p)return false;
                  const leaves=[...p.querySelectorAll('*')].filter(e=>!e.children.length &&
                    !e.closest('button.asset-item,[role=option]')).map(e=>(e.textContent||'').trim());
                  const values=[...p.querySelectorAll('input')].map(e=>(e.value||'').trim());
                  return leaves.includes(name)||values.includes(name);
                }""",
                arg={
                    "sel": "flow-add-menu-popover-content button.detail-add-to-prompt-btn",
                    "name": label,
                },
                timeout=10000,
            )
        except Exception:
            snapshot = await page.evaluate(
                """({sel,name}) => {
                  const add=[...document.querySelectorAll(sel)].find(e=>e.getClientRects().length);
                  const p=add?.closest('flow-add-menu-popover-content');
                  if(!p)return {add_visible:!!add,panel:false,name_leaf:false,name_input:false};
                  const leaves=[...p.querySelectorAll('*')].filter(e=>!e.children.length &&
                    !e.closest('button.asset-item,[role=option]')).map(e=>(e.textContent||'').trim());
                  const values=[...p.querySelectorAll('input')].map(e=>(e.value||'').trim());
                  return {
                    add_visible:!!add,panel:true,name_leaf:leaves.includes(name),
                    name_input:values.includes(name)
                  };
                }""",
                {
                    "sel": "flow-add-menu-popover-content button.detail-add-to-prompt-btn",
                    "name": label,
                },
            )
            print("SAFE_NATIVE_DETAIL_STATE " + json.dumps(snapshot), flush=True)
            raise
        detail_state = await page.evaluate(
            """({sel,name}) => {
              const add=[...document.querySelectorAll(sel)].find(e=>e.getClientRects().length);
              const p=add?.closest('flow-add-menu-popover-content');
              if(!p)return {settled:false,variants:[]};
              const leaves=[...p.querySelectorAll('*')].filter(e=>!e.children.length &&
                !e.closest('button.asset-item,[role=option]')).map(e=>(e.textContent||'').trim());
              const values=[...p.querySelectorAll('input')].map(e=>(e.value||'').trim());
              const settled=leaves.includes(name)||values.includes(name);
              return {settled,variants:[...p.querySelectorAll('button.character-thumbnail-button')]
                .map(e=>({name:(e.innerText||'').trim(),active:e.classList.contains('character-thumbnail-active')}))};
            }""",
            {
                "sel": "flow-add-menu-popover-content button.detail-add-to-prompt-btn",
                "name": label,
            },
        )
        if not detail_state.get("settled"):
            raise RuntimeError("native Character detail did not settle on requested name")
        await add.click()
    _STAGE = "native_chip_commit"
    await page.wait_for_function(
        """({sel,n,id,type}) => {
          const rows=[...document.querySelectorAll(sel)];
          if(rows.length!==n)return false;
          const chip=rows[rows.length-1];
          if(chip.getAttribute('data-reference-type')!==type)return false;
          return type!=='entity' || chip.getAttribute('data-entity-id')===id;
        }""",
        arg={
            "sel": MENTION_CHIP,
            "n": before + 1,
            "id": item["id"],
            "type": "entity" if character else "media",
        },
        timeout=10000,
    )
    committed = (await composer.read_chips(page))[-1]
    expected_type = "entity" if character else "media"
    if committed.get("reference_type") != expected_type:
        actual_type = committed.get("reference_type")
        raise RuntimeError(f"native picker committed {actual_type!r}, expected {expected_type!r}")
    if character and committed.get("entity_id") != item["id"]:
        raise RuntimeError("native picker committed a different Character entity")
    await page.evaluate(
        """sel => {
      const e=document.querySelector(sel);e.focus();const p=e.lastElementChild||e;
      const r=document.createRange();r.selectNodeContents(p);r.collapse(false);
      const s=getSelection();s.removeAllRanges();s.addRange(r);
    }""",
        COMPOSER,
    )
    await page.wait_for_timeout(200)
    await page.keyboard.type(" ", delay=80)
    return detail_state


async def run_probe(input_path: Path, profile: str) -> dict[str, Any]:
    global _STAGE
    _STAGE = "load_input"
    raw = json.loads(input_path.read_text(encoding="utf-8"))
    config = validate_input(raw)
    project = config["project_id"]
    prompt = config["prompt"]
    media = config["media"]
    characters = config["characters"]
    request = GenerateVideoRequest(
        prompt=prompt,
        mode=Mode.R2V,
        model=config["model_value"],
        duration=config["duration"],
        count=config["count"],
        aspect=config["aspect_value"],
        resolution=config["resolution"],
        reference_entities=tuple(item["id"] for item in characters),
        reference_entity_names=tuple(item["name"] for item in characters),
    )
    composer = MigratedComposer()
    report: dict[str, Any] = {"generation_dispatched": 0, "mutation_dispatched": 0, "arms": []}
    media_names = {item["id"]: item["picker_name"] for item in media}
    entity_names = {item["id"]: item["name"] for item in characters}
    raw_specs: list[Any] = []
    _STAGE = "open_profile"
    async with FlowApiClient(profile_dir=auth.profile_dir(profile), headless=False) as client:
        page = client._page
        context = client._context
        assert page is not None and context is not None
        await context.add_init_script(f"({BLOCK_JS})()")
        await page.evaluate(BLOCK_JS)

        page.on("request", lambda req: observe_request(req, report))
        _STAGE = "read_project"
        native = await read_native_project_payload(page, project, timeout_s=30)
        baseline_media_ids = {
            row[0]
            for row in native[2]
            if isinstance(row, list) and len(row) > 1 and row[1] == project
        }
        native_characters = {
            row.character.entity_id: row.character.display_name
            for row in parse_native_characters(native, project)
        }
        if any(native_characters.get(item["id"]) != item["name"] for item in characters):
            raise ValueError("configured Character names do not match the existing project")
        project_media = {
            row[0]
            for row in native[2]
            if isinstance(row, list) and len(row) > 2 and row[1] == project
        }
        if any(item["id"] not in project_media for item in media):
            raise ValueError("configured media IDs are not existing assets in this project")
        initial = await page.evaluate(
            """sel => {
              const e=document.querySelector(sel);if(!e)return 'missing';
              const clone=e.cloneNode(true);
              clone.querySelectorAll('.mention-chip,.prosemirror-placeholder')
                .forEach(n=>n.remove());
              return (clone.innerText||clone.textContent||'').trim();
            }""",
            COMPOSER,
        )
        if initial or await composer.read_chips(page):
            raise RuntimeError("composer draft is nonempty; preserving it and stopping")
        settings_ui: dict[str, Any] | None = None
        for arm in ("native_picker", "production_composer", "native_replay"):
            _STAGE = f"{arm}_settings"
            await composer.ensure_editor(page, project)
            await composer.apply_video_settings(page, request)
            settings_ui = {
                "verified_values": {
                    "model": config["model_value"].value,
                    "duration": config["duration"],
                    "aspect": config["aspect_value"].value,
                    "resolution": config["resolution"],
                    "count": config["count"],
                },
                "ui_selection_verified_by": "MigratedComposer.apply_video_settings",
                "verification_scope": "method returned after reading each requested setting",
            }
            await composer.clear_composer(page)
            native_variants: list[dict[str, Any]] = []
            for index, item in enumerate(media, start=1):
                _STAGE = f"{arm}_media_{index}"
                if arm.startswith("native"):
                    await _native_reference(page, composer, item, character=False)
                else:
                    await composer._mention_by_name(page, item["picker_name"], expect_chips=index)  # noqa: SLF001
            if arm.startswith("native"):
                for item in characters:
                    _STAGE = f"{arm}_character"
                    detail = await _native_reference(page, composer, item, character=True)
                    if detail is not None:
                        native_variants.append({"character": item["name"], **detail})
            else:
                _STAGE = f"{arm}_character"
                await composer.attach_character_entities(
                    page,
                    entity_ids=tuple(entity_names),
                    names=tuple(entity_names.values()),
                    clear=False,
                )
            await composer.send_prompt(page, prompt, append=True)
            chips = await composer.read_chips(page)
            _STAGE = f"{arm}_blocked_submit"
            await page.evaluate("() => {window.__characterParityBlockAll=true}")
            print(
                "SAFE_PRE_SUBMIT_DOM "
                + json.dumps(
                    await page.evaluate(
                        """sel => {
                  const e=document.querySelector(sel);
                  return {editor_focused:document.activeElement===e,
                    editor_text_length:e?.textContent?.length,
                    buttons:[...document.querySelectorAll('button')].filter(b=>
                      b.getClientRects().length && [...b.querySelectorAll('mat-icon,i,span')]
                      .some(n=>(n.textContent||'').trim()==='arrow_forward'))
                    .map(b=>({disabled:b.disabled,classes:b.className,
                      icons:[...b.querySelectorAll('mat-icon,i,span')].map(n=>n.tagName),
                      rect:{x:b.getBoundingClientRect().x,y:b.getBoundingClientRect().y}}))};
                }""",
                        COMPOSER,
                    )
                ),
                flush=True,
            )
            _STAGE = f"{arm}_submit_gate"
            button = await composer._pre_submit_gate(page)  # noqa: SLF001
            _STAGE = f"{arm}_submit_click"
            await button.click(timeout=5000)
            _STAGE = f"{arm}_capture_wait"
            await page.wait_for_function(
                "() => window.__characterParityBlocked.length > 0", timeout=10000
            )
            _STAGE = f"{arm}_capture_read"
            captured = await page.evaluate("() => window.__characterParityBlocked")
            _STAGE = f"{arm}_capture_parse"
            bodies = [item.get("body", "") for item in captured if item.get("kind") == "submit"]
            if len(bodies) != 1:
                raise RuntimeError("expected exactly one blocked R2V submit capture")
            outer = json.loads(parse_qs(bodies[0]).get("f.req", ["[]"])[0])
            entry = next(entry for group in outer for entry in group if entry[0] == "MZZa6b")
            payload = json.loads(entry[1])
            spec = payload[0][0]
            raw_specs.append(spec)
            actual = {
                "rich_prompt": spec[0],
                "media_ids": [row[1] for row in spec[1]],
                "model": spec[2],
                "count": spec[3],
                "entity_ids": [row[0] for row in spec[9]],
                "project_id": payload[1][5],
            }
            check = rich_prompt_checks(spec[0], media=media, characters=characters, prompt=prompt)
            expected = {
                "media_ids": [item["id"] for item in media],
                "count": config["count"],
                "entity_ids": [item["id"] for item in characters],
                "project_id": project,
            }
            actual_for_inputs = {
                "media_ids": actual["media_ids"],
                "model": actual["model"],
                "count": actual["count"],
                "entity_ids": actual["entity_ids"],
                "project_id": actual["project_id"],
            }
            input_equality = field_equality(actual_for_inputs, expected)
            expected_model_key = {
                ("omni_flash", 10): "abra_r2v_10s",
            }.get((config["model_value"].value, config["duration"]))
            input_equality["model"] = (
                spec[2] == expected_model_key if expected_model_key is not None else None
            )
            input_equality["rich_prompt"] = all(
                check[key]
                for key in ("media_order_matches", "character_order_matches", "prompt_text_matches")
            )
            actual_media_mentions = {row["id"]: row["name"] for row in check["media_mentions"]}
            actual_media = [
                {"id": media_id, "name": actual_media_mentions.get(media_id)}
                for media_id in actual["media_ids"]
            ]
            actual_characters = check["character_mentions"]
            report["arms"].append(
                {
                    "arm": arm,
                    "equal_to_inputs": input_equality,
                    "media": actual_media,
                    "characters": actual_characters,
                    "rich_prompt": summarize_prompt(
                        actual["rich_prompt"], media_names=media_names, entity_names=entity_names
                    ),
                    "generation_spec": summarize_prompt(
                        spec, media_names=media_names, entity_names=entity_names
                    ),
                    "prompt_text": {
                        "length": len(prompt),
                        "sha256": hashlib.sha256(prompt.strip().encode()).hexdigest(),
                    },
                    "model": actual["model"],
                    "count": actual["count"],
                    "project_id": actual["project_id"],
                    "chip_types": [chip.get("reference_type") for chip in chips],
                    "native_character_variant_controls": native_variants,
                    "rich_prompt_checks": check,
                    "settings_ui_readback": settings_ui,
                    "generation_blocked": True,
                }
            )
            print("SAFE_ARM_CAPTURE " + json.dumps(report["arms"][-1]), flush=True)
            _STAGE = f"{arm}_cleanup"
            await composer.clear_composer(page)
            if arm != "native_replay":
                await page.reload(wait_until="domcontentloaded")
                await page.locator(COMPOSER).first.wait_for(state="visible")
                draft = await page.evaluate(
                    """sel => {
                      const e=document.querySelector(sel);if(!e)return 'missing';
                      const clone=e.cloneNode(true);
                      clone.querySelectorAll('.mention-chip,.prosemirror-placeholder')
                        .forEach(n=>n.remove());
                      return (clone.innerText||clone.textContent||'').trim();
                    }""",
                    COMPOSER,
                )
                if draft or await composer.read_chips(page):
                    raise RuntimeError(
                        "composer was not empty after reload; preserving draft and stopping"
                    )
                await page.evaluate(BLOCK_JS)
        _STAGE = "verify_unchanged_media"
        after = await read_native_project_payload(page, project, timeout_s=30)
        report["server_media_ids_unchanged"] = baseline_media_ids == {
            row[0]
            for row in after[2]
            if isinstance(row, list) and len(row) > 1 and row[1] == project
        }
        if report["generation_dispatched"] or report["mutation_dispatched"]:
            raise RuntimeError("network observer detected a forbidden dispatch")
        if not report["server_media_ids_unchanged"]:
            raise RuntimeError("project media changed during supposedly read-only parity probe")
        if len(report["arms"]) == 3:
            report["generation_spec_comparison"] = compare_generation_specs(*raw_specs)
            report["arm_parity"] = {
                "model": report["arms"][0]["model"] == report["arms"][1]["model"],
                "count": report["arms"][0]["count"] == report["arms"][1]["count"],
                "project_id": report["arms"][0]["project_id"] == report["arms"][1]["project_id"],
                "rich_prompt": report["arms"][0]["rich_prompt"] == report["arms"][1]["rich_prompt"],
                "generation_spec_nonvarying_fields": report["generation_spec_comparison"][
                    "all_nonvarying_fields_equal"
                ],
                "media_ids": report["arms"][0]["media"] == report["arms"][1]["media"],
                "character_ids_names": report["arms"][0]["characters"]
                == report["arms"][1]["characters"],
                "settings_ui_readback": report["arms"][0]["settings_ui_readback"]
                == report["arms"][1]["settings_ui_readback"],
            }
            report["client_serialization_only"] = True
            report["backend_image_consumption_proved"] = False
            report["wire_aspect_resolution"] = "not decoded"
        print("SAFE_NATIVE_PARITY " + json.dumps(report), flush=True)
    return report


def main() -> int:
    global _STAGE
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="private JSON with existing project/media/Character IDs",
    )
    parser.add_argument("--profile", required=True, help="authenticated migrated Flow profile name")
    args = parser.parse_args()
    if os.environ.get("GFLOW_CLI_FLOW_HOST") != "flow.google.com":
        parser.error("GFLOW_CLI_FLOW_HOST must be flow.google.com")
    try:
        asyncio.run(run_probe(args.input, args.profile))
    except Exception as exc:  # safe summary only; never print prompts or raw request bodies
        frames = traceback.extract_tb(exc.__traceback__)
        print(
            "SAFE_FAILURE "
            + json.dumps(
                {
                    "error_type": type(exc).__name__,
                    "message": redact_sensitive_text(str(exc))[:800],
                    "route": getattr(exc, "route", None),
                    "stage": _STAGE,
                    "cause_type": type(exc.__context__).__name__ if exc.__context__ else None,
                    "cause_message": redact_sensitive_text(str(exc.__context__))[:400]
                    if exc.__context__
                    else None,
                    "trace": [
                        {
                            "file": Path(frame.filename).name,
                            "line": frame.lineno,
                            "function": frame.name,
                        }
                        for frame in frames
                    ],
                }
            ),
            flush=True,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
