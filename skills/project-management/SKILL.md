---
name: project-management
description: Manage reusable AutoFlow project and Character context; select an existing brand project, avoid per-clip scratch projects, and preserve used media before project cleanup.
---

# AutoFlow project management

One brand/Character group should normally share one Flow project. Do not create a
project per shot, product, retry or test. Character identity and reference media are
project-scoped; never assume an entity ID from another project is interchangeable.

## Select once, reuse

1. Read `gflow_project_context`. It is an offline cached binding, not a live inventory.
2. For an existing brand, use its recorded project UUID. `gflow_list_projects` reads
   only the local catalog; a missing row does not mean Flow has no such project.
3. Inspect its Characters with `gflow_character_list`. Bind the project and exact
   selected names using `gflow_project_bind`. Missing, ambiguous or image-less
   Characters fail binding. Do not import duplicates to work around that failure.
4. Image/video generation calls without `project` reuse this binding. Explicit
   `project` or `project_name` overrides it. Use `replace=true` only to intentionally
   switch the binding, not on every call. CLI twins are `gflow project bind UUID
   --character-name NAME --profile PROFILE` and `gflow project context --json`.
5. Select only Characters needed for a scene using the bound IDs/names or native
   mentions. Binding does not attach all Characters automatically. Revalidate the
   remote list after an identity change; cached metadata is not proof of likeness.

Portrait/full-body references are not interchangeable with a contact sheet by
assumption. Inspect the actual saved image and native form before changing them.
Do not press a full-body generation action or regenerate media without authorization.

## Cleanup is separate from binding

Use `gflow_project_rename` to give the retained project a recognizable brand title.
Rename uses the existing native readback path; it does not create or merge projects.

Binding does not merge projects, move assets, upscale, or delete anything. Build an
exact UUID inventory first. Identify approved/used clips from the current project
manifest and approvals; a generic title or old date is not enough to delete a project.

Before deleting a project, preserve every used clip at the owner-requested resolution
(normally 1080p), verify dimensions/audio/full decode, and record its source project,
workflow/media ID, local path and hash. Keep the original until this succeeds. If
upscaling availability or cost is unknown, verify it before dispatch; do not call it
free from memory. Preserve Characters needed for future work in the retained project.

Only remove exact verified unused targets within the owner's scope. If usage cannot
be resolved or transfers are unverified, stop deletion and report those targets. Never
delete all projects matching a title, infer that downloads merge projects, or claim
that Flow's remote archive is a verified backup without checking it.
