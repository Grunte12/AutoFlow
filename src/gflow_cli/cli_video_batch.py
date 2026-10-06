"""Thin CLI adapter for the shared conservative video-batch service."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import click

from gflow_cli import json_output
from gflow_cli._cli_helpers import _make_provider_dir, _resolve_profile, run_with_handlers
from gflow_cli.config import get_settings
from gflow_cli.errors import ConfigurationError
from gflow_cli.services.video_batch import run_video_batch


async def _run_batch(
    manifest: Path,
    *,
    profile: str | None,
    out_dir: Path | None,
    dry_run: bool,
    as_json: bool,
) -> None:
    try:
        raw: Any = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise ConfigurationError(
            "Cannot read UTF-8 JSON video manifest.", route="video.batch"
        ) from None
    profile_name = _resolve_profile(profile)
    result = await run_video_batch(
        raw,
        base_dir=manifest.resolve().parent,
        profile=profile_name,
        profile_dir=_make_provider_dir(profile_name),
        out_dir=out_dir or get_settings().output_dir,
        dry_run=dry_run,
    )
    if as_json:
        json_output.emit(result)
    else:
        click.echo(f"Video batch: {result['status']}; {len(result['completed'])} completed.")
        for file in result["files"]:
            click.echo(file["path"])
        if result.get("catalog_pending") or result["stopped"]:
            click.echo(result["next_action"])
    if result["status"] != "completed":
        raise SystemExit(1)


@click.command("batch")
@click.argument("manifest", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--profile", default=None, help="Profile name (overrides default).")
@click.option("--out-dir", type=click.Path(file_okay=False, path_type=Path), default=None)
@click.option("--dry-run", is_flag=True, help="Validate all local inputs without opening Chrome.")
@click.option("--json", "as_json", is_flag=True, help="Emit the safe structured batch result.")
def batch(
    manifest: Path,
    profile: str | None,
    out_dir: Path | None,
    dry_run: bool,
    as_json: bool,
) -> None:
    """Run 1..4 supplied local-image shots, sequentially in one existing project.

    Resume verifies input/output hashes. Uncertain submission stops the batch and
    cannot be retried automatically. See docs/VIDEO_BATCH.md.
    """
    run_with_handlers(
        lambda: _run_batch(
            manifest, profile=profile, out_dir=out_dir, dry_run=dry_run, as_json=as_json
        ),
        cli_command="video batch",
        as_json=as_json,
    )
