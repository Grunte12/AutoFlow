"""Real Flow refusal regression, navigation only, generation RPCs blocked."""

from __future__ import annotations

import asyncio
import base64
import os
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

import pytest
from playwright.async_api import Route
from pytest_bdd import given, scenarios, then, when

from gflow_cli.api.client import FlowApiClient
from gflow_cli.api.video import Aspect, GenerateVideoRequest, Mode, VideoModel, is_media_uuid
from gflow_cli.config import reset_settings
from gflow_cli.errors import PreSubmitConfigurationError, ProblemDetails

scenarios("../features/presubmit_r2v_live.feature")

_BLOCKED_MEDIA_RPCS: frozenset[str] = frozenset(
    {"YhhmEf", "eb1hJf", "nprQif", "MZZa6b", "ogiZ0b", "maseQ"}
)
_REFERENCE_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVR4"
    "2mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


@given("an explicitly configured owned Flow profile and project", target_fixture="binding")
def binding(monkeypatch: pytest.MonkeyPatch) -> tuple[Path, str]:
    profile = os.environ.get("AUTOFLOW_E2E_PROFILE_DIR")
    project = os.environ.get("AUTOFLOW_E2E_PROJECT")
    if not profile or not project:
        pytest.skip("Set explicit AUTOFLOW_E2E_PROFILE_DIR and AUTOFLOW_E2E_PROJECT")
    path = Path(profile)
    assert path.is_absolute() and path.is_dir() and is_media_uuid(project)
    monkeypatch.setenv("GFLOW_CLI_HOME", str(path.parent))
    monkeypatch.setenv("GFLOW_CLI_FLOW_HOST", "flow.google.com")
    monkeypatch.setenv("GFLOW_CLI_LEASE_WAIT_SECONDS", "0")
    reset_settings()
    return path, project


@when("the real client receives a 10s Omni reference video request", target_fixture="result")
def run_request(binding: tuple[Path, str], tmp_path: Path) -> tuple[ProblemDetails, list[str]]:
    async def run() -> tuple[ProblemDetails, list[str]]:
        path, project = binding
        requests: list[str] = []
        reference = tmp_path / "reference.png"
        reference.write_bytes(_REFERENCE_PNG)
        request = GenerateVideoRequest(
            prompt="Pre-submit regression; must not generate.",
            mode=Mode.R2V,
            aspect=Aspect.PORTRAIT,
            model=VideoModel.OMNI_FLASH,
            duration=10,
            reference_images=(reference,),
        )
        async with FlowApiClient(profile_dir=path, headless=False) as client:
            context = client._context  # noqa: SLF001 - observe owned live entry point
            assert context is not None

            async def boundary(route: Route) -> None:
                url = urlsplit(route.request.url)
                requested_rpcs = {
                    rpc
                    for value in parse_qs(url.query).get("rpcids", [])
                    for rpc in value.split(",")
                }
                # nprQif travels in f.req rather than the rpcids query parameter.
                request_body = unquote(route.request.post_data or "")
                if (
                    any(rpc in requested_rpcs or rpc in request_body for rpc in _BLOCKED_MEDIA_RPCS)
                    or "batchGenerate" in url.path
                    or "batchAsyncGenerate" in url.path
                ):
                    requests.append("unexpected_media_dispatch")
                    await route.abort()
                    return
                await route.continue_()

            await context.route("**/*", boundary)
            with pytest.raises(PreSubmitConfigurationError) as caught:
                await client.generate_video(req=request, project_id=project, download=False)
            return caught.value.to_problem_details(), requests

    return asyncio.run(run())


@then("it returns positive pre-submit configuration proof")
def proof(result: tuple[ProblemDetails, list[str]]) -> None:
    assert result[0]["submission_state"] == "not_submitted"
    assert result[0]["requested_value"] == 10
    assert result[0]["capability"] == "unverified"


@then("no upload or generation request was dispatched")
def no_dispatch(result: tuple[ProblemDetails, list[str]]) -> None:
    assert result[1] == []
