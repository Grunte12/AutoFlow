"""A guard refusal is positive proof; generic transport errors are not."""

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from gflow_cli.api.transports.migrated_composer import MigratedComposer
from gflow_cli.api.video import Aspect, GenerateVideoRequest, Mode, VideoModel
from gflow_cli.errors import PreSubmitConfigurationError

ENTITY_IDS = (
    "a0000000-0000-4000-8000-000000000101",
    "a0000000-0000-4000-8000-000000000102",
)
ENTITY_NAMES = ("Momo", "Nori")


@pytest.mark.anyio
@pytest.mark.parametrize("duration", [4, 6, 10])
async def test_r2v_duration_refusal_precedes_any_settings_or_submit(duration: int) -> None:
    composer = MigratedComposer()
    composer._open_pane = AsyncMock(side_effect=AssertionError("must not open settings"))
    request = GenerateVideoRequest(
        prompt="private script must never appear in proof",
        mode=Mode.R2V,
        aspect=Aspect.PORTRAIT,
        duration=duration,
        reference_images=(Path("sheet.png"),),
    )
    with pytest.raises(PreSubmitConfigurationError) as caught:
        await composer.apply_video_settings(AsyncMock(), request)
    proof = caught.value.to_problem_details()
    assert proof["submission_state"] == "not_submitted"
    assert proof["requested_value"] == duration
    assert proof["capability"] == "unverified"
    assert proof["safe_next_action"] == "inspect_controls"
    assert "private script" not in str(proof)
    assert "only at" not in str(proof)
    assert "labs.google" not in proof["remediation_hint"]
    composer._open_pane.assert_not_awaited()


@pytest.mark.anyio
@pytest.mark.parametrize("mode,duration", [(Mode.R2V, 8), (Mode.R2V, None), (Mode.I2V, 10)])
async def test_guard_leaves_existing_supported_paths_unchanged(
    mode: Mode, duration: int | None
) -> None:
    composer = MigratedComposer()
    composer._open_pane = AsyncMock(side_effect=RuntimeError("test reached settings"))
    request = GenerateVideoRequest(
        prompt="x",
        mode=mode,
        aspect=Aspect.PORTRAIT,
        duration=duration,
        reference_images=(Path("sheet.png"),) if mode is Mode.R2V else (),
        start_image=Path("first.png") if mode is Mode.I2V else None,
        model=VideoModel.OMNI_FLASH if duration == 10 else None,
    )
    with pytest.raises(RuntimeError, match="test reached settings"):
        await composer.apply_video_settings(AsyncMock(), request)


@pytest.mark.anyio
async def test_explicit_omni_flash_r2v_at_10s_with_mixed_refs_reaches_settings() -> None:
    composer = MigratedComposer()
    composer._open_pane = AsyncMock(side_effect=RuntimeError("test reached settings"))
    request = GenerateVideoRequest(
        prompt="x",
        mode=Mode.R2V,
        aspect=Aspect.PORTRAIT,
        duration=10,
        model=VideoModel.OMNI_FLASH,
        reference_images=(Path("reference-one.png"), Path("reference-two.png")),
        reference_entities=ENTITY_IDS,
        reference_entity_names=ENTITY_NAMES,
    )

    with pytest.raises(RuntimeError, match="test reached settings"):
        await composer.apply_video_settings(AsyncMock(), request)

    composer._open_pane.assert_awaited_once()


@pytest.mark.anyio
@pytest.mark.parametrize("duration", [4, 6])
async def test_omni_flash_r2v_below_10s_stays_refused(duration: int) -> None:
    composer = MigratedComposer()
    composer._open_pane = AsyncMock(side_effect=AssertionError("must not open settings"))
    request = GenerateVideoRequest(
        prompt="x",
        mode=Mode.R2V,
        aspect=Aspect.PORTRAIT,
        duration=duration,
        model=VideoModel.OMNI_FLASH,
        reference_images=(Path("reference.png"),),
    )

    with pytest.raises(PreSubmitConfigurationError) as caught:
        await composer.apply_video_settings(AsyncMock(), request)

    assert caught.value.to_problem_details()["requested_value"] == duration
    composer._open_pane.assert_not_awaited()
