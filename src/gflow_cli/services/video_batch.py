"""Bounded, sequential local-input video batches with fail-closed resume."""

from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import re
import stat
import tempfile
import uuid
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from gflow_cli.api.client import (
    MAX_IMAGE_BYTES,
    FlowApiClient,
    _is_supported_image_header,  # pyright: ignore[reportPrivateUsage]
)
from gflow_cli.api.dto import GenerationCheckpoint
from gflow_cli.api.video import Aspect, GenerateVideoRequest, Mode, VideoModel, is_media_uuid
from gflow_cli.config import get_settings
from gflow_cli.data.models import AssetKind, AssetRecord, LocalFileRecord
from gflow_cli.data.repository import DataRepository
from gflow_cli.data.store import DataStore
from gflow_cli.errors import ConfigurationError
from gflow_cli.profile_lease import (
    _lock_nonblocking,  # pyright: ignore[reportPrivateUsage]
    _unlock,  # pyright: ignore[reportPrivateUsage]
)

if TYPE_CHECKING:
    from gflow_cli.config import Settings

_SETTINGS_KEYS = {"model", "aspect", "duration", "resolution", "seed", "count"}
_SHOT_KEYS = _SETTINGS_KEYS | {
    "id",
    "mode",
    "prompt",
    "prompt_file",
    "start_image",
    "end_image",
    "reference_images",
}
_HELD_LOCKS: set[Path] = set()


@dataclass(frozen=True)
class PreparedShot:
    id: str
    request: GenerateVideoRequest
    identity: dict[str, Any]


@dataclass(frozen=True)
class PreparedVideoBatch:
    project_id: str
    shots: tuple[PreparedShot, ...]


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _file_hash(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _record_completed_asset(
    *,
    settings: Settings,
    profile: str,
    profile_dir: Path,
    media_id: str,
    project_id: str,
    workflow_id: str | None,
    output: Path,
    output_bytes: int,
    output_sha256: str,
) -> None:
    """Record observed asset/file facts without implying operation metadata."""
    store = DataStore.open(settings.resolved_db_path())
    try:
        repo = DataRepository(store)
        repo.upsert_profile(profile, profile_dir)
        existing = repo.get_asset_by_flow_media_id(profile, media_id)
        if existing is None:
            asset_id = str(uuid.uuid4())
            repo.upsert_asset(
                AssetRecord(
                    id=asset_id,
                    profile_name=profile,
                    flow_project_id=project_id,
                    flow_media_id=media_id,
                    flow_workflow_id=workflow_id,
                    flow_media_generation_id=None,
                    kind=AssetKind.VIDEO,
                    status="MEDIA_GENERATION_STATUS_SUCCESSFUL",
                    model=None,
                    aspect_ratio=None,
                    width=None,
                    height=None,
                    duration_seconds=None,
                    seed=None,
                    metadata_json={},
                ),
            )
        else:
            if existing.kind is not AssetKind.VIDEO:
                raise ValueError("media id is already cataloged as a non-video asset")
            if existing.flow_project_id not in (None, project_id):
                raise ValueError("media id is already cataloged under another project")
            if workflow_id is not None and existing.flow_workflow_id not in (None, workflow_id):
                raise ValueError("media id is already cataloged with another workflow")
            asset_id = existing.id
            store.conn.execute(
                "UPDATE assets SET flow_project_id = COALESCE(flow_project_id, ?), "
                "flow_workflow_id = COALESCE(flow_workflow_id, ?) WHERE id = ?",
                (project_id, workflow_id, asset_id),
            )
        repo.upsert_local_file(
            LocalFileRecord(
                id=str(uuid.uuid4()),
                profile_name=profile,
                asset_id=asset_id,
                path=output,
                media_type=mimetypes.guess_type(output.name)[0],
                bytes=output_bytes,
                sha256=output_sha256,
            ),
        )
    finally:
        store.close()


def _local_file(value: Any, base_dir: Path) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("local inputs must be nonempty path strings")
    path = Path(value).expanduser()
    resolved = (path if path.is_absolute() else base_dir / path).resolve(strict=True)
    if not resolved.is_file():
        raise ValueError("local input is not a regular file")
    return resolved


def _image(value: Any, base_dir: Path) -> Path:
    path = _local_file(value, base_dir)
    if path.stat().st_size > MAX_IMAGE_BYTES:
        raise ValueError("image exceeds upload size limit")
    with path.open("rb") as stream:
        if not _is_supported_image_header(stream.read(12)):
            raise ValueError("not a supported image")
    return path


def prepare_video_batch(manifest: Any, base_dir: Path) -> PreparedVideoBatch:
    """Validate ALL rows before browser work. Never rewrite prompts or invent inputs."""
    try:
        if not isinstance(manifest, dict):
            raise ValueError("manifest must be an object")
        manifest = cast("dict[str, Any]", manifest)
        if set(manifest) - {"project_id", "defaults", "shots"}:
            raise ValueError("manifest accepts project_id, defaults, shots only")
        project_id = manifest.get("project_id")
        if not isinstance(project_id, str) or not is_media_uuid(project_id):
            raise ValueError("explicit existing project_id UUID is required")
        defaults = manifest.get("defaults", {})
        if not isinstance(defaults, dict):
            raise ValueError("defaults must be an object")
        defaults = cast("dict[str, Any]", defaults)
        if set(defaults) - _SETTINGS_KEYS:
            raise ValueError("invalid defaults keys")
        rows = manifest.get("shots")
        if not isinstance(rows, list):
            raise ValueError("shots must be a list")
        rows = cast("list[Any]", rows)
        if not 1 <= len(rows) <= 4:
            raise ValueError("shots must contain 1..4 rows")
        shots: list[PreparedShot] = []
        seen: set[str] = set()
        for index, raw in enumerate(rows):
            if not isinstance(raw, dict):
                raise ValueError(f"shots[{index}] contains unsupported keys")
            row = cast("dict[str, Any]", raw)
            if set(row) - _SHOT_KEYS:
                raise ValueError(f"shots[{index}] contains unsupported keys")
            shot_id = row.get("id")
            if not isinstance(shot_id, str) or not re.fullmatch(
                r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", shot_id
            ):
                raise ValueError(f"shots[{index}] requires a safe id (1..64 characters)")
            if shot_id in seen:
                raise ValueError("shot ids must be unique")
            seen.add(shot_id)
            if ("prompt" in row) == ("prompt_file" in row):
                raise ValueError(f"shots[{index}] requires prompt XOR prompt_file")
            prompt = row.get("prompt")
            if "prompt_file" in row:
                prompt = _local_file(row["prompt_file"], base_dir).read_text(encoding="utf-8")
            if not isinstance(prompt, str) or not prompt.strip():
                raise ValueError(f"shots[{index}] prompt must be nonempty UTF-8 text")
            prompt.encode("utf-8")
            mode = Mode(row.get("mode"))
            if mode not in (Mode.I2V, Mode.R2V):
                raise ValueError("batch supports supplied local i2v/r2v inputs only")
            values = {**defaults, **{k: v for k, v in row.items() if k in _SETTINGS_KEYS}}
            for key in ("count", "duration", "seed"):
                if key in values and values[key] is not None and type(values[key]) is not int:
                    raise ValueError(f"{key} must be an integer")
            if values.get("count", 1) != 1:
                raise ValueError("batch count must be 1")
            refs = row.get("reference_images", [])
            if not isinstance(refs, list):
                raise ValueError("reference_images must be a list of local paths")
            start = _image(row["start_image"], base_dir) if "start_image" in row else None
            end = _image(row["end_image"], base_dir) if "end_image" in row else None
            images = tuple(_image(v, base_dir) for v in cast("list[Any]", refs))
            model = values.get("model")
            if model is not None and not isinstance(model, str):
                raise ValueError("model must be a string")
            request = GenerateVideoRequest(
                prompt=prompt,
                mode=mode,
                start_image=start,
                end_image=end,
                reference_images=images,
                model=VideoModel.from_cli(model),
                aspect=Aspect.from_cli(values.get("aspect", "16:9")),
                count=1,
                duration=values.get("duration"),
                resolution=values.get("resolution"),
                seed=values.get("seed"),
            )
            identity = asdict(request)
            # Paths are not semantic input identity: equivalent owner-staged files
            # should resume. Full content hashes ARE identity, in reference order.
            identity["start_image"] = _file_hash(start) if start else None
            identity["end_image"] = _file_hash(end) if end else None
            identity["reference_images"] = [_file_hash(p) for p in images]
            shots.append(PreparedShot(shot_id, request, identity))
        return PreparedVideoBatch(project_id, tuple(shots))
    except (OSError, ValueError, TypeError) as exc:
        # Never echo input values or parser source text (which may contain prompts).
        raise ConfigurationError(
            detail=f"Video batch preflight rejected input ({type(exc).__name__}). "
            "Check project UUID, unique ids, local image files, prompt exclusivity and settings.",
            route="video.batch",
        ) from None


@contextmanager
def _ledger_lock(path: Path) -> Generator[None]:
    lock = path.with_suffix(path.suffix + ".lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    if lock in _HELD_LOCKS:
        raise ConfigurationError("Video batch ledger is already in use.", route="video.batch")

    # Inspect before opening so FIFOs and other special files are rejected
    # without risking a blocking open. O_NONBLOCK closes the race on platforms
    # that support it; O_NOFOLLOW prevents the final path component from
    # changing into a symlink between inspection and open.
    try:
        existing = lock.lstat()
    except FileNotFoundError:
        existing = None
    except OSError:
        raise ConfigurationError(
            "Video batch ledger lock cannot be inspected safely.", route="video.batch"
        ) from None
    if existing is not None and not stat.S_ISREG(existing.st_mode):
        raise ConfigurationError(
            "Video batch ledger lock must be a regular non-symlink file.",
            route="video.batch",
        )

    flags = os.O_CREAT | os.O_RDWR
    flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        fd = os.open(lock, flags, 0o600)
    except OSError:
        raise ConfigurationError(
            "Video batch ledger lock cannot be opened safely.", route="video.batch"
        ) from None
    try:
        try:
            descriptor_stat = os.fstat(fd)
            current = lock.lstat()
        except OSError:
            raise ConfigurationError(
                "Video batch ledger lock changed while opening.", route="video.batch"
            ) from None
        if (
            not stat.S_ISREG(descriptor_stat.st_mode)
            or descriptor_stat.st_nlink != 1
            or not stat.S_ISREG(current.st_mode)
            or not os.path.samestat(descriptor_stat, current)
        ):
            raise ConfigurationError(
                "Video batch ledger lock must be a regular non-symlink file.",
                route="video.batch",
            )
        if os.fstat(fd).st_size == 0:
            os.write(fd, b"\0")
        try:
            _lock_nonblocking(fd)
        except OSError:
            raise ConfigurationError(
                "Video batch ledger is already in use.", route="video.batch"
            ) from None
        _HELD_LOCKS.add(lock)
        try:
            yield
        finally:
            _HELD_LOCKS.remove(lock)
            _unlock(fd)
    finally:
        os.close(fd)


def _save_ledger(path: Path, ledger: dict[str, Any]) -> None:
    """Durable replacement, restrictive permissions, no best-effort checkpoint writes."""
    fd, temporary = tempfile.mkstemp(prefix=".video-batch-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(ledger, stream, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        if os.name != "nt":
            directory = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _result(ledger: dict[str, Any], *, dry_run: bool = False) -> dict[str, Any]:
    rows = cast("list[dict[str, Any]]", ledger["shots"])
    complete = [row for row in rows if row["state"] == "completed"]
    catalog_pending = [row["id"] for row in complete if not row.get("catalog_recorded", False)]
    stopped = next((row for row in rows if row["state"] not in ("completed", "not_started")), None)
    status = "completed" if len(complete) == len(rows) or dry_run else "failed"
    if stopped:
        status = (
            "indeterminate"
            if stopped["state"] != "failed"
            else ("partial" if complete else "failed")
        )
    return {
        "status": status,
        "dry_run": dry_run,
        "project_id": ledger["project_id"],
        "completed": [row["id"] for row in complete],
        "files": [row["file"] for row in complete],
        "catalog_pending": catalog_pending,
        "not_started": [row["id"] for row in rows if row["state"] == "not_started"],
        "stopped": (
            {
                "shot_id": stopped["id"],
                "state": stopped["state"],
                "reason": stopped.get("reason", "Previous call did not finish safely."),
                "media_ids": stopped.get("media_ids", []),
                "operation_id": stopped.get("operation_id"),
                "workflow_ids": stopped.get("workflow_ids", []),
            }
            if stopped
            else None
        ),
        "next_action": (
            "Dry run made no catalog changes. A normal run will reconcile completed outputs "
            "without regenerating them; not-started shots may still submit."
            if catalog_pending and dry_run
            else "Retry this command to reconcile local catalog records; completed outputs "
            "remain saved and will not be regenerated."
            if catalog_pending
            else "Inspect the existing Flow project and recover by recorded media id; "
            "do not resubmit or delete the ledger."
            if stopped
            else "Preflight passed; run without dry_run to submit."
            if dry_run
            else "None."
            if status == "completed"
            else "Browser setup failed before submission."
        ),
        "credits": None,
        "credits_before": None,
        "credits_after": None,
        "credits_charged": None,
        "credits_reason": "Not measured; count-one requests may spend account credits.",
    }


def _load_ledger(path: Path, initial: dict[str, Any], *, out_dir: Path) -> dict[str, Any]:
    if not path.exists():
        return initial
    try:
        raw: Any = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("invalid ledger")
        ledger = cast("dict[str, Any]", raw)
        if ledger.get("fingerprint") != initial["fingerprint"]:
            raise ValueError("input fingerprint changed")
        if ledger.get("version") != 1 or not isinstance(ledger.get("shots"), list):
            raise ValueError("invalid ledger")
        if [r["id"] for r in ledger["shots"]] != [r["id"] for r in initial["shots"]]:
            raise ValueError("invalid ledger shots")
        for row in ledger["shots"]:
            if row["state"] not in {
                "not_started",
                "call_pending",
                "submit_attempted",
                "remote_started",
                "indeterminate",
                "failed",
                "completed",
            }:
                raise ValueError("invalid ledger state")
            if row["state"] == "completed":
                file = row["file"]
                output = Path(file["path"]).resolve(strict=True)
                if not output.is_relative_to(out_dir.resolve()) or not output.is_file():
                    raise ValueError("completed output is outside the batch output directory")
                if _file_hash(output) != file["sha256"]:
                    raise ValueError("completed output hash mismatch")
        return ledger
    except (OSError, ValueError, TypeError, KeyError):
        raise ConfigurationError(
            "Resume rejected: changed inputs, invalid ledger, or missing/changed output. "
            "Do not regenerate; inspect the ledger and recover existing media.",
            route="video.batch",
        ) from None


def _reconcile_catalog(
    *,
    path: Path,
    ledger: dict[str, Any],
    profile: str,
    profile_dir: Path,
    settings: Settings,
) -> bool:
    """Repair completed asset/file rows without launching Flow or spending credits."""
    rows = cast("list[dict[str, Any]]", ledger["shots"])
    for row in rows:
        if row["state"] != "completed" or row.get("catalog_recorded", False):
            continue
        file = cast("dict[str, Any]", row["file"])
        output = Path(file["path"]).resolve(strict=True)
        try:
            _record_completed_asset(
                settings=settings,
                profile=profile,
                profile_dir=profile_dir,
                media_id=str(file["media_id"]),
                project_id=str(file["project_id"]),
                workflow_id=(
                    file["workflow_id"] if isinstance(file.get("workflow_id"), str) else None
                ),
                output=output,
                output_bytes=int(file["bytes"]),
                output_sha256=str(file["sha256"]),
            )
        except Exception:
            row["catalog_recorded"] = False
            return False
        row["catalog_recorded"] = True
        _save_ledger(path, ledger)
    return True


async def run_video_batch(
    manifest: dict[str, Any],
    *,
    base_dir: Path,
    profile: str,
    profile_dir: Path,
    out_dir: Path,
    state_path: Path | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Use one client/project, sequentially; any uncertain call permanently blocks resume."""
    prepared = prepare_video_batch(manifest, base_dir)
    settings: Settings = get_settings()
    settings_dump = cast(Any, settings).model_dump(mode="json")
    identity: dict[str, Any] = {
        "profile": profile,
        "profile_dir": str(profile_dir.resolve()),
        "project_id": prepared.project_id,
        "out_dir": str(out_dir.resolve()),
        "settings": settings_dump,
        "shots": [{"id": shot.id, **shot.identity} for shot in prepared.shots],
    }
    initial: dict[str, Any] = {
        "version": 1,
        "project_id": prepared.project_id,
        "fingerprint": _digest(json.dumps(identity, sort_keys=True).encode("utf-8")),
        "shots": [
            {"id": shot.id, "state": "not_started", "catalog_recorded": False}
            for shot in prepared.shots
        ],
    }
    path = (state_path or out_dir / "video-batch-state.json").resolve()
    if dry_run:
        return _result(_load_ledger(path, initial, out_dir=out_dir), dry_run=True)
    with _ledger_lock(path):
        ledger = _load_ledger(path, initial, out_dir=out_dir)
        rows = cast("list[dict[str, Any]]", ledger["shots"])
        if not _reconcile_catalog(
            path=path,
            ledger=ledger,
            profile=profile,
            profile_dir=profile_dir,
            settings=settings,
        ):
            return _result(ledger)
        if all(row["state"] == "completed" for row in rows) or any(
            row["state"] not in ("completed", "not_started") for row in rows
        ):
            return _result(ledger)
        _save_ledger(path, ledger)  # Intent durable before browser launch.
        out_dir.mkdir(parents=True, exist_ok=True)
        async with FlowApiClient(
            profile_dir=profile_dir, out_dir=out_dir, settings=settings
        ) as client:
            for shot, row in zip(prepared.shots, rows, strict=True):
                if row["state"] == "completed":
                    continue
                row["state"] = "call_pending"
                _save_ledger(path, ledger)  # Crash in/around the call cannot invite retry.

                def checkpoint(
                    cp: GenerationCheckpoint,
                    current: dict[str, Any] = row,
                ) -> None:
                    current["state"] = cp.phase
                    current["media_ids"] = list(cp.media_ids)
                    current["operation_id"] = cp.operation_id
                    current["workflow_ids"] = list(cp.workflow_ids)
                    _save_ledger(path, ledger)  # Failure propagates; never swallow it.

                try:
                    result = await client.generate_video(
                        req=shot.request,
                        project_id=prepared.project_id,
                        out_dir=out_dir / shot.id,
                        on_checkpoint=checkpoint,
                    )
                    if not result.status.is_terminal:
                        raise ValueError("nonterminal result")
                    if not result.status.succeeded:
                        row.update(state="failed", reason="Flow returned a terminal failed result.")
                    else:
                        if result.project_id != prepared.project_id or result.local_path is None:
                            raise ValueError("missing output or mismatched project")
                        output = result.local_path.resolve(strict=True)
                        if not output.is_relative_to(out_dir.resolve()) or not output.is_file():
                            raise ValueError("unexpected output location")
                        row["file"] = {
                            "shot_id": shot.id,
                            "path": str(output),
                            "sha256": _file_hash(output),
                            "bytes": output.stat().st_size,
                            "media_id": result.status.media_id,
                            "workflow_id": result.workflow_id,
                            "project_id": result.project_id,
                        }
                        row["state"] = "completed"
                except Exception as exc:
                    row.update(
                        state="indeterminate",
                        reason=f"Call stopped ({type(exc).__name__}); remote outcome uncertain.",
                    )
                    _save_ledger(path, ledger)
                    break
                _save_ledger(path, ledger)
                if row["state"] != "completed":
                    break
                if not _reconcile_catalog(
                    path=path,
                    ledger=ledger,
                    profile=profile,
                    profile_dir=profile_dir,
                    settings=settings,
                ):
                    break
        return _result(ledger)
