# SPDX-License-Identifier: MIT
"""MCP resources — static and dynamic documentation endpoints.

Resources provide read-only reference material that AI agents can
consult before making tool calls. This prevents hallucinated CLI
scripting and guides agents toward the proper tool-based interface.
"""

from __future__ import annotations

import re
from pathlib import Path

import structlog

from gflow_cli.mcp.server import server

log = structlog.get_logger()

# ---------------------------------------------------------------------------
# Static resources
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[3]  # src/gflow_cli/mcp → repo root


@server.resource(
    uri="gflow://docs/mcp-guide",
    name="MCP Agent Guide",
    description=(
        "AutoFlow workflow reference for project reuse, Character images and video inputs. "
        "Read when needed; already exposed tool schemas can be used directly."
    ),
)
async def mcp_guide() -> str:
    """Return the MCP agent guide.

    Truth rule (#495, extended by the wave's post-merge review): the guide may
    only name tools that are actually registered — so under no-spend mode the
    generate-tool sections are replaced by an explanation instead of steering
    agents into unknown-tool protocol errors.
    """
    from gflow_cli.mcp.server import no_spend_active

    if no_spend_active():
        return """\
# AutoFlow MCP Agent Guide (no-spend mode)

This server runs in NO-SPEND mode: the credit-spending generate tools
(`gflow_generate_image`, `gflow_generate_video`) are NOT registered and any
call to them fails as an unknown tool. Do not attempt generation; tell the
user to restart the server without --no-spend / GFLOW_MCP_NO_SPEND to enable
it.

Available tools:

### gflow_auth_status
Credit-free, non-interactive Flow session probe.

### gflow_list_projects
Browse the local project catalog.

### gflow_list_tools
List available gflow prompt tools (name, title, description, category).

## Important Rules
1. **Use tools, not shell commands.** Do NOT run `gflow ...` via the terminal.
2. **Generation is disabled here by operator choice.** Do not work around it.
"""
    return """\
# AutoFlow MCP Agent Guide

Use tools, not shell commands, when operating through MCP.
Use an exposed tool and its current schema directly. With deferred tools or a
hub, discover only the needed capability, inspect once, and reuse while valid.
Refresh when the server/schema changes or a tool is missing. Native names below
retain gflow_ for compatibility; use the hub's published aliases when applicable.
gflow_list_tools lists prompt-rewriting presets, NOT MCP capabilities.

## Project and Character setup

- gflow_project_context reads a cached project/Character binding. Reuse the known
  project; gflow_list_projects is local history, not a complete Flow inventory.
- gflow_character_list and gflow_character_show inspect saved Characters in a
  project. Verify exact IDs and actual reference images, not just display names.
- gflow_project_bind remembers a selected project and character_names. Binding
  alone does not attach Characters to every generation.
- gflow_character_update_images replaces supplied portrait_path/full_body_path
  slots. Use project, entity_id and a UUID operation_id. Omitted slots and metadata
  stay unchanged. Replay only identical inputs under the same operation_id;
  inspect partial/uncertain outcomes before another upload.

Use one close-up and one full-body image when that is the chosen reference setup.
Keep their identity, age, markings and accessories consistent. Inspect the actual
saved images after updates. Character info holds stable traits; put important
scene directions in the video prompt too. Image weights and likeness guarantees
are not established by a successful upload or entity binding.

## Generation

- gflow_auth_status checks the session before generation; login is CLI-only.
- gflow_generate_image generates images; select model/settings from its schema.
- gflow_generate_video: i2v requires initial_frame. R2V can use reference_images
  or saved reference_entities. On flow.google.com, the saved-Character path uses
  mode=r2v, count=1, project, and positionally paired reference_entity_names.
  @Name resolves a saved Character; local reference_images are separate inputs.
  State each reference's role, the scene goal and exact dialogue. A filename is
  not an identity binding. Native inline chip position is not preserved by the
  current AutoFlow prompt resolver/composer.

Use wait=true for a normal single job. wait=false returns a queued receipt, not
a finished clip; use the host's supported task mechanism, not an invented poll
tool. Recover an existing download with gflow_download_media and known media_id.
Honor the user's existing credit authorization and scope; do not ask again for
the same authorized action. Costs vary with the selected operation/model. Never
resubmit an uncertain generation just because its response/download was delayed.
Inspect output against the references and report observed quality separately
from successful tool execution. The optional autoflow-mcp skill adds examples.
"""


# #501: KNOWN_ISSUES.md is ~70 KB and grows every release — an unbounded
# read_text() injected all of it into the agent's context on every fetch.
# The default read is a small index; one templated fetch serves a section.

_SECTION_CAP_BYTES = 16 * 1024


def _slugify(title: str) -> str:
    return re.sub(r"-{2,}", "-", re.sub(r"[^a-z0-9]+", "-", title.lower())).strip("-")


def _iter_issue_sections(text: str) -> list[tuple[str, str, str]]:
    """Return (slug, title, body) for every ``### `` heading in the doc."""
    sections: list[tuple[str, str, str]] = []
    parts = re.split(r"^### (.+)$", text, flags=re.MULTILINE)
    # parts = [preamble, title1, body1, title2, body2, ...]
    for i in range(1, len(parts) - 1, 2):
        title = parts[i].strip()
        sections.append((_slugify(title), title, parts[i + 1]))
    return sections


def _build_known_issues_index(text: str) -> str:
    lines = [
        "# Known issues — index",
        "",
        "Full text of one issue: read `gflow://docs/known-issues/<slug>`.",
        "",
    ]
    for slug, title, body in _iter_issue_sections(text):
        status = ""
        # Match both '**Status:** Open' and the Conventions legend's
        # '**Status: Open**' colon-inside style (post-merge review).
        match = re.search(r"\*\*Status:\s*(.+)", body)
        if match:
            status = " — " + re.sub(r"[*\[\]]", "", match.group(1)).split("(")[0].strip()[:80]
        lines.append(f"- `{slug}` — {title}{status}")
    return "\n".join(lines)


def _extract_known_issue_section(text: str, slug: str) -> str | None:
    for section_slug, title, body in _iter_issue_sections(text):
        if section_slug == slug:
            return f"### {title}\n{body.rstrip()}\n"
    return None


def _cap_section(text: str) -> str:
    encoded = text.encode("utf-8")
    if len(encoded) <= _SECTION_CAP_BYTES:
        return text
    return (
        encoded[:_SECTION_CAP_BYTES].decode("utf-8", errors="ignore")
        + "\n\n[truncated at 16 KB — read KNOWN_ISSUES.md in the repo for the rest]"
    )


def _known_issues_text() -> str | None:
    path = _REPO_ROOT / "KNOWN_ISSUES.md"
    return path.read_text(encoding="utf-8") if path.exists() else None


@server.resource(
    uri="gflow://docs/known-issues",
    name="Known Issues",
    description=(
        "Index of current known issues (titles + status). Read "
        "gflow://docs/known-issues/{slug} for one issue's full text."
    ),
)
async def known_issues() -> str:
    """Return a bounded index of KNOWN_ISSUES.md (#501)."""
    text = _known_issues_text()
    if text is None:
        return "KNOWN_ISSUES.md not found."
    return _build_known_issues_index(text)


@server.resource(
    uri="gflow://docs/known-issues/{slug}",
    name="Known Issue Section",
    description="Full text of a single known issue, by slug from the index.",
)
async def known_issues_section(slug: str) -> str:
    """Return one issue's full text, capped at 16 KB (#501)."""
    text = _known_issues_text()
    if text is None:
        return "KNOWN_ISSUES.md not found."
    section = _extract_known_issue_section(text, slug)
    if section is None:
        # Cap the echoed slug: reflecting arbitrary client input back as
        # trusted resource content would reopen the unbounded-injection path
        # this resource exists to close (post-merge review of #501).
        return (
            f"Unknown section slug {slug[:100]!r}. Read gflow://docs/known-issues "
            "for the index of valid slugs."
        )
    return _cap_section(section)


@server.resource(
    uri="gflow://db/schema",
    name="Database Schema",
    description="SQLite database schema for gflow.db — operations catalog.",
)
async def db_schema() -> str:
    """Return the initial migration SQL as a schema reference."""
    migration_path = _REPO_ROOT / "src" / "gflow_cli" / "data" / "migrations" / "0001_initial.sql"
    if migration_path.exists():
        return migration_path.read_text(encoding="utf-8")
    return "Migration file not found."
