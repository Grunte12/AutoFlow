"""macOS generation windows on Playwright's private pipe, not a CDP attach transport.

Login is deliberately outside this policy. Unsupported Chrome versions fail
closed: a requested background run must never fall back to a visible window.
"""

from __future__ import annotations

import asyncio
import sys
from typing import TYPE_CHECKING, Any, cast
from weakref import WeakSet

from gflow_cli.errors import ConfigurationError

if TYPE_CHECKING:
    from pathlib import Path

    from playwright.async_api import BrowserContext, Page

_BACKGROUND_CONTEXTS: WeakSet[Any] = WeakSet()
_SETUP_TIMEOUT_S = 8
_REMEDIATION = (
    "Background browser setup failed before submission. Use a current Google Chrome "
    "on macOS, or explicitly set GFLOW_CLI_BROWSER_BACKGROUND=false to watch a run. "
    "For login/consent, use gflow auth login; its window stays visible. "
    "Do not retry an already-submitted generation."
)


def background_launch_kwargs(kwargs: dict[str, Any], profile_dir: Path) -> dict[str, Any]:
    """Suppress Playwright's initial foreground page without exposing a debug port.

    Persistent launch normally waits for an initial page; ignore_default_args=True
    skips that wait. Supply the profile and private pipe explicitly, keep Chromium's
    sandbox ON, and retain only the reviewed runtime flags needed for this mode.
    No driver monkey-patch or user Chrome attachment is involved.
    """
    if sys.platform != "darwin":
        raise ConfigurationError(
            detail="Background browser mode is currently macOS-only.", remediation_hint=_REMEDIATION
        )
    if kwargs.get("headless"):
        raise ConfigurationError(
            detail="Background browser mode requires headed Chrome.", remediation_hint=_REMEDIATION
        )
    result = dict(kwargs)
    args = [a for a in kwargs.get("args", []) if not a.startswith("--window-position=")]
    result.update(
        ignore_default_args=True,
        args=[
            *args,
            f"--user-data-dir={profile_dir}",
            "--remote-debugging-pipe",
            "--no-startup-window",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-background-networking",
            "--disable-default-apps",
            "--disable-extensions",
            "--disable-sync",
            "--disable-popup-blocking",
            "--disable-background-timer-throttling",
            "--disable-backgrounding-occluded-windows",
            "--disable-renderer-backgrounding",
            "--use-mock-keychain",
        ],
    )
    return result


def mark_background_context(context: BrowserContext) -> None:
    """Ephemeral, weak ownership marker: never persist state into the profile."""
    _BACKGROUND_CONTEXTS.add(context)


def is_background_page(page: Page) -> bool:
    return page.context in _BACKGROUND_CONTEXTS


async def new_background_page(context: BrowserContext) -> Page:
    """Create an owned ordinary Page already minimized, without activating Chrome."""
    browser = context.browser
    if browser is None:
        raise ConfigurationError(
            detail="Background browser has no owned browser.", remediation_hint=_REMEDIATION
        )
    session = None
    target_session = None
    try:
        async with asyncio.timeout(_SETUP_TIMEOUT_S):
            session = cast(Any, await browser.new_browser_cdp_session())
            # Register before creating the target; don't race a pages snapshot.
            async with context.expect_page(timeout=_SETUP_TIMEOUT_S * 1000) as event:
                target = await session.send(
                    "Target.createTarget",
                    {
                        "url": "about:blank",
                        "background": True,
                        "focus": False,
                        "newWindow": True,
                        "windowState": "minimized",
                    },
                )
            page = await event.value
            target_session = cast(Any, await context.new_cdp_session(page))
            info = await target_session.send("Target.getTargetInfo")
            if info["targetInfo"]["targetId"] != target["targetId"]:
                raise RuntimeError("background_target_not_owned_or_minimized")
            # Chrome on macOS can ignore createTarget's initial windowState.
            # Apply bounds on this exact owned window, never on the Chrome app.
            bounds = await target_session.send("Browser.getWindowForTarget")
            if bounds["bounds"]["windowState"] != "minimized":
                await target_session.send(
                    "Browser.setWindowBounds",
                    {"windowId": bounds["windowId"], "bounds": {"windowState": "minimized"}},
                )
            while bounds["bounds"]["windowState"] != "minimized":
                await asyncio.sleep(0.05)
                bounds = await target_session.send("Browser.getWindowForTarget")
            mark_background_context(context)
            return page
    except Exception as exc:
        # No exception text: CDP/browser failures can contain profile details.
        raise ConfigurationError(
            detail="Could not create a minimized background browser page.",
            remediation_hint=_REMEDIATION,
        ) from exc
    finally:
        for attached in (target_session, session):
            if attached is not None:
                try:
                    await asyncio.wait_for(attached.detach(), timeout=1)
                except Exception:  # noqa: BLE001 — owner closes the context on failure
                    pass
