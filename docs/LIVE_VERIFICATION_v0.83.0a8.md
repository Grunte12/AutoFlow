# AutoFlow 0.83.0a8 Character direct-commit verification

## Scope and observed cause

A guarded authenticated R2V preflight selected an exact saved Character row.
Flow committed the correct entity UUID immediately and closed its picker. The old
helper then waited for a detail panel that was no longer present. Both mutation
and generation dispatch counters remained zero during this investigation.

The common helper now waits for either a newly committed chip or the exact
selected detail. It never presses Enter. Existing final reference-kind and ordered
entity-ID checks remain unchanged. CLI and MCP use this shared helper; no payload
or tool schema changed.

## Test evidence

- Direct-commit unit control failed before the fix and passed afterward.
- Focused R2V, saved-video and native-image update regressions: 70 passed.
- Real-browser delayed direct-commit BDD: 3 passed (normal, wrong ID, wrong kind).
  The fixture is network-free; it tests DOM behavior, not Google model behavior.
- Authenticated guarded native preflight: exact ordered existing Characters,
  loaded single portrait previews, two distinct portrait/full-body media bindings;
  generation and mutation counters both zero. The imported source path was checked.
- Installed runtime reports 0.83.0a8. Existing editable runtime changes preserved.
- Final elevated offline suite: 5,117 passed, 10 skipped, coverage 91.79%.
  The initial sandbox run had build-cache/socket denials and version-site mismatches;
  these were fixed or rerun with the required permissions, not silently waived.
- Hygiene, doc links, PII, published mirror, council-memory, whole-tree Ruff/format
  and release-version gates passed. Pyright: zero errors/warnings.
- Lead diff review: no schema/auth/queue changes; no automatic write replay;
  final exact binding validation preserved. No upstream PR or public release.

## One authorized media test

The owner authorized one 10-second 720p portrait clip with existing Characters and
unchanged dialogue, no automatic retry. The MCP adapter first encountered a stale
session after daemon reload; discovery failed before job creation. Both services
were confirmed idle before reconnecting, and a read-only Character call passed.
One subsequent generation job was accepted and completed: one H.264/AAC MP4,
10.005 seconds, 720×1280 at 24 fps, full decode without errors. SHA256:
`dedb565aa770f7427a31cee2e50e32fe26a88d3aadafdc9166b17854fe8410f0`.
Two nonoverlapping 0.2-second contact-sheet reviews plus lead frame review found
Goofy broadly aligned, but Memo orange/calico markings less prominent than its saved
single images. Likeness remains partial, not approved. No video retry occurred.

## Limits

No new project/Character, image generation, STS, posting, or destructive cleanup.
Correct serialization and loaded thumbnails do not independently prove backend
image consumption. One rendered sample cannot establish perfect likeness or all-case
reliability. The tool-level direct-commit defect is repaired; model-level likeness
is not declared solved.
