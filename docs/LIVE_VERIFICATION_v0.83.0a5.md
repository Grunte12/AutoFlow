# AutoFlow 0.83.0a5 source-preview verification

Date: 2026-10-10. Scope: explicit Omni Flash, count-one, 10-second R2V with
two existing saved Characters and two approved local reference images.
Private account/project/entity/media IDs, prompts and captured bodies stay local.

## Actual live proof

- The original request was refused by a shared duration guard derived from Veo
  Lite's 8-second measurement. This was an AutoFlow restriction, not a Flow limit.
- The first successful isolated probe used a test-process-only bypass to measure
  the selected native model. The blocked submit was `MZZa6b`, model key
  `abra_r2v_10s`, count one; exact project, two Character IDs, two freshly uploaded
  image IDs and prompt text were verified. Zero generation network requests.
- After the narrow guard repair, the opt-in browser-bound BDD ran the registered
  native MCP handler -> durable queue -> worker -> production composer **without
  the bypass**: **1 passed in 73.22 seconds**. Production control readback verified
  Omni Flash, 10s, portrait, 720p and count one; the blocked wire preserved both
  Character and both image bindings. No generated video or generation credits.
- Capture deliberately ends with a typed configuration error: it must not return
  fake success, video files, or a task awaiting a paid retry.

The test uploaded the two approved references through the normal path; those
image assets remain in the selected project. It created no project or Character
and changed neither Character's portrait, body nor personality.

## Failures and workflow lessons

- The original delivery tree lacked the caret fix already present in the local
  runtime. After adding the second image mention, query cleanup removed the first
  chip. The guard stopped before submission. The delivery now focuses the editor
  and collapses its DOM range at the end, preserving earlier mentions.
- Composer clearing selects its actual contents rather than assuming macOS
  Control+A means Select All. An empty picker never presses Enter on the form.
- The first capture observer attempted to decode a binary upload body. It now
  inspects only batchexecute text and generation endpoint URLs.
- A formal run completed input capture but failed final MCP-envelope readback
  while an offline suite shared pytest's default temp root. The repeat run used
  a distinct `--basetemp` and passed. Parallel runs must isolate their databases
  and temp roots; do not infer a video failure from a test-harness failure.

## Safe operation and limits

Use explicit `model="omni_flash", duration=10, mode="r2v", count=1` with paired
`reference_entities` / `reference_entity_names` and the intended images. Omitted
duration still pins 8s. Other non-8s combinations, including omitted-model 10s
and Omni 4s/6s, remain refused as unverified. Never downgrade or retry blindly.

This proves native MCP queue/composer **input binding**, not a rendered clip,
likeness, dialogue timing or flawless output. The HTTP LinkHub paid-generation
path and creative QC must still be accepted by the owner's Affiliate chat.
Character image-update acceptance replay is a separate check; it is not implied
by this generation-input capture.

## Delivery gates

- Focused transport tests: 36 passed; MCP parity/server tests: 61 passed;
  browser-bound BDD binding guard: 5 passed.
- Final isolated offline suite: **5,088 passed, 7 skipped, 92% coverage**.
  Live/e2e/container suites were explicitly excluded from that offline sweep.
- Ruff check and format check: clean across 549 source/test files. The capture
  script also passed both checks. Strict Pyright source: zero errors/warnings.
- Repository hygiene, documentation links, published-doc PII check, mirror/nav
  check and council-memory link check passed. New verification evidence is
  repository-only, deliberately not a published website page.
- The real-client omitted-model 10s refusal BDD passed: **1 passed in 9.46
  seconds**, no upload or generation dispatch, requested duration unchanged.
- Preview version matches package, source, lock and plugin metadata. The first
  offline version test caught stale editable-install metadata; reinstalling the
  isolated preview fixed it without weakening the assertion.

Lead surface review: shared guard covers CLI/direct/queued calls; no parameter or
queue schema was added. MCP claims, CLI usage, changelog, README, preview status,
index and published mirrors agree. Existing 8s/default behavior and unverified
combination refusals remain. No new dependency, auth or transport abstraction.

## Distribution boundary

Owner-repository source preview only. No upstream push, PR, merge, tag, PyPI
publication, MCP registry publication or Docker registry release. No paid video
generation, automatic retry, batch or host workaround was performed here.
