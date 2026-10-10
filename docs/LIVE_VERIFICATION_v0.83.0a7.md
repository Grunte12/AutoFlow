# AutoFlow 0.83.0a7 source-preview verification

Date: 2026-10-11. Owner feature-branch preview only: no upstream PR/merge,
registry publication, release tag, Character edit, upload or paid generation.

## Measured cause and repair

The independent native control required an exact Character search row, its
selected detail panel, and the structural Add-to-prompt button. Enter alone
did not commit a Character in the current picker. The old fresh production arm
then backspaced its failed query and removed existing image chips. Its guard
stopped before submission. Moving only the caret into a paragraph did not fix it.

The shared composer now uses the measured native Character confirmation, waits
for the requested detail name rather than a stale preceding Character, and
waits for the entity chip to finish binding. It verifies ordered entity UUIDs,
not set membership. Append caret placement is inside the last paragraph. An
unfinished native confirmation returns a typed pre-submit refusal; no retry
is performed through destructive Character-query cleanup. Media insertion and
CLI/direct/queued MCP request schemas are unchanged.

The reusable test's request observer also failed on unrelated binary traffic:
Playwright's text-body accessor raised UnicodeDecodeError, then its exception
rewriter masked that as TypeError. The observer now reads bytes with replacement
decoding; a regression covers binary telemetry and generation/upload counting.
This tester failure was not a missing Character or a disabled submit button.

## Evidence layers

A guarded real-browser native-versus-fresh-production run captured both arms.
Luna independently compared the full retained redacted rich trees: chip types,
ordered image IDs, Character UUID/name pairs, text segmentation/order,
whitespace and text hashes match exactly. Both also match the retained actual
prior production job's rich prompt, media IDs, model, count and entity IDs.
The project is explicitly scoped and validated in both captured requests.

Requested portrait, ten seconds, 720p and count one were read back by checked UI
controls. The wire model key encodes ten seconds. Numeric aspect/resolution
enums in retained output are not independently mapped and are not guessed.
Current-versus-native UI readback is a separate proof from old-output enum equality.

The reusable regression now captures native, production and a second native
control. Full generation specifications match except two UUID slots, `[5][4]`
and `[5][5]`, which also vary in the repeated native capture. Their semantics
remain unmapped. The comparator permits only measured UUID variance in those
slots; every other slot, including undecoded numeric settings, must match.
It reports both the exact-equality result and all differing paths rather than
claiming byte-identical complete requests. Six offline probe tests cover the
comparison and reject other differences or non-UUID values.

Generation and asset-mutation dispatch counters stayed zero. Server media IDs
were unchanged. No video was created. The prior rejected likeness is still
unresolved: client equality does not prove backend entity-to-image resolution,
model pixel consumption or rendered Character identity.

## Regression and delivery checklist

- [x] Old fresh helper RED in the guarded real browser before repair.
- [x] New helper native/current two-arm capture passed, independently reviewed by Luna.
- [x] 165 focused composer/R2V/saved-Character/probe tests passed, including duplicate
  names, stale detail, failed Add preserving prior media, wrong kind/UUID and order.
- [x] Binary-observer and full-spec regression: six offline probe tests passed.
- [x] Reusable opt-in BDD real-browser parity regression: one passed with three
  captures in 122.92 seconds; zero dispatch and unchanged media.
- [x] Installed runtime: two-arm guarded acceptance passed in 84.33 seconds.
  Luna independently compared its complete redacted structures against the source run.
  Native variant controls were transient; their availability/meaning is not inferred.
- [x] Final hygiene, docs/mirror/privacy and lint/format passed; strict src types:
  zero errors. Final offline run: 5115 passed, seven skipped, 91.90% coverage.
  Four isolated workers completed in 132.61 seconds.
- [ ] Owner branch push and scoped editable runtime installation.
- [x] Installed-runtime guarded acceptance.
- [ ] Rendered identity acceptance: remains unresolved; no new generation authorized.

The reusable probe and opt-in command are documented in
[E2E testing](E2E_TESTING.md#character-picker-parity). Private input files and
raw captures remain local and are not published.
