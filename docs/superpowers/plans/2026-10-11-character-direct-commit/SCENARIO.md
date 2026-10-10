# Character row direct-commit compatibility

## Evidence and scope

The authenticated 10-second R2V preflight selected Goofy and committed an entity
chip carrying the requested UUID. The picker closed. AutoFlow then waited for a
detail panel that no longer existed. Generation and Character writes were blocked;
both dispatch counters stayed zero. This is a confirmation-state bug, not evidence
that Flow ignores saved images.

Change only the shared Character confirmation wait: accept a new chip OR the exact
selected detail, then preserve the existing ordered UUID and kind checks. No new
transport, API field, project, retry, auth behavior or credit authority.

Predict: isolated fix; no new selector or boundary. Review concerns are duplicate
Add, wrong-kind/wrong-ID chips, and stale detail. Existing final validation stays.

## Coverage

Active D3 (two native commit paths/stale detail), D7 (typed pre-submit refusal),
D11 (duplicate exact names/extra chips), D13 (CLI and queued MCP use this helper).
Other dimensions have no changed boundary: authentication, WAF, queue, database,
paths, platform and logs remain untouched.

| Scenario | Expected | Evidence |
|---|---|---|
| Exact row commits directly and closes picker | No second Add; ordered IDs remain correct | Unit + real-browser BDD + guarded native preflight |
| Row opens matching detail | One Add only | Existing unit regression |
| Stale detail names another Character | Refuse before Add/submit | Existing unit regression |
| Wrong ID or media chip commits directly | Refuse before submit | New unit + browser BDD |
| Existing media precedes two Characters | Preserve media and validate only new chips | New unit + browser BDD |
| Duplicate exact names | Refuse before click | Existing unit regression |

## Plan and limits

- [x] Reproduce exact failure with submits blocked.
- [x] Add a failing direct-commit unit test before the fix.
- [x] Repair the common wait without weakening final checks.
- [x] Run real-browser BDD and authenticated guarded preflight.
- [x] Apply only this hunk to the installed runtime; confirm imported source.
- [x] Submit the human-authorized one 10s/720p clip via MCP, no retry.
- [x] Compare split 0.2s contact sheets with actual saved single-image references.

Output is technically valid; likeness is partial. Memo markings remain different.
No production approval or all-case claim follows from successful tool execution.

One authorized output is not proof of all scenarios or backend image consumption.
Production identity approval still belongs to the owner.
