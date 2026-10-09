# Scenario: canonical Character and pre-submit diagnostics

## Coverage map

D1/D2: retain auth and lease; do not change token minting. D3/D9: native upload and identity observer contracts need real browser evidence. D4/D6: uncertain batches and import resume must never duplicate or cross input identities. D5: one client, serialized composer. D7/D12: exit 11 remains, closed structured proof only. D8/D11: image magic/size, Unicode paths and source hashes. D10: preserve headed default. D13: CLI, direct MCP, queued video and LinkHub file-ID staging are distinct paths.

| Case | Severity | Expected result | Evidence |
|---|---|---|---|
| Known guard rejects before any submit | High | Explicit not_submitted proof; requested settings retained | Unit plus live refusal |
| Ordinary ConfigurationError or click timeout | Critical | No no-spend proof; no automatic retry | Unit |
| Omni 10s not verified for R2V | Critical | Refuse safely; do not claim Flow-wide impossibility or downgrade | Unit plus controls probe |
| Batch has a later incompatible row | Critical | Validate all rows before first billed operation | Batch integration (follow-up) |
| Native Character import | Critical | Original bytes bound, zero media generation | Real browser E2E |
| Interrupted import with changed sheet | Critical | Reconcile by operation/source identity; never regenerate | Service integration |
| Character chip with null submit response | Critical | Do not adopt first project output or remove guard | Transport integration/E2E |
| Diagnostic includes prompt, path or signed URL | Critical | No unsafe values in structured fields | Unit |
| MCP accepted input absent in worker | Critical | Stable entity IDs and names round-trip unchanged | MCP/codec integration |

Known issue: migrated Character list uses retired projectInitialData; video entity observation is unported. This plan does not interpret either as absence of Flow's native feature.
