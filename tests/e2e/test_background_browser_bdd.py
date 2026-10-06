"""Real macOS Chrome, synthetic DOM only; no Google requests/accounts/credits."""

from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from playwright.async_api import async_playwright
from pytest_bdd import given, scenarios, then, when

from gflow_cli.api.client import FlowApiClient
from gflow_cli.api.transports.ui_automation_video import VideoGenerationMixin
from gflow_cli.config import Settings

pytestmark = pytest.mark.skipif(sys.platform != "darwin", reason="macOS focus contract")
scenarios("../features/background_browser.feature")


def frontmost() -> int:
    # Read NSWorkspace metadata, not screenshots, Accessibility, or personal tabs.
    return int(
        subprocess.check_output(
            [
                "/usr/bin/osascript",
                "-l",
                "JavaScript",
                "-e",
                "ObjC.import('AppKit'); "
                "Number($.NSWorkspace.sharedWorkspace.frontmostApplication.processIdentifier)",
            ],
            text=True,
        ).strip()
    )


@pytest.fixture
def world(tmp_path: Path) -> dict[str, Any]:
    return {"root": tmp_path}


@given("a disposable headed Chrome profile on macOS")
def profile(world: dict[str, Any]) -> None:
    world["foreground"] = frontmost()


async def drive(world: dict[str, Any]) -> None:
    settings = Settings(browser_background=True)
    client = FlowApiClient(profile_dir=world["root"] / "profile", settings=settings)
    kwargs = client._persistent_context_kwargs()  # noqa: SLF001
    kwargs["channel"] = "chrome"
    async with async_playwright() as pw:
        context = await pw.chromium.launch_persistent_context(**kwargs)
        client._context = context  # noqa: SLF001
        try:
            assert not context.pages  # no transient default page
            world["focus_samples"] = [frontmost()]
            pages = await client._open_page_pool(2)  # noqa: SLF001
            world["focus_samples"].append(frontmost())
            page = pages[0]
            await page.set_content(
                '<input id="prompt"><input id="file" type="file">'
                "<button onclick=\"this.dataset.checked='yes'\">Settings</button>"
                "<script>window.ticks=0;setInterval(()=>window.ticks++,50)</script>"
            )
            await page.locator("#prompt").fill("Synthetic prompt; never submitted")
            await page.locator("#file").set_input_files(
                {
                    "name": "fixture.txt",
                    "mimeType": "text/plain",
                    "buffer": b"local fixture",
                }
            )
            await page.get_by_role("button", name="Settings", exact=True).click()
            await VideoGenerationMixin._nudge_tab_if_stalled(  # noqa: SLF001
                page, [], 0, 0, False, 0, "local-fixture"
            )
            await asyncio.sleep(1)
            world["focus_samples"].append(frontmost())
            world["states"] = []
            for pooled in pages:
                session = await context.new_cdp_session(pooled)
                bounds = await session.send("Browser.getWindowForTarget")
                world["states"].append(bounds["bounds"]["windowState"])
                await session.detach()
            world["interaction"] = await page.evaluate("""({
                prompt:document.querySelector('#prompt').value,
                filename:document.querySelector('#file').files[0].name,
                checked:document.querySelector('button').dataset.checked,
                ticks:window.ticks})""")
        finally:
            await context.close()
        world["closed"] = not context.pages


@when("generation opens two background pages")
def open_pages(world: dict[str, Any]) -> None:
    asyncio.run(drive(world))


@when("a page fills a prompt uploads a local fixture and clicks a settings control")
def interact(world: dict[str, Any]) -> None:
    assert world["interaction"]["checked"] == "yes"


@when("the video status observer encounters a stall")
def stall(world: dict[str, Any]) -> None:
    assert world["states"] == ["minimized", "minimized"]


@then("the original desktop application retains focus")
def focus(world: dict[str, Any]) -> None:
    assert all(pid == world["foreground"] for pid in world["focus_samples"])


@then("both browser windows remain minimized")
def minimized(world: dict[str, Any]) -> None:
    assert world["states"] == ["minimized", "minimized"]


@then("browser interactions and timer polling still work")
def work(world: dict[str, Any]) -> None:
    assert world["interaction"]["filename"] == "fixture.txt"
    assert world["interaction"]["prompt"].startswith("Synthetic")
    assert world["interaction"]["ticks"] >= 5
    assert world["closed"]
