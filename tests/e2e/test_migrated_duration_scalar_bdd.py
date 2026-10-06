"""Real Chromium + route-fulfilled DOM; no Google/account/credits."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from playwright.async_api import async_playwright
from pytest_bdd import given, parsers, scenarios, then, when

from gflow_cli.api.transports.migrated_composer import RADIOGROUP, MigratedComposer
from gflow_cli.errors import UiSelectorDriftError

scenarios("../features/migrated_duration_scalar.feature")


@pytest.fixture
def world() -> dict[str, Any]:
    return {"duplicate": False}


@given(parsers.parse('a duration row whose unit is "{unit}"'))
def labels(world: dict[str, Any], unit: str) -> None:
    world["unit"] = unit


@given("two complete duration rows")
def duplicate(world: dict[str, Any]) -> None:
    world.update(unit="วินาที", duplicate=True)


async def drive(world: dict[str, Any], *, pin: bool = False) -> None:
    radios = "".join(
        f'<button role="radio" aria-checked="false" data-seconds="{n}">{n} {world["unit"]}</button>'
        for n in (4, 6, 8, 10)
    )
    group = f'<div role="radiogroup">{radios}</div>'
    html = (
        '<div id="pane"><div role="radiogroup"><button role="radio">x1</button>'
        '<button role="radio">x2</button></div>'
        + group
        + (group if world["duplicate"] else "")
        + '<div role="radiogroup"><button role="radio">360p</button>'
        '<button role="radio">720p</button></div></div>'
        '<script>window.clicks=0; document.querySelectorAll("[role=radio]").forEach(r=>'
        'r.onclick=()=>{window.clicks++; r.parentElement.querySelectorAll("[role=radio]")'
        '.forEach(x=>x.setAttribute("aria-checked",String(x===r)));});</script>'
    )
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            world["post_requests"] = 0

            def observe(request: Any) -> None:
                if request.method == "POST":
                    world["post_requests"] += 1

            page.on("request", observe)
            await page.route(
                "https://flow.google.com/**",
                lambda route: route.fulfill(status=200, content_type="text/html", body=html),
            )
            await page.goto("https://flow.google.com/project/local-duration-only")
            composer = MigratedComposer()
            try:
                if pin:
                    await composer._pin_r2v_duration(page, page.locator("#pane"))  # noqa: SLF001
                else:
                    await composer._select(page, page.locator("#pane"), axis="duration", text="10s")  # noqa: SLF001
            except Exception as exc:
                world["error"] = exc
            world["checked"] = await page.locator('[aria-checked="true"]').evaluate_all(
                "nodes=>nodes.map(r=>Number(r.getAttribute('data-seconds')))"
            )
            world["clicks"] = await page.evaluate("window.clicks")
            world["groups"] = await page.locator(RADIOGROUP).count()
        finally:
            await browser.close()


@when("the shared composer selects ten seconds")
def select(world: dict[str, Any]) -> None:
    asyncio.run(drive(world))


@when("the shared composer pins the reference duration")
def pin(world: dict[str, Any]) -> None:
    asyncio.run(drive(world, pin=True))


@then("the ten-second radio alone is checked")
def ten(world: dict[str, Any]) -> None:
    assert "error" not in world
    assert world["checked"] == [10]


@then("the eight-second radio alone is checked")
def eight(world: dict[str, Any]) -> None:
    assert "error" not in world
    assert world["checked"] == [8]


@then("ambiguity is reported without clicking")
def ambiguous(world: dict[str, Any]) -> None:
    assert isinstance(world.get("error"), UiSelectorDriftError)
    assert world["clicks"] == 0


@then("no generation is submitted")
def no_submit(world: dict[str, Any]) -> None:
    assert world["post_requests"] == 0
    assert world["checked"] in ([], [8], [10])
