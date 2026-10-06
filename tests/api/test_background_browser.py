"""Generation-only background launch policy; login keeps its separate launch."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from gflow_cli.api.client import FlowApiClient
from gflow_cli.api.transports.ui_automation_video import VideoGenerationMixin
from gflow_cli.config import Settings


def test_background_launch_has_no_startup_window(tmp_path: Path) -> None:
    client = FlowApiClient(profile_dir=tmp_path, settings=Settings(browser_background=True))
    kwargs = client._persistent_context_kwargs()
    assert kwargs["ignore_default_args"] is True
    assert "--no-startup-window" in kwargs["args"]
    assert "--remote-debugging-pipe" in kwargs["args"]
    assert f"--user-data-dir={tmp_path}" in kwargs["args"]
    assert "--password-store=basic" in kwargs["args"]
    assert "--no-sandbox" not in kwargs["args"]
    assert not any(a.startswith("--remote-debugging-port") for a in kwargs["args"])
    assert kwargs["headless"] is False


def test_visible_launch_remains_standard(tmp_path: Path) -> None:
    client = FlowApiClient(profile_dir=tmp_path, settings=Settings(browser_background=False))
    kwargs = client._persistent_context_kwargs()
    assert kwargs["ignore_default_args"] == ["--enable-automation", "--no-sandbox"]
    assert "--no-startup-window" not in kwargs["args"]


@pytest.mark.asyncio
async def test_background_poll_never_raises_window() -> None:
    from gflow_cli.background_browser import mark_background_context

    page = MagicMock()
    page.bring_to_front = AsyncMock()
    mark_background_context(page.context)
    result = await VideoGenerationMixin._nudge_tab_if_stalled(page, [], 0, 0, False, 0, "fixture")
    page.bring_to_front.assert_not_awaited()
    assert result[2] is True


@pytest.mark.asyncio
async def test_visible_poll_preserves_legacy_nudge() -> None:
    page = MagicMock()
    page.bring_to_front = AsyncMock()
    await VideoGenerationMixin._nudge_tab_if_stalled(page, [], 0, 0, False, 0, "fixture")
    page.bring_to_front.assert_awaited_once()


@pytest.mark.asyncio
async def test_target_creation_is_subscribed_owned_minimized_and_detached() -> None:
    from gflow_cli.background_browser import is_background_page, new_background_page

    context = MagicMock()
    browser_session = AsyncMock()
    browser_session.send.return_value = {"targetId": "owned"}
    context.browser.new_browser_cdp_session = AsyncMock(return_value=browser_session)
    page = MagicMock(context=context)
    target_session = AsyncMock()
    target_session.send.side_effect = [
        {"targetInfo": {"targetId": "owned"}},
        {"bounds": {"windowState": "minimized"}},
    ]
    context.new_cdp_session = AsyncMock(return_value=target_session)
    event = MagicMock()
    event.value = asyncio.get_running_loop().create_future()
    event.value.set_result(page)
    context.expect_page.return_value.__aenter__.return_value = event
    assert await new_background_page(context) is page
    assert is_background_page(page)
    browser_session.send.assert_awaited_once_with(
        "Target.createTarget",
        {
            "url": "about:blank",
            "background": True,
            "focus": False,
            "newWindow": True,
            "windowState": "minimized",
        },
    )
    browser_session.detach.assert_awaited_once()
    target_session.detach.assert_awaited_once()
    context.new_page.assert_not_called()


@pytest.mark.asyncio
async def test_unsupported_target_never_falls_back_to_visible() -> None:
    from gflow_cli.background_browser import new_background_page
    from gflow_cli.errors import ConfigurationError

    context = MagicMock()
    session = AsyncMock()
    session.send.side_effect = RuntimeError("unsupported; sensitive diagnostic")
    context.browser.new_browser_cdp_session = AsyncMock(return_value=session)
    with pytest.raises(ConfigurationError, match="minimized background") as raised:
        await new_background_page(context)
    assert "sensitive" not in str(raised.value)
    session.detach.assert_awaited_once()
    context.new_page.assert_not_called()


def test_background_refuses_headless_and_other_platforms(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from gflow_cli.background_browser import background_launch_kwargs
    from gflow_cli.errors import ConfigurationError

    monkeypatch.setattr("gflow_cli.background_browser.sys.platform", "darwin")
    with pytest.raises(ConfigurationError, match="headed"):
        background_launch_kwargs({"headless": True}, tmp_path)
    monkeypatch.setattr("gflow_cli.background_browser.sys.platform", "linux")
    with pytest.raises(ConfigurationError, match="macOS-only"):
        background_launch_kwargs({"headless": False}, tmp_path)
