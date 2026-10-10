# AutoFlow 0.83.0a2 source-preview verification

## Scope and authority

One owner-approved saved-Character R2V video, Omni 1.1 Flash, 8 seconds, 720p,
portrait, count one. Existing Characters only. No new entities, STS, posting or retry.
This is a feature-branch source preview, not a signed public registry release.

## Evidence

The paid run used the initial repair candidate reporting 0.83.0a1. Follow-up changes
add explicit prompt-text preflight validation and diagnostics; they are checked by
offline replay and a zero-credit native request probe, not a second paid generation.

- A zero-credit background probe verified two native entity chips and the corresponding
  MZZa6b entity-reference slots. The request was aborted before transmission.
- A BDD-bound real stdio MCP test passed: enqueue → atomic claim → native UI attachment
  → one submit → exact rich-prompt/new-baseline attribution → running status → terminal
  result → download → full ffmpeg decode. The isolated test database did not consume
  another daemon's pending queue.
- The terminal clip is 8.000 seconds, 720 × 1280, video plus audio, 2,397,829 bytes.
- Read-only native readback of the completed clip confirmed that its prompt text and
  both entity IDs matched the intended request. No stale composer text was observed.
- Capture/artifact paths, account-specific IDs, database and raw logs remain private,
  outside Git. No signed media URL or credentials are published here.

## Creative QC is a separate result: rejected

Forty frames at 0.2-second intervals were split into disjoint early/late contact sheets
and reviewed by two Luna agents, with lead review against both original sheets.
The output made the puppy look adult and omitted its teal harness. The kitten looked
older/larger and markings were only a loose match. The video added on-screen text
despite the prompt. This test clip is not a valid production asset and was not added
to the affiliate repository's canonical asset manifest.

The test proves transport binding and end-to-end execution, not reliable Character
likeness. Explicit concise age/accessory cues and output QC remain necessary. This
preview does not claim all models, all accounts or every generation scenario is bug-free.

## Remaining verification boundaries

The paid E2E was run through MCP once; a second paid CLI clip was deliberately not
generated under one-clip authority. CLI shares the same request/transport path and
is covered offline; paid CLI replay is not claimed. Source checks and delivery receipts
must describe their actual results, not infer them from this media test.

## Source and installation gates

- Final offline suite: 4,988 passed, 7 skipped; coverage 92.18% (80% required).
- Focused follow-up: 11 binding/null-ack observer tests passed.
- Installed CLI and owned HTTP MCP initialize response report 0.83.0a2.
- The owned daemon queue was idle before its scoped restart. Existing unrelated
  runtime changes were preserved rather than replacing the installed checkout.
- A zero-credit probe against the installed source verified both native chips,
  entity wire slots and exact prompt text; the request was aborted before billing.
- The installed checkout is not identical to the clean delivery tree: pre-existing
  local duration/parser changes were retained. The full suite covers the delivery
  tree, not a falsely claimed full installed-checkout suite.
