"""Capture one native MCP R2V request without dispatching generation.

Uses the registered MCP handler and its real queue/client/composer. Two local
image uploads may add project assets; no Character/project is created. In-page
fetch/XHR guards block all generation RPCs from before composer gestures, and
all batchexecute traffic at the final click. A network observer must see zero
generation dispatches. The intentional typed stop is not a generated video.

--probe-unverified temporarily bypasses ONLY the local 10s policy in this test
process, never on the installed daemon, to measure the native wire before fixing
the policy. It is not an end-user workaround.

Reading: exact mixed bindings + Omni R2V 10s/count1 + zero dispatch = input proof,
not rendered video success. Missing/mismatched capture = unverified; never retry.
Output contains IDs/settings/hashes, not raw bodies, prompts, URLs or tokens.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from gflow_cli.api.client import FlowApiClient  # noqa: E402
from gflow_cli.api.transports import migrated_composer as composer_mod  # noqa: E402
from gflow_cli.api.transports.batchexecute import parse_frames  # noqa: E402
from gflow_cli.api.transports.saved_character_video import character_submission  # noqa: E402
from gflow_cli.api.video import Mode, VideoModel  # noqa: E402
from gflow_cli.errors import ConfigurationError  # noqa: E402
from gflow_cli.mcp import tools  # noqa: E402, F401 - register the real tool
from gflow_cli.mcp.server import server  # noqa: E402

# No raw captured body is persisted. The app's original functions are never called
# for a blocked request; arming all mode also blocks an unknown future submit RPC.
BLOCK_JS = r"""() => {
  if (window.__autoflowBlocked) return;
  window.__autoflowBlocked = []; window.__autoflowBlockAll = false;
  const isTarget = (u,b) => {
    const s=String(u)+' '+String(b || '');
    return /batch(?:Async)?Generate/.test(s) ||
      (/data\/batchexecute/.test(s) && (window.__autoflowBlockAll ||
       /YhhmEf|eb1hJf|MZZa6b|nprQif|ogiZ0b/.test(s)));
  };
  const f=window.fetch;
  window.fetch=function(i,n) {
    const u=i?.url || i, b=n?.body || i?.body || null;
    if (isTarget(u,b)) {
      window.__autoflowBlocked.push({body:String(b || '')});
      return Promise.reject(new Error('AutoFlow no-dispatch verification'));
    }
    return f.apply(this,arguments);
  };
  const o=XMLHttpRequest.prototype.open, s=XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open=function(m,u) {this.__autoflowUrl=u;return o.apply(this,arguments)};
  XMLHttpRequest.prototype.send=function(b) {
    if (isTarget(this.__autoflowUrl,b)) {
      window.__autoflowBlocked.push({body:String(b || '')}); return;
    }
    return s.apply(this,arguments);
  };
}"""


async def capture(arguments: dict, *, probe_unverified: bool = False) -> dict:
    assert arguments["mode"] == "r2v" and arguments["model"] == "omni_flash"
    assert arguments["duration"] == 10 and arguments["count"] == 1
    assert len(arguments["reference_images"]) == len(arguments["reference_entities"]) == 2
    report: dict = {"generation_dispatched": 0, "capture_count": 0, "upload_shapes": []}
    original_enter = FlowApiClient.__aenter__
    original_validate = composer_mod.validate_migrated_video_configuration
    original_settings = composer_mod.MigratedComposer.apply_video_settings

    async def verified_settings(self, page, request):
        await original_settings(self, page, request)
        # Production selectors read back every chosen control before returning.
        report["settings_verified"] = {
            "model": request.model.value,
            "duration": request.duration,
            "aspect": request.aspect.value,
            "resolution": request.resolution,
            "count": request.count,
        }

    async def guarded_enter(self):
        client = await original_enter(self)
        assert client._context is not None and client._page is not None
        await client._context.add_init_script(f"({BLOCK_JS})()")
        await client._page.evaluate(BLOCK_JS)

        def observe(request):
            if re.search(r"batch(?:Async)?Generate", request.url):
                report["generation_dispatched"] += 1
                return
            if "batchexecute" not in request.url:
                return
            body = request.post_data or ""
            if any(rpc in request.url or rpc in body for rpc in composer_mod.SUBMIT_RPCS):
                report["generation_dispatched"] += 1

        client._page.on("request", observe)

        async def observe_upload(response):
            if "batchexecute" not in response.url or "maseQ" not in response.url:
                return
            try:
                frames = parse_frames(await response.text())
                for rpc, payload in frames:
                    if rpc == "maseQ":
                        report["upload_shapes"].append(
                            {
                                "type": type(payload).__name__,
                                "length": len(payload) if isinstance(payload, list) else None,
                                "row_types": [type(x).__name__ for x in payload]
                                if isinstance(payload, list)
                                else [],
                            }
                        )
            except Exception:
                pass

        client._page.on("response", observe_upload)
        return client

    def probe_policy(request):
        if not (
            probe_unverified
            and request.mode is Mode.R2V
            and request.model is VideoModel.OMNI_FLASH
            and request.duration == 10
        ):
            original_validate(request)

    async def blocked_submit(self, page, **expected):
        assert expected["project_id"] == arguments["project"]
        assert tuple(expected["expect_entity_ids"]) == tuple(arguments["reference_entities"])
        media_ids = tuple(expected["expect_reference_ids"])
        assert len(media_ids) == 2
        await page.evaluate("() => { window.__autoflowBlockAll=true; }")
        submit = await self._pre_submit_gate(page)
        await submit.click(timeout=5_000)
        await page.wait_for_function(
            "() => window.__autoflowBlocked.some(r => r.body.includes('MZZa6b'))",
            timeout=20_000,
        )
        rows = await page.evaluate("() => window.__autoflowBlocked")
        submits = []
        for row in rows:
            outer = json.loads(parse_qs(row["body"]).get("f.req", ["[]"])[0])
            submits.extend(
                (entry, row["body"]) for group in outer for entry in group if entry[0] == "MZZa6b"
            )
        assert len(submits) == 1, "Missing or repeated blocked generation request"
        entry, body = submits[0]
        character_submission(
            body, arguments["project"], tuple(arguments["reference_entities"]), arguments["prompt"]
        )
        assert composer_mod._r2v_body_problem(body, "MZZa6b", media_ids) is None
        spec = json.loads(entry[1])[0][0]
        assert spec[2] == "abra_r2v_10s" and spec[3] == 1, "Wrong model/duration/count"
        assert report["generation_dispatched"] == 0, "Generation crossed the guard"
        report.update(
            capture_count=1,
            rpcid="MZZa6b",
            model_key=spec[2],
            count=spec[3],
            entity_ids=list(expected["expect_entity_ids"]),
            media_ids=list(media_ids),
            prompt_verified=True,
            bindings_verified=True,
        )
        raise ConfigurationError("Intentional no-dispatch capture completed; no video generated")

    with (
        patch.object(FlowApiClient, "__aenter__", guarded_enter),
        patch.object(composer_mod, "validate_migrated_video_configuration", probe_policy),
        patch.object(composer_mod.MigratedComposer, "apply_video_settings", verified_settings),
        patch.object(composer_mod.MigratedComposer, "submit_and_observe", blocked_submit),
    ):
        result = await server.call_tool("gflow_generate_video", {**arguments, "wait": True})
        report["mcp_is_error"] = result.is_error if hasattr(result, "is_error") else None
        for block in result.content:
            if getattr(block, "type", None) == "text":
                try:
                    value = json.loads(block.text)
                    if isinstance(value, dict) and isinstance(value.get("error"), dict):
                        report["mcp_error"] = {
                            k: value["error"].get(k) for k in ("title", "detail", "exit_code")
                        }
                except (ValueError, TypeError):
                    pass
    assert report["capture_count"] == 1 and report["generation_dispatched"] == 0, report
    assert report.get("mcp_error", {}).get("detail") == (
        "Intentional no-dispatch capture completed; no video generated"
    ), report
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--inputs-dir", type=Path, required=True)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--probe-unverified", action="store_true")
    args = parser.parse_args()
    arguments = json.loads(args.request.read_text())["arguments"]
    ids = arguments.pop("reference_file_ids")
    assert all(re.fullmatch(r"[a-f0-9]{32}", value) for value in ids)
    files = [args.inputs_dir / f"{value}.png" for value in ids]
    assert all(path.is_absolute() and path.is_file() for path in files)
    arguments["reference_images"] = [str(path) for path in files]
    arguments["profile"] = args.profile
    report = asyncio.run(capture(arguments, probe_unverified=args.probe_unverified))
    args.out.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
