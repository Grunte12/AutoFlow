---
name: autoflow-mcp
description: Use AutoFlow MCP to reuse Google Flow projects and Characters, set portrait/full-body references, and generate media with explicit reference roles. Use for operating AutoFlow, not developing its source code.
---

# AutoFlow MCP

Use the connected MCP tools. The native tool identifiers below retain `gflow_`
for compatibility; the product is AutoFlow.

## Find only what you need

- If the needed tool and current schema are already exposed, call it directly.
  Do not fetch the full tool list or this guide again before every operation.
- With a deferred tool host or hub, search for the specific capability once,
  inspect its schema, then reuse that handle/schema while valid. A hub may rename
  tools: use its published alias, not a prefix guessed from the native name.
- Refresh on a changed server/schema, missing tool, or schema error. Listing is
  appropriate when the provider is genuinely unknown. A skill routes calls; it
  does not replace schema validation, permissions or the client's MCP discovery.
- `gflow_list_tools` lists **prompt-rewriting presets**, not MCP capabilities.
  Do not call it to discover Character or video tools.

## Route the task

| Need | Native tool | Essential inputs / meaning |
|---|---|---|
| Reuse project | `gflow_project_context` | Cached binding; use the user's known project UUID when available |
| Find local projects | `gflow_list_projects` | Bounded `limit`; this is local history, not the complete remote inventory |
| Inspect Characters | `gflow_character_list`, then `gflow_character_show` | `project`, then exact `entity_id`; keep selected IDs/names for this task |
| Remember chosen project | `gflow_project_bind` | `project`, optional `character_names`; binding does not attach Characters automatically |
| Replace saved images | `gflow_character_update_images` | `project`, `entity_id`, `operation_id`, `portrait_path` and/or `full_body_path` |
| Check session | `gflow_auth_status` | Check before the first generation; recheck on auth failure |
| Generate video | `gflow_generate_video` | Scene prompt and explicit settings; see reference rules below |
| Generate image | `gflow_generate_image` | Use current schema for model and image references |
| Recover a download | `gflow_download_media` | Known `media_id`; does not regenerate the clip |

For new Character imports or visual continuity work, read
[Character references](references/characters.md). For cleanup, use the installed
AutoFlow project-management skill when available; otherwise inspect the relevant
tool schema and verify exact targets and preservation before deleting assets.

## Saved-Character video

On the supported `flow.google.com` path, use `mode="r2v"`, `count=1`, the existing
`project`, and paired `reference_entities` / `reference_entity_names`. `@Name` in
the prompt resolves that same saved identity. Prefer exact IDs when names collide.
Use `reference_images` for separate product, environment or direct-image inputs;
state each input's role. I2V uses `initial_frame`, not saved Character entities.

Write the scene goal, who says/does what, and only the appearance/camera details
that matter. Saved images provide identity; important scene instructions belong
in the generation prompt, even if Character info also records them. Literal
filenames are not identity bindings. A correct binding is not a likeness guarantee.

Use `wait=true` for an ordinary single job. With `wait=false`, pending is a receipt,
not a finished clip; continue through the host's supported task mechanism. Do not
invent a poll tool or resubmit a job because a response/download was delayed.
Honor the user's existing scope and credit authorization without asking again for
the same action. No-spend mode disables generation. Inspect uncertain outcomes
before retrying. Return the artifact and the observed QC result.
