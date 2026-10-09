"""Read-only native Character readback on flow.google.com."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from gflow_cli.api.transports.native_character_ui import (
    NATIVE_CHARACTER_RPC,
    NATIVE_PROJECT_URL,
    read_native_characters,
    read_verified_native_character,
)
from gflow_cli.errors import TransportTimeoutError, WireFormatError

PROJECT = "a0000000-0000-4000-8000-000000000001"
OTHER_PROJECT = "a0000000-0000-4000-8000-000000000002"
ENTITY = "b0000000-0000-4000-8000-000000000001"
WORKFLOW = "c0000000-0000-4000-8000-000000000001"
MEDIA = "d0000000-0000-4000-8000-000000000001"


def _frame(rpcid: str, payload: Any) -> str:
    frame = [["wrb.fr", rpcid, json.dumps(payload), None, None, None, "generic"]]
    return ")]}'\n\n10\n" + json.dumps(frame) + "\n"


def _payload(*, project_id: str = PROJECT) -> list[Any]:
    workflow = [
        WORKFLOW,
        None,
        None,
        ["portrait", [1, 2], None, None, MEDIA, None, [3, 4]],
        project_id,
        ENTITY,
    ]
    entity = [
        project_id,
        ENTITY,
        None,
        [1, "Momo", [[[WORKFLOW]]]],
        MEDIA,
        [1086, 1448],
    ]
    return [None, [workflow], None, None, None, [entity]]


class _Response:
    def __init__(self, url: str, body: str) -> None:
        self.url = url
        self._body = body

    async def text(self) -> str:
        return self._body


class _Locator:
    def __init__(self, page: _FakePage, selector: str) -> None:
        self.page = page
        self.selector = selector

    async def wait_for(self, **kwargs: Any) -> None:
        self.page.waits.append((self.selector, kwargs))
        self.page.hydration_wait_started.set()
        if not self.page.hydrated:
            await self.page.hydration.wait()


class _FakePage:
    def __init__(
        self,
        *,
        responses: list[_Response] | None = None,
        hydrated: bool = True,
        url: str = "about:blank",
        landed_url: str | None = None,
    ) -> None:
        self.responses = responses or []
        self.hydrated = hydrated
        self.hydration = asyncio.Event()
        if hydrated:
            self.hydration.set()
        self.url = url
        self.landed_url = landed_url
        self.gotos: list[tuple[str, dict[str, Any]]] = []
        self.waits: list[tuple[str, dict[str, Any]]] = []
        self.hydration_wait_started = asyncio.Event()
        self.handlers: list[Any] = []

    def on(self, event: str, handler: Any) -> None:
        assert event == "response"
        self.handlers.append(handler)

    def remove_listener(self, event: str, handler: Any) -> None:
        assert event == "response"
        self.handlers.remove(handler)

    def locator(self, selector: str) -> _Locator:
        return _Locator(self, selector)

    async def goto(self, url: str, **kwargs: Any) -> None:
        self.gotos.append((url, kwargs))
        self.url = self.landed_url or url
        for response in self.responses:
            for handler in tuple(self.handlers):
                await handler(response)


def _response(rpcid: str, payload: Any, *, host: str = "flow.google.com") -> _Response:
    return _Response(
        f"https://{host}/_/AiSandboxAngularFrontend/data/batchexecute?rpcids={rpcid}",
        _frame(rpcid, payload),
    )


async def test_read_native_characters_navigates_and_reads_native_rpc() -> None:
    page = _FakePage(responses=[_response(NATIVE_CHARACTER_RPC, _payload())])

    result = await read_native_characters(page, PROJECT, timeout_s=0.1)  # type: ignore[arg-type]

    assert len(result) == 1
    assert result[0].character.entity_id == ENTITY
    assert result[0].workflow_media_bindings == ((WORKFLOW, MEDIA),)
    assert page.gotos == [
        (
            NATIVE_PROJECT_URL.format(project_id=PROJECT),
            {"wait_until": "domcontentloaded", "timeout": 45_000},
        )
    ]
    assert page.waits == [("flow-prompt-box", {"state": "visible"})]
    assert page.handlers == []


async def test_verified_read_uses_exact_binding_parser() -> None:
    page = _FakePage(responses=[_response(NATIVE_CHARACTER_RPC, _payload())])

    result = await read_verified_native_character(
        page,  # type: ignore[arg-type]
        PROJECT,
        ENTITY,
        timeout_s=0.1,
    )

    assert result.character.entity_id == ENTITY
    assert result.workflow_media_bindings == ((WORKFLOW, MEDIA),)


async def test_ignores_other_host_and_other_rpc_frames() -> None:
    page = _FakePage(
        responses=[
            _response(NATIVE_CHARACTER_RPC, _payload(), host="example.invalid"),
            _response("UpteDb", _payload()),
            _response(NATIVE_CHARACTER_RPC, _payload()),
        ]
    )

    result = await read_native_characters(page, PROJECT, timeout_s=0.1)  # type: ignore[arg-type]

    assert result[0].character.entity_id == ENTITY


async def test_missing_rpc_times_out_and_removes_listener() -> None:
    page = _FakePage(responses=[_response("UpteDb", _payload())])

    with pytest.raises(TransportTimeoutError, match=NATIVE_CHARACTER_RPC) as exc:
        await read_native_characters(page, PROJECT, timeout_s=0.001)  # type: ignore[arg-type]

    assert "not_submitted" not in str(exc.value)
    assert page.handlers == []


async def test_wrong_project_payload_is_rejected_without_wire_content() -> None:
    page = _FakePage(
        responses=[_response(NATIVE_CHARACTER_RPC, _payload(project_id=OTHER_PROJECT))]
    )

    with pytest.raises(WireFormatError) as exc:
        await read_native_characters(page, PROJECT, timeout_s=0.1)  # type: ignore[arg-type]

    assert OTHER_PROJECT not in str(exc.value)
    assert page.handlers == []


async def test_malformed_payload_is_rejected_without_echoing_raw_body() -> None:
    page = _FakePage(
        responses=[
            _response(
                NATIVE_CHARACTER_RPC,
                {"private": "PRIVATE_RAW_PAYLOAD_SENTINEL"},
            )
        ]
    )

    with pytest.raises(WireFormatError) as exc:
        await read_native_characters(page, PROJECT, timeout_s=0.1)  # type: ignore[arg-type]

    assert "PRIVATE_RAW_PAYLOAD_SENTINEL" not in str(exc.value)
    assert page.handlers == []


@pytest.mark.parametrize(
    ("method", "args"),
    [
        (read_native_characters, ("not-a-uuid",)),
        (read_verified_native_character, (PROJECT, "not-a-uuid")),
    ],
)
async def test_invalid_ids_are_rejected_before_navigation(
    method: Any, args: tuple[str, ...]
) -> None:
    page = _FakePage(responses=[_response(NATIVE_CHARACTER_RPC, _payload())])

    with pytest.raises(WireFormatError, match="canonical UUID"):
        await method(page, *args, timeout_s=0.1)

    assert page.gotos == []
    assert page.handlers == []


async def test_flow_payload_is_not_returned_until_composer_anchor_is_hydrated() -> None:
    page = _FakePage(
        responses=[_response(NATIVE_CHARACTER_RPC, _payload())],
        hydrated=False,
    )
    result_task = asyncio.create_task(
        read_native_characters(page, PROJECT, timeout_s=0.1)  # type: ignore[arg-type]
    )
    await asyncio.wait_for(page.hydration_wait_started.wait(), timeout=0.1)
    assert not result_task.done()
    page.hydration.set()

    result = await result_task

    assert result[0].character.entity_id == ENTITY
    assert page.waits[0][0] == "flow-prompt-box"


async def test_redirect_to_another_project_is_rejected_even_with_empty_payload() -> None:
    page = _FakePage(
        responses=[_response(NATIVE_CHARACTER_RPC, [None, [], None, None, None, []])],
        landed_url=NATIVE_PROJECT_URL.format(project_id=OTHER_PROJECT),
    )

    with pytest.raises(WireFormatError, match="requested project"):
        await read_native_characters(page, PROJECT, timeout_s=0.1)  # type: ignore[arg-type]

    assert page.handlers == []
