"""Read native Flow Character entities from the migrated project's own page load.

This transport only observes the page's ``Zzl0ze`` reply. It does not submit a
request, create or edit an entity, or own the caller's Playwright page.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, NoReturn
from urllib.parse import urlsplit
from uuid import UUID

from gflow_cli.api.transports.batchexecute import parse_frames
from gflow_cli.api.transports.native_character import (
    NativeCharacterReadback,
    parse_native_characters,
    parse_verified_native_character,
)
from gflow_cli.errors import TransportTimeoutError, WireFormatError

if TYPE_CHECKING:
    from playwright.async_api import Page

NATIVE_CHARACTER_RPC = "Zzl0ze"
NATIVE_PROJECT_URL = "https://flow.google.com/project/{project_id}"
NATIVE_CHARACTER_READY = "flow-prompt-box"
NATIVE_CHARACTER_READ_TIMEOUT_S = 20.0
NATIVE_CHARACTER_NAVIGATION_TIMEOUT_MS = 45_000
_ROUTE = f"batchexecute:{NATIVE_CHARACTER_RPC}"
_FLOW_HOST = "flow.google.com"


def _canonical_uuid(value: object, field: str) -> str:
    """Validate a route identifier without echoing caller or wire values."""
    if not isinstance(value, str):
        _invalid_uuid(field)
    try:
        canonical = str(UUID(value))
    except (ValueError, AttributeError):
        _invalid_uuid(field)
    if value != canonical:
        _invalid_uuid(field)
    return canonical


def _invalid_uuid(field: str) -> NoReturn:
    raise WireFormatError(
        f"native character readback: {field} must be a canonical UUID",
        route=_ROUTE,
        discovery={"format": "native-character-v1", "reason": "non-canonical identifier"},
    )


def _is_flow_batchexecute(url: str) -> bool:
    parsed = urlsplit(url)
    return (
        parsed.scheme == "https"
        and parsed.hostname == _FLOW_HOST
        and parsed.path.endswith("/data/batchexecute")
    )


def _is_requested_project_route(url: str, project_id: str) -> bool:
    parsed = urlsplit(url)
    return (
        parsed.scheme == "https"
        and parsed.hostname == _FLOW_HOST
        and parsed.path.rstrip("/") == f"/project/{project_id}"
    )


async def _read_project_payload(page: Page, project_id: str, *, timeout_s: float) -> object:
    """Navigate the caller-owned page and observe its native project listing."""
    project_id = _canonical_uuid(project_id, "project id")
    reply: asyncio.Future[object] = asyncio.get_running_loop().create_future()

    async def on_response(response: Any) -> None:
        if reply.done() or not _is_flow_batchexecute(str(getattr(response, "url", ""))):
            return
        try:
            body = await response.text()
        except Exception:  # noqa: BLE001 - aborted or unreadable bodies are not evidence
            return
        for rpcid, payload in parse_frames(body):
            if rpcid == NATIVE_CHARACTER_RPC and not reply.done():
                reply.set_result(payload)
                return

    page.on("response", on_response)
    ready_task: asyncio.Task[None] | None = None
    try:
        await page.goto(
            NATIVE_PROJECT_URL.format(project_id=project_id),
            wait_until="domcontentloaded",
            timeout=NATIVE_CHARACTER_NAVIGATION_TIMEOUT_MS,
        )
        ready_task = asyncio.create_task(
            page.locator(NATIVE_CHARACTER_READY).wait_for(state="visible")
        )
        try:
            payload, _ = await asyncio.wait_for(
                asyncio.gather(reply, ready_task),
                timeout=timeout_s,
            )
        except TimeoutError as exc:
            raise TransportTimeoutError(
                detail=(
                    f"Flow did not return {NATIVE_CHARACTER_RPC} and render the "
                    f"composer-ready anchor within {timeout_s:.0f}s of opening the project."
                ),
                remediation_hint=(
                    "No native Character readback was verified. Re-open the project and "
                    "retry the read; do not infer that a Character is absent from this timeout."
                ),
                route=_ROUTE,
            ) from exc
    finally:
        if not reply.done():
            reply.cancel()
        if ready_task is not None and not ready_task.done():
            ready_task.cancel()
        if ready_task is not None:
            await asyncio.gather(ready_task, return_exceptions=True)
        page.remove_listener("response", on_response)

    if not _is_requested_project_route(str(getattr(page, "url", "")), project_id):
        raise WireFormatError(
            "native character readback: Flow did not remain on the requested project route",
            route=_ROUTE,
            discovery={
                "format": "native-character-v1",
                "reason": "requested project route did not remain active",
            },
        )
    return payload


async def read_native_characters(
    page: Page,
    project_id: str,
    *,
    timeout_s: float = NATIVE_CHARACTER_READ_TIMEOUT_S,
) -> list[NativeCharacterReadback]:
    """Read all native Characters from the ``Zzl0ze`` reply to a project load.

    The caller owns and retains ``page``. This operation navigates that page but
    performs no write and returns only fields admitted by the pure native parser.
    """
    project_id = _canonical_uuid(project_id, "project id")
    payload = await _read_project_payload(page, project_id, timeout_s=timeout_s)
    return parse_native_characters(payload, project_id)


async def read_verified_native_character(
    page: Page,
    project_id: str,
    entity_id: str,
    *,
    timeout_s: float = NATIVE_CHARACTER_READ_TIMEOUT_S,
) -> NativeCharacterReadback:
    """Read one Character only when its project/workflow/media binding is exact."""
    project_id = _canonical_uuid(project_id, "project id")
    entity_id = _canonical_uuid(entity_id, "entity id")
    payload = await _read_project_payload(page, project_id, timeout_s=timeout_s)
    return parse_verified_native_character(payload, project_id, entity_id)


__all__ = [
    "NATIVE_CHARACTER_READ_TIMEOUT_S",
    "NATIVE_CHARACTER_READY",
    "NATIVE_CHARACTER_RPC",
    "NATIVE_PROJECT_URL",
    "read_native_characters",
    "read_verified_native_character",
]
