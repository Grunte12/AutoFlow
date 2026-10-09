# AutoFlow 0.83.0a1 source-preview verification

Verified on 2026-10-10 against one owner-approved, authenticated
`flow.google.com` project. This is a source preview, not a PyPI, Docker or MCP
Registry release. No release tag or protected-branch merge is part of delivery.

## Character upload and replay

The final live BDD passed: `MCP import replays read-only through both CLI and MCP
stdio` (96.77 seconds). One new verification Character was imported via the real
MCP stdio server, then replayed through separate CLI and MCP processes using the
same operation UUID. Exact entity/project/workflow/media identifiers matched;
the operation journal was unchanged on replay. A new browser session verified
name/personality after reload. Generation tools were unregistered during the
MCP test. No video or image generation command was called.

| Evidence layer | Verified result |
|---|---|
| File count | One original local character-sheet input; no substitute/generated portrait |
| Magic bytes | Valid PNG source validated before opening Chrome |
| Shape | Source 1086 × 1448; exact native project/entity/workflow/media relationships |
| Invariants | Source SHA256 matched import/replays; journal succeeded once, unchanged on replay |
| User-confirmable artifact | Verification Character retained the uploaded image, name and personality after reload; private receipt holds IDs |

Replay proof is stable bindings plus the unchanged journal and the shared
service's read-only reconciliation path. The test does not have an independent
network-upload counter. Private source paths, IDs, hashes, authentication data
and raw browser logs are deliberately omitted here.

## Root causes repaired

- Native upload replies contain nested media/workflow rows, not flat UUID fields.
- Empty native Characters have a valid empty character-info array.
- Upload acceptance precedes image-reference processing and metadata autosave.
- A saved metadata acknowledgement does not independently prove image ownership.
- The first project snapshot can retain the old name after metadata save.

The importer waits for metadata acknowledgement, then checks exact image
ownership and metadata through fresh reads. Only bounded read-only transitional
snapshots are rechecked. Wrong parent/project bindings fail immediately. No
upload or generation retry is performed. Earlier interrupted test journals are
preserved rather than silently completed or recreated.

## Offline verification

- Full regression immediately before the final stale-name repair: 4,973 passed,
  7 skipped; coverage 92.29%.
- After the final repair: 46 import/service tests passed.
- Whole-source strict types, lint and format passed.
- Repository hygiene, doc links, published-doc PII and mirror checks passed.
- Duplication proxy found no findings in the changed modules; it is not a hosted
  SonarCloud verdict.

## Limits

Only the named native Character import/replay path is live-proven by this
receipt. Paid video generation, migrated `@Character` terminal attribution,
remote LinkHub uploaded-file staging, other accounts and Windows are not proven.
The installed local runtime must retain its existing background-browser, batch
and caret fixes. A full independent council/hosted CI verdict is not claimed;
Luna completed test batches before reaching its usage limit. This preview is
not declared merge-ready or a stable release.
