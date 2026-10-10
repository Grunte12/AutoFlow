# Project reuse implementation plan

Goal: one selected brand/Character group reuses one existing Flow project.
Owner authorized implementation and cleanup; deletion remains gated on exact targets
and preservation of used media at 1080p. No bulk deletion by title.

Architecture: an opt-in, profile-local binding stores an existing project UUID and
selected Character UUID/name pairs. Both CLI and MCP resolve omitted project arguments
from it before creating a project or queueing work. Explicit project/project-name wins.
No Characters are attached automatically and no media is moved or deleted by binding.

Preimplementation review: lead-authored five-lens review, not an independent council,
following the owner's instruction to keep reasoning work with the lead. CAUTION:
atomic writes, fail-closed malformed state, per-profile isolation, and queue-time
snapshot are mandatory. Auth, browser transport and paid submission remain unchanged.

## Tasks

- [x] Red unit/BDD tests for binding, routing, isolation and malformed state.
- [x] Shared atomic project binding and native Character read verification.
- [x] CLI `project bind/context` and MCP twins; resolve image/video defaults on both.
- [x] Shipped project-management skill; docs and parity checks.
- [x] Offline gates and credit-free native bind/context verification.
- [ ] Push tested source and install without reverting unrelated runtime edits.
- [ ] Map used/unused remote projects, preserve used media at 1080p, then remove
      only verified unused targets. This is a separate destructive gate.

No additional paid generation is authorized by this plan. The one owner-approved
8-second Character test was already submitted and completed before this change.

## Scenario matrix

| Case | Expected behavior | Layer |
| --- | --- | --- |
| No binding | Preserve existing behavior | unit |
| Bound, omitted project | Reuse project for image/video | BDD, adapters |
| Explicit project or new title | Explicit request wins | unit, adapters |
| Queued request, binding changes later | Payload retains selected project | MCP |
| Broken JSON or unknown version | Configuration error, never create | unit |
| Other profile | Never borrow binding | unit |
| Ambiguous/missing/image-less Character | Refuse bind; keep old state | service |
| Different binding without replace | Refuse overwrite | unit |
| Same binding | Idempotent | unit |
| Cleanup without approved-asset mapping | Stop before deletion | skill |

Remote project merging/deletion and video upscaling are not claimed supported by this
binding feature. Probe their actual surfaces before performing cleanup.

## Verification

Offline final snapshot: 5015 passed, 7 skipped, coverage 92.12%; lint, format,
strict types, repo hygiene, docs links, website privacy/mirror and plugin mirror pass.
Luna independently ran 31 focused offline cases with an isolated temporary directory.
CLI live bind verified two existing Characters without writes to remote assets;
CLI context and installed native HTTP MCP bind/context agree. MCP initializes a3.
No generation was sent to test default routing: the owner's single paid Character
test was already consumed. Queue-time routing is verified offline across five modes;
this is not evidence of a new paid default-routing generation or likeness guarantee.
