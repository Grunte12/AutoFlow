# AutoFlow 0.83.0a6 source-preview verification

Date: 2026-10-11 (work started 2026-10-10). Scope: native Character personality readback and read-only
diagnosis of the prior rejected saved-Character video. Owner source preview only;
no release tag, registry publication, upstream PR or merge.

## Confirmed reader defect and repair

The native project parser unconditionally returned `personality=None` despite
the stored text at `character_info[2]`. List/show, CLI and MCP share this parser.
It now preserves text exactly, including Unicode and an empty string. Missing or
null values remain null; malformed non-text values raise a safe format error.
Voice remains null because its native wire shape has not been established.

Luna added failing regression cases before the fix: seven failures confirmed
discarded text and accepted malformed values. The focused suite passed 173 tests;
the final full offline suite passed 5,101 tests with seven skips and 92% coverage.
Real CLI followed by native MCP stdio reads passed for both existing Characters
(17.69 and 16.77 seconds), preserving expected personality digests and workflow IDs.
An earlier restricted sandbox attempt stopped at cookie pre-read permission,
before any Character observation; the correctly authorized run passed.

## Actual production job diagnosis, not only a blocked capture

A fresh native project read located the exact previously generated media and
workflow. Its stored generation specification uses `abra_r2v_10s`, two saved
Character entity IDs in its entity-reference slot, and the same IDs plus display
names in the rich prompt. Its two media-reference IDs are the uploaded café and
product, not the Character portrait/body media IDs. This agrees with the native
UI's observed separation of entity references and plain media references.

The currently served public frontend's route-split module was inspected as a
positive control: it contains `MZZa6b` and the reference-video builder. That builder
serializes plain image references separately from Character entity IDs (protobuf
fields 2 and 10 respectively). Entity conversion creates a one-ID reference, not
a client-side expansion of portrait/body pixels. The exact production row agrees
with this native construction. The missing portrait IDs in the plain-image slot
are therefore not, by themselves, an AutoFlow dropped-upload defect.

Both Characters still have the expected saved personality hashes and verified
workflow-to-media bindings. One has portrait and full-body references; the other
has a portrait and no full-body reference. No metadata or images were changed.

**Not proven:** that the server resolved the entity references into those images
for Omni, or that the model consumed their pixels. Stored entity UUIDs are not
proof of downstream image consumption. The cartoon/human rendered identity was
rejected; repairing the public metadata reader does not repair that output.
Name collision, missing species prose and model-specific entity handling remain
hypotheses unless further observable evidence distinguishes them. Do not replace
native Character binding with appearance prose and label it fixed.

Private evidence: the owner's exact prior dispatch/QC receipt and a fresh native
production-row read. Account/project/entity/media IDs, prompts, signed URLs and
raw response bodies are deliberately not published here.

## Verification and delivery

- [x] Confirm the actual stored personalities and approved image bindings.
- [x] Locate the exact production video row and its retained rich prompt.
- [x] Regression RED before parser repair.
- [x] Regression GREEN and CLI/native MCP live reads for both Characters.
- [x] Hygiene, links, website privacy/mirror, repository memory, Ruff and strict types.
- [x] Public HTTP LinkHub read after scoped local installation, for both Characters:
  returned personality text exactly equals the expected native text, and approved
  workflow IDs are unchanged. The public schema version is unchanged.
- [x] Owner push of implementation commit `310c2f03` to `bugfix/omni-r2v-10s`.
- [x] Scoped editable installation: source and package metadata both report
  `0.83.0a6`; 46 installed-runtime parser/CLI tests passed. Existing unrelated
  runtime edits were retained. Idle local AutoFlow/LinkHub services were restarted
  before public HTTP acceptance.
- [ ] Rendered Character identity acceptance: unresolved; no additional generation.

No video generation, upload, Character/project mutation, deletion or generation
credits are authorized in this verification pass. New generation remains stopped.

## Durable lesson

Separate three facts: metadata readback, native request binding, and rendered
identity. Tests must name the layer they prove. A successful request or exact
entity UUID is not a passing likeness test.
