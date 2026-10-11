# Saved-Character guard diagnostics

Scope: diagnostic-only addition on top of AutoFlow 0.83.0a10. No version bump,
schema change, new request, parser change or relaxation of billing guards.

## Scenario and blast radius

- Valid first saved-Character submit: log RPC identity and body digest, continue.
- Second known submit after attribution: log adopted IDs and duplicate reason,
  abort exactly as before.
- Non-submit RPC carrying R2V state: preserve existing abort behavior and record
  `known_submit_rpc=false` to make the disputed carrier observable.
- Payload includes private token/prompt: neither appears in diagnostic logs.

These cases execute the actual production guard through the existing fake-route
harness. They describe our logging/routing behavior, not a new claim about what
Flow sends. The third case is synthetic; the offending production RPC remains
unknown until captured. No production submit was used for verification.

Both CLI and queued MCP reach `MigratedComposer.submit_and_observe`; no public
parameters, exceptions, checkpoint policy or retry flags changed. Formal transport
redesign/predict is not applicable: the action envelope and carrier predicate are
unchanged. No generalized logging framework or storage was added.

## Verification

- Before logging addition: three parametrized cases failed because diagnostic
  records were absent; existing rejection behavior remained intact.
- After: targeted suites passed 168 tests, independently rerun by Luna.
- Wider transport suite: 1,262 passed, 21 skipped; modified composer module
  coverage 86.87% (80% gate passed).
- Whole-source pyright: zero errors/warnings.
- Ruff check and format check: clean across all source/tests (553 files).
- Repository hygiene, documentation links, published PII check, council-memory
  check and regenerated website-doc mirror: passed.
- The idle installed MCP process was restarted. Initialization reported
  0.83.0a10, and the installed editable source contained the new diagnostic event
  and the unchanged admission/abort predicate. Zero tool calls were made.
- After discarding the Hub's stale upstream session with a graceful restart,
  actual Hub video-schema discovery succeeded and the read-only auth-status
  tool returned authenticated. No video tool was called.

The new event has not yet been observed on a real credit-spending submit.
An owner-authorized next run may supply that evidence; this document does not
authorize generation or assert the underlying duplicate issue is fixed.
