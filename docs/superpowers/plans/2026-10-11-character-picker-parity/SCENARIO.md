# Character picker parity repair

## Decision and scope

The live native control proves Character row -> selected detail -> Add commits
the entity. The old production Enter-only path failed before submission and its
query cleanup deleted prior media. A paragraph-caret-only repair did not fix it.
Use the observed native confirmation for Characters, retaining media insertion
and exact prebilling UUID/kind checks. No auth, wire schema or MCP signature change.

Review lenses: shared transport keeps CLI/direct/queued MCP behavior aligned;
no new authentication or secret logging; bounded waits replace blind retries;
structural selectors are locale-independent (asset names are data); existing
Character entities remain unchanged. This is a localized repair, not a new transport.

## Must-cover scenarios

| Scenario | Expected result | Evidence |
|---|---|---|
| Append after two image chips | Caret inside last paragraph; images preserved | Unit + real browser |
| Character row opens detail rather than commits | Add confirmation commits exact entity | Unit + real browser |
| Previous Character detail is still visible | Wait for newly selected name, never use stale detail | Unit + real browser |
| Missing/duplicate name | Refuse before Add/submit | Unit |
| Add fails, wrong kind/UUID or reversed IDs | Refuse before billing | Unit |
| Native versus fresh production | Ordered rich tree, names/IDs, text, images, model/count/project equal | Guarded BDD e2e |
| Aspect/duration/resolution controls | Read checked UI controls; do not invent unknown wire enums | Guarded BDD e2e |
| Any accidental generation/upload/edit | Block before network dispatch | Probe guard + observer |
| Full spec differs in per-capture UUIDs | Repeat native control; retain paths; reject every other difference | Guarded BDD e2e + unit |

Only reference selection and composer text are changed. There is no creation,
upload, Character image edit, new video, cleanup or credit spend. Exact client
serialization cannot prove server-side Character image resolution or likeness.

## Execution checklist

- [x] Native interaction positively observed; full native rich tree retained privately.
- [x] Old fresh production path failed in guarded comparison before source repair.
- [x] Minimal shared Character confirmation repair.
- [x] Luna independent unit and real guarded two-arm regression.
- [x] Quality gates, owner branch push and scoped preview installation.
