# Saved Character video: bounded repair

Owner authorized one short video using existing Characters, followed by identity QC.
Do not create Characters, regenerate on uncertain outcomes, change voices or post.

## Evidence and safety review

- [x] MCP codec preserves entity IDs and names (175 targeted tests, three repetitions).
- [x] Native picker attached both requested entity IDs and emitted them in the R2V request.
- [x] Request capture was aborted before transmission; attachment is not generation proof.
- [x] Root cause: `_unported_form` blocks all saved-Character video requests. The historical
  null submit acknowledgement cannot be treated as a generation record.
- [x] Establish exact workflow attribution from native project/status evidence.

Five lead-reviewed lenses (not an independent council): correct identity, pre-billing
validation, concurrent/old job isolation, CLI/MCP parity, smallest complete repair.
Verdict: CAUTION. Keep refusal until exact entity request binding and unique job attribution
have tests; never pick the first project record or infer absence from a timeout.

## Delivery

1. [x] Add red regression tests for entity request validation and null-ack attribution.
2. [x] Repair observer with exact project/workflow/media filtering and no automatic resubmit.
3. [x] Preserve installed duration/record-schema fixes as explicit prerequisites.
4. [x] Run offline tests, types/lint, and zero-credit browser regression.
5. [x] Install candidate without overwriting unrelated runtime changes.
6. [x] Run the one authorized paid MCP generation, download, then QC at 0.2 s intervals.
7. [x] Run repository delivery checks; push only verified changes and record installed version.

Do not call the generation path complete based on tests or picker chips alone.

## Verified outcome

The one paid stdio MCP run completed and downloaded a fully decodable 8-second
720p portrait clip. Native readback confirmed both entity IDs and intended prompt.
The output failed creative QC (age, accessories and unwanted text), so it remains
test-only. The one-clip approval is consumed; no paid retry is authorized here.

The final offline suite passed 4,988 tests with 7 skipped and 92.18% coverage.
A follow-up focused run passed 11 binding/observer tests. Installed CLI and the
restarted owned HTTP MCP both report 0.83.0a2. The installed-source background
probe verified entity chips, wire slots and exact prompt while aborting submission
before billing. See [live verification](../../../LIVE_VERIFICATION_v0.83.0a2.md).

Implementation commit `08efa6946c53252abaf70f9ba69fd24cbd7fe808` was pushed
to the owner's AutoFlow `feature/autoflow-character-import` branch. No upstream
PR, main-branch merge, release tag or public registry publish was performed.
