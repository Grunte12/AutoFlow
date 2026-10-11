# AutoFlow 0.83.0a10 Character chip hydration

## Scope and cause

An immediate Character selection could render an entity chip before its
`data-entity-id` was populated. The old count-only return skipped the wait used
by the detail/Add path. Final identity validation correctly refused the empty
ID before calling the generation submit routine.

Both selection paths now share a bounded wait for the expected chip count,
entity reference type, and nonempty ID. The existing ordered exact-ID check
remains authoritative. No tool schema, upload policy, checkpoint history,
Character image, project, or paid retry policy changes.

## Offline proof

- Two new regressions failed before the fix: delayed immediate-chip identity,
  and an identity that never hydrates.
- R2V tests pass with two image references preserved before two Characters.
- The affected transport, saved-Character and picker probe suites: 172 passed.
- Wrong reference type, wrong ordered entity IDs and timeouts still refuse.
- Ruff and strict Pyright pass using the worktree's Python environment.
- Broad offline run: 5,096 passed, 30 skipped, coverage 91.91%. Three wheel/build
  checks could not fetch Hatchling under restricted DNS; one HTTP transport
  check could not bind a loopback socket in the sandbox. The affected build,
  HTTP and version suites were rerun with those permissions: 19 passed.

## Authenticated MCP input proof, 2026-10-11

The registered `gflow_generate_video` MCP handler and real queue/client/composer
were exercised with two local image references and two existing saved
Characters: R2V, Omni Flash, 10 seconds, 9:16, 720p, count one. Each chosen
setting was read back. An in-page fetch/XHR guard intercepted the generation
RPC before network dispatch.

- Exactly one intercepted `MZZa6b` request with model key `abra_r2v_10s`.
- Both image media bindings and both exact ordered entity IDs verified.
- Prompt verified against the requested script.
- Generation network dispatches: zero. No video or credit-spending retry.
- The probe ended with its intentional configuration refusal after capture.
- Image reference uploads occurred; existing Characters and their slots were
  not edited. Private input IDs, prompts and account captures stay outside the
  published repository.

An earlier probe blocked prerequisite read RPCs along with generation and
could not capture a submit body. Its observer still saw zero generation
dispatches. The corrected probe permits prerequisite reads and continues to
intercept the known generation RPCs.

This proves client reference binding and serialization. It does not prove
backend image consumption, rendered likeness, or successful paid generation.
