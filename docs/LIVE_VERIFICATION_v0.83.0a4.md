# AutoFlow 0.83.0a4 source-preview verification

Date: 2026-10-10. Surface: existing Character portrait/full-body replacement on
flow.google.com. The operator authorized the selected existing project,
Character, and source images; no generation was authorized for this verification.
Private IDs, image paths, signed URLs, logs and journals remain local.

## Actual live proof

| Route | Observed result |
| --- | --- |
| Native MCP stdio, both slots | Two uploads acknowledged against the exact existing entity; fresh project state matched both workflow/media bindings |
| CLI replay of that operation | Same result, no new uploads; journal unchanged |
| MCP replay of that operation | Same result, no new uploads; journal unchanged |
| CLI portrait-only update | Portrait persisted; existing full-body binding and non-image metadata fingerprint unchanged |
| MCP replay of portrait-only operation | Same result; journal unchanged |
| Installed LinkHub full-body-only update | Approved body restored on the existing Character; portrait and metadata unchanged |
| Installed LinkHub replay of body-only update | Same bindings and result; complete operation-row hash unchanged, no second upload |

The fixed both-slot browser-bound BDD scenario passed in 116.45 seconds in
read-only reconciliation mode against the already successful upload operation.
The portrait-only browser-bound BDD scenario passed in 159.95 seconds.

## Failures retained as lessons

The first clear attempt expected the wrong RPC acknowledgement. It detached only
the selected reference and stopped before upload. A fresh native read verified
that outcome. The repaired driver uses exact project-state readback rather than
an optimistic preview or guessed acknowledgement.

A later test harness stopped after successful upload and CLI replay because its
Then sentence did not match the feature. The binding was corrected and checked
offline; the already completed operation was replayed without another upload.

The installed LinkHub body-only path also exposed a DOM hydration race: the
dialog container was visible before its confirmation button acquired the native
primary-button class. A read-only open/cancel probe observed the generic buttons
hydrate after 0.2 seconds and verified the Character was unchanged. The driver
now waits for the actual confirmation control before uniqueness checks; a new
offline regression models that delay. The failed attempt stopped before
confirmation and upload, with no uploaded bindings in its durable journal.

The next installed attempt exposed the same readiness gap in the shared upload
control lookup after a successful reference clear. It stopped before file choice
or upload, leaving the body reference empty. Three failing regressions captured
late hydration, timeout and duplicate-control handling. The repaired shared
helper waits for the actual control and still refuses missing/ambiguous controls.
A new, explicitly authorized restoration operation then succeeded through the
installed LinkHub MCP path, using the approved original body image. Portrait and
non-image metadata remained unchanged.

## Evidence boundaries

Validated source bytes are frozen and hashed before mutation. Native upload
acknowledgements plus fresh project reads prove exact entity/slot/workflow/media
ownership. The source hash is not a claim that Flow's processed image bytes are
identical, nor a video likeness or rendering-quality evaluation.

Multi-slot changes are not atomic. A failure after reference detachment or the
first upload can leave partial state. Checkpoints remain durable; incomplete or
drifted updates refuse automatic resubmission. Original project media is retained.

No generated images/videos, new Character/project, logout/login, credential
changes or deletion of original media occurred. Verification is against the
operator's current account/UI cohort, not every possible Flow cohort.

## Offline and delivery gates

The isolated source-preview environment was installed from the frozen lockfile.
The full offline suite, excluding live/e2e/smoke/container markers, passed:
5,080 passed, 7 skipped; total coverage 92%. The focused Character suites passed
94 cases. Separate version/smoke checks passed 14 cases. LinkHub's relevant
adapter suite passed 65 cases, including six Character-update regressions.

Whole `src` strict Pyright: zero errors/warnings (explicit preview interpreter).
Ruff check and format check across `src tests`: clean. Repository hygiene,
documentation links, published-docs PII, website mirror and council-memory
structural checks: passed. No formatting fix was required.

The initial broad run used an incomplete shared test environment. Missing image
and media dependencies, sandbox-denied loopback/build access and stale installed
package metadata were corrected with an isolated frozen environment and explicit
test permissions. Preview version-site drift was also repaired. No tests were
weakened or hidden to turn that run green.

Six mirror axes were reviewed: CLI and native MCP share the service; LinkHub
background execution passes the same inputs; native generation worker/codec is
not involved. Tool claims, CLI help, agent skill, docs and published mirrors are
aligned. Existing error classes/exit codes are reused. Generation templates and
model/doctor selectors are unaffected. The Docker pin matches preview metadata,
but this source preview is not a PyPI release or a verified Docker image.

The installed editable source preview reports 0.83.0a4. The public AutoFlow
Character-update capability is available through the existing scoped LinkHub
grant. This is a local source installation, not a registry or tagged release.
