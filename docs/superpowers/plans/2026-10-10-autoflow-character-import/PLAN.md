# AutoFlow canonical Character and pre-submit diagnostics

Goal: reuse original character sheets through native Flow identity bindings, and give agents actionable errors without inviting duplicate paid submissions.

Owner authorized implementation, owner-repository push and installation on 2026-10-10. This is not authorization to publish credentials or retry an uncertain generation.

Architecture: retain the existing browser session, profile lease, request DTO and queued video identity fields. Import must be a non-generating operation, separate from prompt-based Character creation. Add positive pre-submit proof at a narrowly known refusal boundary; ordinary configuration errors remain uncertain.

Predict verdict: CAUTION. Five independent persona reviews agree diagnostics can proceed; native import and migrated identity observation require live evidence before claiming support. No new browser engine, registry, daemon or auth implementation.

## Risk register

| Risk | Mitigation |
|---|---|
| Duplicate billed generation | Preserve uncertain ledgers; no inferred no-spend result from exception class or empty IDs |
| Canonical identity replaced | Never call image generation or silently reinterpret import as a reference-guided portrait |
| Wrong binding | Verify entity/project/workflow/media identifiers and metadata readback |
| Secrets in diagnostics | Closed safe fields, metadata-only probe, no screenshots, tokens or raw network bodies |
| Dirty runtime lost | Work in an isolated branch; installation must preserve and verify existing changes |

## Task 1 — Refusal evidence (independently shippable)

- [x] Review five predict personas and existing migration evidence.
- [x] Add failing tests for positive pre-submit proof, redaction and exit 11 compatibility.
- [x] Implement a narrow configuration error subtype and use it at the existing R2V duration refusal.
- [x] Preserve requested duration; label unmeasured combinations unverified rather than globally unsupported.
- [x] Test CLI/MCP serialization and unchanged ordinary-error semantics.

Files: `src/gflow_cli/errors.py`, `src/gflow_cli/api/transports/migrated_composer.py`, targeted tests and error documentation.

## Task 2 — Native import evidence gate

- [x] Inspect current native Character upload controls using one owned client, without media generation.
- [x] Capture the actual native upload/binding and metadata readback contract.
- [x] Turn observed browser behavior into a rerunnable E2E test (live pass still gated below).
- [x] Implement only after the contract is known; do not substitute unverified REST-equivalence assumptions.

## Task 3 — Character import and MCP twin

- [x] Validate original files before starting Chrome; record source hashes and operation-aware recovery.
- [x] Import without generation, bind stable workflow IDs, verify name/personality/source ownership.
- [x] Add CLI and native MCP surfaces over one service.
- [ ] Add remote uploaded-file staging in the separate LinkHub adapter (deferred product integration).
- [ ] Verify entity reuse and terminal-result attribution before removing migrated entity guards.

## Task 4 — Delivery

- [x] Run repository quality checks and lead safety/surface review.
- [ ] Full independent branch council / hosted CI verdict (not claimed for source preview).
- [x] Run named live CLI/MCP and browser E2E matrix; do not treat mocks as Flow proof.
- [x] Push a feature branch to the owner's AutoFlow repository only.
- [x] Install tested changes without replacing unrelated dirty runtime files; verify the active MCP revision.

## Definition of done

All applicable tasks checked, safe failures and identity bindings verified live, no duplicate submission, passing scoped offline tests plus full lint/format and CI results recorded. A partial diagnostics increment is not completion of Character import or video identity reuse.

## Verification status

Positive refusal proof passed offline CLI/MCP tests and one live non-generating
browser BDD. Native Character listing passed both real CLI and MCP stdio.
The final native upload and cross-surface replay BDD passed after the owner
approved one additional test Character. Earlier interrupted operations must not
be automatically replayed. Existing-image upload controls are not verified.

REA 6.2.0 CLI now discovers the exact owned Flow target through a temporary
loopback CDP endpoint. This does not require global MCP configuration changes.
Discovery alone was not used as proof of an API contract.

Static-source inspection subsequently succeeded, including Flow's shipped
Google CDN scripts. The upload RPC declares a nested media response; this
invalidates the flat-ID fake fixture, but is not yet a verified native import
receipt. Both development probes now default to headless inspection; a visible
window requires explicit `--visible`. Read-only REA source inspection passed in
headless Chrome. This is not proof that paid generation works headless; retain
the production generation browser policy.

Full offline selection plus scoped environment-blocked reruns: 4,915 passed,
30 skipped, 171 deselected. Six additional STARTED-journal mismatch cases passed
separately after full-suite collection. Build caches used for packaging reruns
were outside the source checkout.

## Work allocation

### Latest upload repair gate

The observed upload reply has nested media/workflow rows, not flat UUID fields.
The importer now validates their project/entity relationships. Empty native
Characters no longer break listing. Upload acknowledgement is not completion:
the importer waits for image processing and an exact metadata save acknowledgement
before Done, then reloads project bindings and the Character form.

Owner subsequently approved exactly two test Characters. Both original-sheet
uploads created test entities; neither complete import receipt passed. The second
failure was specific: the form had saved requested metadata while the first
project snapshot still returned the previous name. The importer now retries
only bounded read-only transitional snapshots (missing references/workflow or a
stale name), never uploads or metadata writes. This last repair passed 46 scoped
import/service tests. Whole-source lint, format and strict types passed.

The full offline run immediately before that final stale-name repair passed
4,973 tests, skipped 7, and achieved 92.29% coverage. The final repair has scoped
verification, not another full-suite or successful fresh live-import receipt.
Luna completed the earlier verification batches, then exhausted its usage limit;
the lead ran the final background scripts. A stream/file-descriptor bug in the
MCP test harness was also repaired before the second upload.

All seven version declaration sites now identify the source preview as
`0.83.0a1`. The feature branch was pushed to the owner's AutoFlow repository and
installed into the existing local source runtime. Its CLI and live loopback MCP
both report `0.83.0a1`; native Character import and existing video-batch tools are
registered. Installed import regression: 82 passed. The pre-existing tracked
patch passed reverse-apply verification, confirming local fixes remain present.
No release tag or PyPI/MCP Registry publication occurred. This preview is not a
stable release; version-pinned distribution artifacts have not been published.
The initial two-Character authorization was exhausted.
The owner approved one additional test Character. The final live BDD passed in
96.77 seconds: real MCP import, same-UUID CLI/MCP replay, exact bindings, unchanged
journal/source hash and fresh metadata form verification. Its public sanitized
receipt is `docs/LIVE_VERIFICATION_v0.83.0a1.md`; private IDs remain local.
Migrated video entity submission and remote LinkHub file staging remain separate
unchecked work, not proven by this upload repair. Push and installation follow
the verified source-preview path, without PyPI publication or a release tag.

The lead owns root causes, request/response contracts, uncertainty handling and
installation decisions. Luna workers own disjoint deterministic test batches
and repeated verification. They do not duplicate live mutations or independently
retry submissions. Frame QC, when resumed, is split into distinct time ranges.

Run offline tests first. Use one background client for the smallest necessary
live evidence batch, not a visible browser per test. REA CLI is a development
inspection tool, not a new runtime dependency or an alternative auth stack.
