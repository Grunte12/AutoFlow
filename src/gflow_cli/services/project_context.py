"""Opt-in project reuse; local state never authorizes remote cleanup or generation."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from gflow_cli.api.client import FlowApiClient
from gflow_cli.errors import ConfigurationError
from gflow_cli.profile_lease import ProfileLease

_FILENAME = ".gflow_project.json"
_REMEDIATION = "Inspect the project binding with project context, then explicitly bind the project."


class BoundCharacter(BaseModel):
    """Cached identifiers, not a claim that remote Characters cannot change."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    entity_id: UUID
    name: str = Field(min_length=1, max_length=256)


class ProjectBinding(BaseModel):
    """Small versioned profile-local default, reusable by any brand."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    version: Literal[1] = 1
    project: UUID
    characters: tuple[BoundCharacter, ...] = ()


def load_binding(profile_dir: Path) -> ProjectBinding | None:
    """Read without browser activity; invalid state must never create a new project."""
    path = profile_dir / _FILENAME
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise ConfigurationError(
            detail="Cannot read the project binding.", remediation_hint=_REMEDIATION
        ) from exc
    try:
        return ProjectBinding.model_validate_json(raw)
    except (ValidationError, ValueError) as exc:
        raise ConfigurationError(
            detail="Invalid project binding; automatic project creation is blocked.",
            remediation_hint=_REMEDIATION,
        ) from exc


def save_binding(profile_dir: Path, binding: ProjectBinding, *, replace: bool = False) -> None:
    """Atomic write under the existing cross-process profile lease."""
    with ProfileLease(profile_dir):
        existing = load_binding(profile_dir)
        if existing == binding:
            return
        if existing is not None and not replace:
            raise ConfigurationError(
                detail="A different project/Character binding already exists.",
                remediation_hint="Inspect project context; use replace to intentionally switch.",
            )
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=profile_dir, prefix=".gflow_project-", delete=False
            ) as output:
                temporary = Path(output.name)
                output.write(binding.model_dump_json(indent=2) + "\n")
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, profile_dir / _FILENAME)
        except OSError as exc:
            raise ConfigurationError(
                detail="Cannot save the project binding.", remediation_hint=_REMEDIATION
            ) from exc
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)


def resolve_project(profile_dir: Path, project: str | None, project_name: str | None) -> str | None:
    """Explicit ID/title wins; otherwise reuse the bound project (no network calls)."""
    if project is not None or project_name is not None:
        return project
    binding = load_binding(profile_dir)
    return str(binding.project) if binding is not None else None


async def bind_project(
    profile_dir: Path,
    project: str,
    character_names: tuple[str, ...] = (),
    *,
    replace: bool = False,
    headless: bool = True,
) -> ProjectBinding:
    """Verify selected existing Characters in Flow, then persist the local default.

    This reads remote state only. It never creates a project, imports Characters,
    attaches them to a generation, renames anything, or deletes media.
    """
    try:
        project_uuid = UUID(project)
    except ValueError as exc:
        raise ConfigurationError(detail="Project must be a UUID.") from exc
    if len(set(character_names)) != len(character_names) or any(
        not n.strip() for n in character_names
    ):
        raise ConfigurationError(detail="Character names must be nonempty and unique.")
    selected: list[BoundCharacter] = []
    async with FlowApiClient(profile_dir=profile_dir, headless=headless) as client:
        characters = await client.list_characters(str(project_uuid))
        for name in character_names:
            matches = [c for c in characters if c.display_name == name]
            if len(matches) != 1 or not matches[0].workflow_ids:
                raise ConfigurationError(
                    detail="Selected Character is missing, ambiguous, or has no reference image.",
                    remediation_hint="List this project's Characters; select exact unique names.",
                )
            selected.append(BoundCharacter(entity_id=UUID(matches[0].entity_id), name=name))
    binding = ProjectBinding(project=project_uuid, characters=tuple(selected))
    save_binding(profile_dir, binding, replace=replace)
    return binding
