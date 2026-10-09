# Predict review

Five independent read-only reviews on the isolated source baseline:

| Persona | Verdict | Main constraint |
|---|---|---|
| Architect | CAUTION 8/10 | Upload workflow IDs are promising, not proof of native Character slot binding |
| Security/reCAPTCHA | CAUTION 6/10 | ConfigurationError alone is not a pre-submit/no-spend witness |
| Performance/Playwright | CAUTION 8/10 | One owned client and serialized composer; no per-video re-upload |
| CLI/MCP UX | CAUTION 6/10 | Additive parity and stable IDs; read back personality, do not imply native creation exists |
| Devil's Advocate/YAGNI | CAUTION 6/10 | Observe native Upload first; no new registry or synthetic portrait fallback |

References: `api/client.py` upload_image/create_entity/patch_entity; `services/character_create.py` generated portrait saga; `api/transports/migrated_composer.py` duration guard/entity binding/result observer; `worker/codec.py` reference entity fields; `KNOWN_ISSUES.md` migrated-host and identity-drop history. The configured batch runner emits attempted before a transport can reject; its conservative unknown outcome must not be widened into retry permission.

Decision: implement narrow safe diagnostics now; keep import and actual billed reference reuse behind live evidence gates.
