"""Scope REA's passive inspection to one owned Flow browser, without MCP setup.

No proxy, request replay, cookie export, navigation by REA, or Generate gesture.
Only a loopback CDP port is added to the existing AutoFlow launch seam. The
browser/profile lease closes when inspection completes. Raw Evidence is not
printed: report summaries and matching shipped-source snippets only.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import socket
import sys
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlsplit
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _spike_common import resolve_profile_dir  # noqa: E402

from gflow_cli.api.client import FlowApiClient  # noqa: E402
from gflow_cli.redaction import redact_sensitive_text  # noqa: E402


async def rea(*args: str) -> dict[str, Any]:
    process = await asyncio.create_subprocess_exec(
        "npx",
        "-y",
        "rea-agents@6.2.0",
        *args,
        "--format",
        "json",
        "--full-output",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=60)
    except TimeoutError:
        process.kill()
        await process.wait()
        raise RuntimeError("REA command exceeded its bounded inspection window") from None
    if process.returncode:
        try:
            failure = json.loads(stdout)
            error = failure.get("data", failure)
            if not isinstance(error, dict):
                error = failure
            detail = {key: error[key] for key in ("code", "message") if key in error}
        except (ValueError, TypeError, AttributeError):
            detail = {"stderr": redact_sensitive_text(stderr.decode(errors="replace")[:600])}
        raise RuntimeError(f"REA exit {process.returncode}: {json.dumps(detail)}")
    return cast("dict[str, Any]", json.loads(stdout))


def uuid_arg(value: str) -> str:
    if str(UUID(value)) != value:
        raise argparse.ArgumentTypeError("expected canonical UUID")
    return value


async def inspect(
    profile: str,
    project: str,
    *,
    entity: str | None = None,
    sources: bool = False,
    visible: bool = False,
) -> None:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]

    class InspectionClient(FlowApiClient):
        def _persistent_context_kwargs(self) -> dict[str, Any]:
            result = super()._persistent_context_kwargs()
            result["args"] = [
                *cast("list[str]", result["args"]),
                "--remote-debugging-address=127.0.0.1",
                f"--remote-debugging-port={port}",
            ]
            return result

    async with InspectionClient(
        profile_dir=resolve_profile_dir(profile), headless=not visible
    ) as client:
        page = await client._checkout_page()  # noqa: SLF001 - owns this leased context
        try:
            target_url = f"https://flow.google.com/project/{project}"
            if entity is not None:
                target_url += f"/character/{entity}"
            await page.goto(target_url, wait_until="domcontentloaded", timeout=45_000)
            await page.locator(
                "flow-character-edit-page" if entity else "flow-prompt-box"
            ).wait_for(timeout=20_000)
            endpoint = f"http://127.0.0.1:{port}"
            assert client._context is not None  # noqa: SLF001
            response = await client._context.request.get(endpoint + "/json/version")  # noqa: SLF001
            if response.status != 200:
                raise RuntimeError("Owned browser's loopback endpoint is unavailable")
            inventory = await rea(
                "list-browser-targets", endpoint, "--allowed-origins", "https://flow.google.com"
            )
            targets = inventory["data"]["normalized_result"]["targets"]
            matching = [item for item in targets if item["url"] == page.url]
            if len(matching) != 1:
                raise RuntimeError("REA could not identify exactly one owned Flow target")
            print(
                json.dumps(
                    {
                        "owned_target_verified": True,
                        "visible": visible,
                        "generation_submitted": False,
                    },
                    sort_keys=True,
                )
            )
            if sources:
                capture = await rea(
                    "inspect-web-page",
                    endpoint,
                    matching[0]["target_id"],
                    "--allowed-origins",
                    "https://flow.google.com",
                    "--allowed-origins",
                    "https://www.gstatic.com",
                    "--include-script-sources",
                    "--observation-ms",
                    "250",
                )
                scripts = capture["data"]["normalized_result"]["scripts"]
                findings = []
                for item in scripts["items"]:
                    # Exclude inline bootstrap sources which can contain account data.
                    script_url = urlsplit(item["url"])
                    shipped = script_url.hostname in ("flow.google.com", "www.gstatic.com") and (
                        "/_/" in script_url.path or script_url.path.endswith(".js")
                    )
                    if not shipped or not item["source"]["included"]:
                        continue
                    artifact = item["source"]["artifact"]
                    source = artifact["text"]
                    for match in list(re.finditer(r"maseQ|rzMKMb|_\.Xx=class|i2a", source))[:12]:
                        snippet = source[max(0, match.start() - 100) : match.end() + 1100]
                        findings.append(
                            {
                                "symbol": match.group(),
                                "sha256": artifact["sha256"],
                                "snippet": [
                                    redact_sensitive_text(snippet[i : i + 400])
                                    for i in range(0, len(snippet), 400)
                                ],
                            }
                        )
                print(
                    json.dumps(
                        {
                            "scripts_observed": scripts["total"],
                            "matching_source_snippets": findings[:16],
                        },
                        sort_keys=True,
                    )
                )
        finally:
            client._checkin_page(page)  # noqa: SLF001


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--project", type=uuid_arg, required=True)
    parser.add_argument("--entity", type=uuid_arg)
    parser.add_argument("--sources", action="store_true")
    parser.add_argument(
        "--visible",
        action="store_true",
        help="Opt in to a visible browser for human debugging; default is headless inspection.",
    )
    args = parser.parse_args()
    asyncio.run(
        inspect(
            args.profile,
            args.project,
            entity=args.entity,
            sources=args.sources,
            visible=args.visible,
        )
    )
