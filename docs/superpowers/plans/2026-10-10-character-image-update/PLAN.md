# AutoFlow existing Character image replacement

Owner authorizes replacing portrait/full-body images through MCP, Luna tests,
and an owner-repository feature-branch push/source-preview install after proof.
No video/image generation, new Character/project, deletion, protected-branch
push, public registry release or upstream PR is included.

## Diagnosis and design

`mcp/tools.py` exposes import but no existing-entity image replacement. Existing
import creates an entity; reuse it for replacement would be incorrect. Baseline
Luna verification: 149 Character tests passed; 9 new MCP tests fail because the
replacement tool is absent. Preserve the existing project/entity and metadata.

Use one shared service for CLI and direct MCP, existing profile lease/client,
native slot controls, existing operation recorder, and fresh native readback.
Do not infer portrait/full-body ownership from arbitrary reference ordering.

Lead safety assessment (reasoning stays with the lead per owner's instruction):
CAUTION until live slot evidence. Architect: reuse client/recorder; security:
validate bytes and identifiers, return no local paths or signed URLs; performance:
one browser lease, sequential updates; surface parity: mirror CLI/MCP, no queued
generation route; simplicity: two optional inputs, no new registry or daemon.

## Must-cover scenarios

| Case | Required result |
|---|---|
| Portrait only / full-body only / both | Exact requested slots persist after reload |
| Wrong project/entity or ambiguous control | Refuse before upload |
| Missing/corrupt/oversize image, invalid UUID, no inputs | Refuse before browser startup |
| Metadata and untouched slot | Preserved, including name/personality/voice |
| Repeated operation UUID | Read-only reconciliation; never upload again |
| UUID reused with different bytes or target | Refuse |
| Upload acknowledgement without save/readback | Uncertain, not successful; no retry |
| Interruption between slots | Preserve checkpoints; no blind continuation |
| Another active browser job | Respect lease; do not kill its browser |

## Checklist

- [x] Discover current commands and run offline baseline.
- [x] Write and run red MCP input/response tests (9 expected failures).
- [x] Observe exact native slot replacement controls and binding/readback.
- [x] Shared operation-aware service and native driver; CLI/MCP twins.
- [x] Regression and browser-bound BDD, including read-only replay.
- [x] Luna runs offline cases; lead runs authorized live cases sequentially on one profile.
- [x] Lead review, quality gates, sanitized live receipt and mirrored docs.
- [x] Push only to owner's AutoFlow feature branch; install preserving dirty runtime.
- [x] Verify installed MCP tool/version and read-only replay.
- [x] Send final tool handoff after owner-branch push.

Delivery: verified implementation commit `822fb263` is on the owner's
`feature/character-image-update` branch. Local editable source installation
reports 0.83.0a4; installed LinkHub update/replay succeeded. The Affiliate chat
received the approved-image bindings and browser-hold release. No upstream PR,
merge, tag or registry release was performed.

## Live coordination

Affiliate has an active video batch on the same `linkhub` profile. No restart or
profile takeover is allowed while it is running. Read-only slot probe waits for
the lease to become free; offline tests can continue independently.

## Verified feedback and safety review

- Native portrait/body reference slots are indexes 0/1. The preview delete action
  detaches a Character reference; it does not delete the original project media.
- Initial live clear verification incorrectly expected the metadata-save RPC.
  Fresh readback proved the reference had cleared, with no upload performed. The
  driver now admits upload only after exact fresh state proves the chosen slot
  is empty and metadata/other slots are unchanged.
- The next real MCP both-slot update and CLI replay succeeded. A mismatched BDD
  Then sentence stopped the harness after that success; fixed and guarded with
  an offline exact-step test. The completed operation was reconciled read-only,
  not uploaded again: one live scenario passed in 116.45 seconds.
- CLI portrait-only replacement plus MCP replay passed in 159.95 seconds.
  The full-body binding and Character metadata fingerprint remained unchanged.
- LinkHub's generic artifact guard initially classified this metadata-only
  background job as interrupted. A new test reproduced it; the update-specific
  exemption passed all six Character-update adapter tests.
- Installed background body-only verification exposed a dialog hydration gap:
  the container appears before confirmation-button classes. A read-only probe
  proved the target unchanged; wait for the actual control before counting or
  clicking. The new regression failed before the fix; focused suite now 60 passed.
- No auth changes, generated media, new projects/Characters, or original-media
  deletion. Multi-slot replacement is not atomic: interruption can leave a
  cleared or partially replaced slot. Such an operation refuses blind replay.
- The shared upload-control lookup had the same hydration race after reference
  clear. Three red tests proved it; waiting for the actual unique control fixed
  it. Installed LinkHub restoration succeeded, preserving portrait and metadata.
  Luna's final offline run: 5,080 passed, 7 skipped; 92% coverage.

Lead review uses the owner's reasoning/volume split: decisions and evidence
judgment remain with the lead; Luna owns repeatable tests. This is not a public
release, upstream PR, merge, or multi-reviewer council approval.
