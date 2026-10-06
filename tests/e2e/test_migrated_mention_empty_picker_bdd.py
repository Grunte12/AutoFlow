"""Browser-real regression for empty mention pickers on the migrated composer.

Binds ``tests/features/migrated_mention_empty_picker.feature``. The local Flow-origin
route is fulfilled by Playwright, so Chromium exercises real typing, visibility and
keyboard events without Google, a profile, media, or credits.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from playwright.async_api import Page, Route, async_playwright
from pytest_bdd import given, scenarios, then, when

from gflow_cli.api.transports import migrated_composer
from gflow_cli.api.transports.migrated_composer import MENTION_CHIP, MigratedComposer

scenarios("../features/migrated_mention_empty_picker.feature")

PROJECT_URL = "https://flow.google.com/project/e2e-mention-empty-picker"
ASSET_NAME = "requested-reference.png"
ASSET_ID = "e2e-mention-reference-id"

_SCRIPT = """
  const composer = document.querySelector('[contenteditable="true"]');
  const mode = document.body.dataset.picker;
  const picker = document.querySelector('#picker');
  let query = '';
  composer.addEventListener('keydown', event => {
    if (event.key === 'Enter') {
      document.body.dataset.enterPresses = String(
        Number(document.body.dataset.enterPresses || '0') + 1
      );
      if (picker && picker.querySelector('[role="option"]:not([hidden])')) {
        event.preventDefault();
        const chip = document.createElement('span');
        chip.className = 'mention-chip';
        chip.dataset.referenceType = 'media';
        chip.dataset.mentionId = 'e2e-mention-reference-id';
        chip.textContent = '@requested-reference.png';
        composer.appendChild(chip);
        picker.remove();
      } else {
        event.preventDefault();
        document.body.dataset.submitted = 'yes';
      }
      return;
    }
    if (event.key === '@') query = '';
    else if (event.key.length === 1) query += event.key;
    if (event.key === '@' || query.length) {
        if (mode === 'visible' && query.toLowerCase().includes('requested')) {
        const option = picker.querySelector('[role="option"]');
        option.hidden = false;
      }
    }
  });
"""


def _page(mode: str) -> str:
    stale = (
        "<button class='asset-item' role='option' hidden>stale-reference.png</button>"
        if mode == "hidden"
        else ""
    )
    wanted = (
        "<button class='asset-item' role='option' hidden>requested-reference.png</button>"
        if mode == "visible"
        else ""
    )
    return (
        "<!doctype html><html><body data-picker='"
        + mode
        + "' data-submitted='no' data-enter-presses='0'>"
        "<form id='form'><div contenteditable='true' role='textbox'></div></form>"
        f"<div id='picker'>{stale}{wanted}</div>"
        f"<script>{_SCRIPT}</script></body></html>"
    )


@pytest.fixture
def world() -> dict[str, Any]:
    return {}


async def _drive(html: str, world: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    """Run the production mention path against a locally fulfilled Flow URL."""
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        try:
            page: Page = await (await browser.new_context()).new_page()

            async def _serve(route: Route) -> None:
                await route.fulfill(status=200, content_type="text/html", body=html)

            await page.route("https://flow.google.com/**", _serve)
            await page.goto(PROJECT_URL, wait_until="domcontentloaded")
            monkeypatch.setattr(migrated_composer, "FRAME_SEARCH_ATTEMPTS", 1)
            monkeypatch.setattr(migrated_composer, "FRAME_SEARCH_RETRY_PAUSE_S", 0)
            try:
                await MigratedComposer()._mention_by_name(page, ASSET_NAME, expect_chips=1)  # noqa: SLF001
                world["error"] = None
            except BaseException as exc:  # noqa: BLE001 - captured for BDD assertions
                world["error"] = exc
            world["submitted"] = await page.locator("body").get_attribute("data-submitted")
            world["enter_presses"] = await page.locator("body").get_attribute("data-enter-presses")
            world["chips"] = await page.locator(MENTION_CHIP).count()
            world["chip_ids"] = await page.locator(MENTION_CHIP).evaluate_all(
                "nodes => nodes.map(node => node.getAttribute('data-mention-id'))"
            )
        finally:
            await browser.close()


@given("a migrated composer whose mention picker has no results")
def _empty(world: dict[str, Any]) -> None:
    world["html"] = _page("empty")


@given("a migrated composer whose only stale mention option is hidden")
def _hidden(world: dict[str, Any]) -> None:
    world["html"] = _page("hidden")


@given("a migrated composer whose picker offers the requested asset")
def _visible(world: dict[str, Any]) -> None:
    world["html"] = _page("visible")


@when("the driver mentions the requested asset")
def _mention(world: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    asyncio.run(_drive(world["html"], world, monkeypatch))


@then("the composer was not submitted and no mention chip was added")
def _no_submit(world: dict[str, Any]) -> None:
    assert world["submitted"] == "no"
    assert world["enter_presses"] == "0"
    assert world["chips"] == 0
    assert world["error"] is not None


@then("the expected mention chip was committed without submitting")
def _committed(world: dict[str, Any]) -> None:
    assert world["error"] is None, f"visible option did not commit: {world['error']!r}"
    assert world["submitted"] == "no"
    assert world["enter_presses"] == "1"
    assert world["chips"] == 1
    assert world["chip_ids"] == [ASSET_ID]
