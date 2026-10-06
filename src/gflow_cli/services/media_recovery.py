"""Fetch an already-generated asset by media id and record it locally (#865, #871).

Joins three pieces that already exist: the catalog row an orphaned asset always has,
the per-clip recovery in :mod:`gflow_cli.api.transports.migrated_recover`, and the
``local_files`` write that stops ``gflow data list`` reporting ``copy_count: 0`` for a
file that is now on disk.

Spends no credits — the generation it retrieves has already been billed.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

import structlog

from gflow_cli.config import get_settings
from gflow_cli.data.models import AssetKind, AssetLookup, AssetRecord, LocalFileRecord
from gflow_cli.data.repository import DataRepository
from gflow_cli.data.store import DataStore
from gflow_cli.errors import ConfigurationError, DataStoreError

log = structlog.get_logger(__name__)

_ROUTE = "data.download"
_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


@dataclass(frozen=True)
class DownloadedMedia:
    """Result of a recovery run, for the CLI and the MCP tool to report."""

    media_id: str
    workflow_id: str
    profile_name: str
    project_id: str
    path: Path
    bytes: int


def resolve_asset(media_id: str, *, profile: str | None, route: str) -> AssetLookup:
    """The catalog row for *media_id*, scoped to *profile* when given.

    Shared by ``gflow data media`` and ``gflow data download`` so the two agree on what
    "no such media" and "ambiguous across profiles" mean. ``route`` tags the raised
    :class:`DataStoreError` with the caller's command.
    """
    asset = _find_asset(media_id, profile=profile, route=route)
    if asset is None:
        suffix = f" (profile={profile!r})" if profile is not None else ""
        raise DataStoreError(
            detail=f"No local media record found: {media_id}{suffix}",
            route=route,
        )
    return asset


def _find_asset(media_id: str, *, profile: str | None, route: str) -> AssetLookup | None:
    """Find a scoped asset without turning an ordinary miss into an exception."""
    settings = get_settings()
    with DataStore.open(settings.resolved_db_path()) as store:
        repo = DataRepository(store)
        if profile is not None:
            return repo.get_asset_by_flow_media_id(profile, media_id)

        matches = repo.find_assets_by_flow_media_id(media_id)
        if len(matches) > 1:
            candidates = sorted({f"{m.profile_name} ({m.kind.value})" for m in matches})
            raise DataStoreError(
                detail=(
                    f"Media {media_id!r} exists under multiple profiles: "
                    f"{candidates}. Pass --profile NAME to disambiguate."
                ),
                route=route,
            )
        return matches[0] if matches else None


def _canonical_uuid(value: str, *, label: str) -> str:
    """Accept only a canonical UUID string before interpolating it into a route."""
    if not _UUID_RE.fullmatch(value):
        raise ConfigurationError(
            detail=f"The {label} must be a canonical UUID.",
            remediation_hint=f"Pass the {label} UUID exactly as shown in the Flow URL.",
            route=_ROUTE,
        )
    return str(uuid.UUID(value))


def _require_video(asset: AssetLookup, *, media_id: str) -> None:
    if asset.kind is AssetKind.VIDEO:
        return
    # #877: the signed URL comes from the `as29s` record a clip route emits, which
    # is a video mechanism — an image's route never emits one. Refuse from catalog
    # evidence without opening a browser or attaching an MP4 to an image row.
    raise ConfigurationError(
        detail=(
            f"Media {media_id!r} is {asset.kind.value}, and `gflow data download` "
            "recovers video only. The signed URL it needs comes from the record "
            "Flow emits when a clip's own route loads, and an image's route does "
            "not carry one. Tracking the image path in issue #877."
        ),
        remediation_hint=(
            "Nothing to retry — this is a capability gap, not a fault. Open the "
            "image in Flow and save it from there, or pass a video media id. "
            "`gflow data list images` shows which rows are images."
        ),
        route=_ROUTE,
    )


def record_local_file(asset: AssetLookup, path: Path, size: int) -> None:
    """Write the ``local_files`` row for a recovered asset.

    Without this the file is on disk and the catalog still reports ``copy_count: 0``,
    which is the state that made the orphan invisible in the first place.
    """
    settings = get_settings()
    with DataStore.open(settings.resolved_db_path()) as store:
        DataRepository(store).upsert_local_file(
            LocalFileRecord(
                id=str(uuid.uuid4()),
                profile_name=asset.profile_name,
                asset_id=asset.id,
                path=path,
                media_type="video/mp4",
                bytes=size,
                sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            )
        )


async def download_media(
    *,
    media_id: str,
    profile: str | None,
    out_dir: Path | None,
    project_id: str | None = None,
) -> DownloadedMedia:
    """Recover *media_id* to disk and record it in the catalog.

    Without *project_id*, catalog lookup and ambiguity behavior are unchanged. Supplying
    a project allows recovery of an already-generated clip absent from the local catalog;
    that path must be scoped to *profile* and both route UUIDs are validated before a
    browser is opened. New catalog state is written only after the transport verifies the
    recovered clip.
    """
    from gflow_cli._cli_helpers import _make_provider_dir  # noqa: PLC0415 - import cycle
    from gflow_cli.api.client import FlowApiClient  # noqa: PLC0415 - import cycle
    from gflow_cli.api.transports.migrated_recover import recover_clip  # noqa: PLC0415

    if project_id is None:
        asset = resolve_asset(media_id, profile=profile, route=_ROUTE)
        _require_video(asset, media_id=media_id)
        route_project_id = asset.flow_project_id
        profile_name = asset.profile_name
    else:
        media_id = _canonical_uuid(media_id, label="media id")
        project_id = _canonical_uuid(project_id, label="project id")
        asset = _find_asset(media_id, profile=profile, route=_ROUTE)
        if asset is None:
            if profile is None:
                raise ConfigurationError(
                    detail=(
                        f"Media {media_id!r} is not in the local catalog. "
                        "Pass --profile to scope recovery to the Flow account that owns it."
                    ),
                    remediation_hint=(
                        "Use the profile whose Flow account contains this clip, together "
                        "with --project <UUID>."
                    ),
                    route=_ROUTE,
                )
            route_project_id = project_id
            profile_name = profile
        else:
            _require_video(asset, media_id=media_id)
            if asset.flow_project_id and asset.flow_project_id.lower() != project_id:
                raise DataStoreError(
                    detail=(
                        f"Media {media_id!r} conflicts with the catalog project "
                        f"{asset.flow_project_id!r}; refusing supplied project {project_id!r}."
                    ),
                    route=_ROUTE,
                )
            route_project_id = asset.flow_project_id or project_id
            profile_name = asset.profile_name

    if route_project_id is None:
        raise DataStoreError(
            detail=(
                f"Media {media_id!r} has no project id in the catalog, so its clip route "
                "cannot be built. Re-run `gflow data sync` for the owning project."
            ),
            route=_ROUTE,
        )

    settings = get_settings()
    target_dir = out_dir or settings.output_dir
    profile_dir = _make_provider_dir(profile_name)

    async with FlowApiClient(profile_dir=profile_dir, headless=settings.headless) as client:
        clip = await recover_clip(
            client.page,
            project_id=route_project_id,
            media_id=media_id,
            out_dir=target_dir,
        )

    if asset is None:
        _record_recovered_asset(
            profile=profile_name,
            project_id=route_project_id,
            media_id=media_id,
            workflow_id=clip.workflow_id,
            path=clip.path,
            size=clip.bytes,
        )
    else:
        if asset.flow_project_id is None and project_id is not None:
            _update_asset_project_if_missing(asset, project_id=route_project_id)
        record_local_file(asset, clip.path, clip.bytes)
    log.info(
        "data.download.recovered",
        media_id=media_id,
        profile=profile_name,
        path=str(clip.path),
        bytes=clip.bytes,
    )
    return DownloadedMedia(
        media_id=media_id,
        workflow_id=clip.workflow_id,
        profile_name=profile_name,
        project_id=route_project_id,
        path=clip.path,
        bytes=clip.bytes,
    )


def _record_recovered_asset(
    *, profile: str, project_id: str, media_id: str, workflow_id: str, path: Path, size: int
) -> None:
    """Persist only identifiers observed or supplied for a verified recovered clip."""
    settings = get_settings()
    with DataStore.open(settings.resolved_db_path()) as store:
        repo = DataRepository(store)
        asset = repo.get_asset_by_flow_media_id(profile, media_id)
        if asset is not None:
            with store.transaction(immediate=True):
                current = repo.get_asset_by_flow_media_id(profile, media_id)
                if current is None:
                    raise DataStoreError(
                        detail=f"Recovered media {media_id!r} disappeared from the catalog.",
                        route=_ROUTE,
                    )
                _require_video(current, media_id=media_id)
                _require_matching_project(current, project_id=project_id, media_id=media_id)
                if current.flow_project_id is None:
                    store.conn.execute(
                        "UPDATE assets SET flow_project_id = ? "
                        "WHERE id = ? AND flow_project_id IS NULL",
                        (project_id, current.id),
                    )
                asset = current
        else:
            repo.upsert_asset(
                AssetRecord(
                    id=str(uuid.uuid4()),
                    profile_name=profile,
                    flow_project_id=project_id,
                    flow_media_id=media_id,
                    flow_workflow_id=workflow_id,
                    flow_media_generation_id=None,
                    kind=AssetKind.VIDEO,
                    status="ready",
                    model=None,
                    aspect_ratio=None,
                    width=None,
                    height=None,
                    duration_seconds=None,
                    seed=None,
                    metadata_json={},
                )
            )
            asset = repo.get_asset_by_flow_media_id(profile, media_id)
            if asset is None:  # pragma: no cover - repo just inserted this row
                raise DataStoreError(
                    detail=f"Recovered media {media_id!r} could not be recorded.",
                    route=_ROUTE,
                )
        repo.upsert_local_file(
            LocalFileRecord(
                id=str(uuid.uuid4()),
                profile_name=profile,
                asset_id=asset.id,
                path=path,
                media_type="video/mp4",
                bytes=size,
                sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            )
        )


def _require_matching_project(asset: AssetLookup, *, project_id: str, media_id: str) -> None:
    if asset.flow_project_id is None or asset.flow_project_id.lower() == project_id:
        return
    raise DataStoreError(
        detail=(
            f"Media {media_id!r} conflicts with the catalog project "
            f"{asset.flow_project_id!r}; refusing supplied project {project_id!r}."
        ),
        route=_ROUTE,
    )


def _update_asset_project_if_missing(asset: AssetLookup, *, project_id: str) -> None:
    """Add the supplied locator to an existing asset only after verified recovery."""
    settings = get_settings()
    with DataStore.open(settings.resolved_db_path()) as store:
        repo = DataRepository(store)
        with store.transaction(immediate=True):
            current = repo.get_asset_by_flow_media_id(asset.profile_name, asset.flow_media_id)
            if current is None:
                return
            _require_video(current, media_id=asset.flow_media_id)
            _require_matching_project(current, project_id=project_id, media_id=asset.flow_media_id)
            if current.flow_project_id is not None:
                return
            store.conn.execute(
                "UPDATE assets SET flow_project_id = ? WHERE id = ? AND flow_project_id IS NULL",
                (project_id, current.id),
            )
