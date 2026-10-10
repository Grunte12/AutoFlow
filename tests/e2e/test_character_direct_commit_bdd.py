from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
from playwright.async_api import Page, async_playwright
from pytest_bdd import given, scenarios, then, when

from gflow_cli.api.transports.migrated_composer import MigratedComposer
from gflow_cli.errors import ReferenceNotFoundError

scenarios("../features/character_direct_commit.feature")


@pytest.fixture
def world() -> dict[str, Any]:
    return {}


GOOFY_ID = "entity-goofy-001"
MEMO_ID = "entity-memo-002"
MEDIA_ID = "media-existing-003"
_COMPOSER = "[contenteditable='true']"
_CHIPS = ".mention-chip"


def _fixture_html(commits: dict[str, dict[str, str]] | None = None) -> str:
    initial = (
        f"<span class='mention-chip' data-entity-id='{MEDIA_ID}' "
        "data-reference-type='media' contenteditable='false'>Existing shot</span><p><br></p>"
    )
    commit_json = json.dumps(commits or {})
    return f"""<!doctype html>
<html><body>
  <div contenteditable="true" role="textbox">{initial}</div>
  <div class="picker" hidden>
    <button class="asset-item" role="option" data-name="Goofy">Goofy</button>
    <button class="asset-item" role="option" data-name="Memo">Memo</button>
  </div>
  <button class="detail-add-to-prompt-btn" hidden>Add</button>
  <script>
    const editor = document.querySelector("[contenteditable='true']");
    const picker = document.querySelector(".picker");
    const commits = {commit_json};
    let query = "";
    window.enterPressed = false;
    window.addClicked = false;
    document.addEventListener("keydown", event => {{
      if (event.key === "Enter") window.enterPressed = true;
      if (event.key === "@") {{ query = ""; picker.hidden = false; }}
      else if (!picker.hidden && event.key.length === 1) query += event.key;
      if (!picker.hidden) {{
        for (const option of picker.querySelectorAll("[role=option]"))
          option.hidden = !option.dataset.name.toLowerCase().startsWith(query.toLowerCase());
      }}
    }});
    for (const option of picker.querySelectorAll("[role=option]")) {{
      option.addEventListener("click", () => {{
        const name = option.dataset.name;
        picker.hidden = true;
        setTimeout(() => {{
          const commit = commits[name];
          if (commit) {{
            const chip = document.createElement("span");
            chip.className = "mention-chip";
            chip.contentEditable = "false";
            chip.dataset.entityId = commit.id;
            chip.dataset.referenceType = commit.kind;
            chip.textContent = name;
            editor.append(chip);
          }}
        }}, 150);
      }});
    }}
    document.querySelector(".detail-add-to-prompt-btn").addEventListener("click", () => {{
      window.addClicked = true;
    }});
  </script>
</body></html>"""


def _run(world: dict[str, Any], action: Any) -> None:
    async def drive() -> None:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            try:
                page: Page = await (await browser.new_context()).new_page()
                await page.set_content(world["html"])
                world["page"] = page
                try:
                    await action(page)
                except BaseException as exc:  # noqa: BLE001 - asserted by Gherkin step
                    world["error"] = exc
                world["chips"] = await MigratedComposer().read_chips(page)
                world["enter_pressed"] = await page.evaluate("window.enterPressed")
                world["add_clicked"] = await page.evaluate("window.addClicked")
            finally:
                await browser.close()

    asyncio.run(drive())


@given("a browser composer with an existing media chip and exact character options")
def _valid_composer(world: dict[str, Any]) -> None:
    world["html"] = _fixture_html()


@given("a browser composer with a direct a different entity commit")
def _different_entity_composer(world: dict[str, Any]) -> None:
    world["html"] = _fixture_html({"Goofy": {"kind": "entity", "id": MEMO_ID}})


@given("a browser composer with a direct a media chip commit")
def _media_composer(world: dict[str, Any]) -> None:
    world["html"] = _fixture_html({"Goofy": {"kind": "media", "id": GOOFY_ID}})


@when("I select the requested characters through the composer")
def _select_characters(world: dict[str, Any]) -> None:
    async def action(page: Page) -> None:
        await MigratedComposer().attach_character_entities(
            page,
            entity_ids=(GOOFY_ID, MEMO_ID),
            names=("Goofy", "Memo"),
            clear=False,
        )
        assert await page.locator(".picker").is_hidden()

    world["html"] = _fixture_html(
        {
            "Goofy": {"kind": "entity", "id": GOOFY_ID},
            "Memo": {"kind": "entity", "id": MEMO_ID},
        }
    )
    _run(world, action)


@when("I validate the requested character entity")
def _validate_direct_commit(world: dict[str, Any]) -> None:
    _run(
        world,
        lambda page: MigratedComposer().attach_character_entities(
            page, entity_ids=(GOOFY_ID,), names=("Goofy",), clear=False
        ),
    )


@then("the requested entity IDs are attached in order and the media chip is preserved")
def _assert_entity_chips(world: dict[str, Any]) -> None:
    assert "error" not in world
    assert [chip["entity_id"] for chip in world["chips"]] == [MEDIA_ID, GOOFY_ID, MEMO_ID]
    assert [chip["reference_type"] for chip in world["chips"]] == [
        "media",
        "entity",
        "entity",
    ]
    assert world["chips"][0]["text"] == "Existing shot"


@then("no Enter key or Add button is used")
def _assert_direct_path(world: dict[str, Any]) -> None:
    assert world["enter_pressed"] is False
    assert world["add_clicked"] is False


@then("the composer raises ReferenceNotFoundError before submission")
def _assert_mismatch_rejected(world: dict[str, Any]) -> None:
    assert isinstance(world.get("error"), ReferenceNotFoundError)
    assert world["add_clicked"] is False
    assert world["enter_pressed"] is False
