# AutoFlow source preview

AutoFlow is an MIT-licensed fork of [ffroliva/gflow-cli](https://github.com/ffroliva/gflow-cli).
Upstream copyright/license notices are preserved. It is not affiliated with Google.
The package name `gflow-cli`, Python namespace `gflow_cli`, CLI `gflow`, and native
MCP names `gflow_*` are retained for compatibility. No AutoFlow PyPI package or
MCP Registry listing is claimed. Historical release evidence belongs to upstream.

## Install and update

Requires Python 3.11+, uv, Google Chrome and your own Google account with Flow access.
Use the fork source, not `uv tool install gflow-cli` (that installs upstream):

```bash
git clone --branch feature/autoflow-preview https://github.com/Grunte12/AutoFlow.git
cd AutoFlow
uv sync --frozen --no-dev
uv run --frozen --no-dev playwright install chromium
uv run --frozen --no-dev gflow auth login --browser chrome
uv run --frozen --no-dev gflow auth status
```

This checkout-local installation does not replace your globally installed tool.
Keep your previous source revision for rollback; do not delete your saved profile.
For reproducible deployment, review and pin an AutoFlow commit before installing.
To update, pull the chosen fork branch, review its changes, run `uv sync --frozen --no-dev`, then restart the
MCP client/server when no job is active. `gflow update` intentionally refuses source
installs. During preview, the package version is still upstream 0.82.1; identify
your build by its source revision, not that version alone.

## Native MCP first

Register this stdio server in your MCP client's settings. This JSON example is for
clients using `mcpServers` (for example Claude Desktop or Cursor); clients with
another config format use the same command/argument fields, not this JSON schema.
Use the absolute output
of `command -v uv` if your desktop app cannot resolve the shell PATH:

```json
{
  "mcpServers": {
    "autoflow": {
      "command": "/absolute/path/to/uv",
      "args": ["--directory", "/absolute/path/to/AutoFlow", "run", "--frozen", "--no-dev", "gflow", "mcp", "run"]
    }
  }
}
```

For read-only/no-spend onboarding append `--no-spend` to those arguments;
credit-spending generation tools are then not registered, including video batch.
Remove that flag only when generation is intended. Use `gflow_auth_status` first.
A failed Labs credit-balance query alone is not proof that the Flow UI login expired.
See [MCP](MCP.md) for transport, errors and permissions. LinkHub is optional, not an
AutoFlow dependency; remote agents must stage files on the server through their
host's authorized file-transfer mechanism.

## A short agent workflow

1. Read auth status; select an existing project and supplied reference files.
2. Call `gflow_generate_video_batch` with `dry_run=true`. Supply `shots`, `project`,
   `out_dir` and `profile`; reuse a stable `state_path` for real work. Native local
   file paths resolve against the server working directory, not the client VM.
3. After authorization, call once with the identical inputs and `dry_run=false`.
   This native tool completes synchronously; allow enough client timeout. A separate
   optional host adapter may return a queued job instead.
4. Inspect the structured result and use its verified files. An `indeterminate`
   outcome requires inspection/recovery, not another submission. `catalog_pending`
   means completed artifacts survived a catalog persistence problem; resume the same
   state to reconcile instead of regenerating.

Minimal native MCP arguments (replace the example UUID and server-local paths):

```json
{
  "shots": [{"id": "opening", "mode": "i2v", "prompt": "A gentle camera push-in.",
             "start_image": "/server/frames/opening.png"}],
  "project": "11111111-1111-4111-8111-111111111111",
  "profile": "my-profile",
  "out_dir": "/server/out/opening",
  "state_path": "/server/out/opening/video-batch-state.json",
  "model": "omni_flash", "aspect": "9:16", "duration": 10, "resolution": "720p",
  "dry_run": true
}
```

Batch accepts 1–4 supplied-image i2v/r2v shots, each count=1. It creates no images
or projects and never silently rewrites prompts/settings. See [VIDEO_BATCH](VIDEO_BATCH.md)
for the full manifest, validation and resume rules. Ten-second i2v controls are
Omni Flash specific; this does not establish 10-second r2v reference retention.

For a clip that already exists but is absent from the local catalog, call
`gflow_download_media` with the actual `media_id`, explicit `project` and `profile`.
This downloads and catalogs existing media; it does not generate or spend credits.
Content hashes are not Flow media IDs. Wrong account/project/kind conflicts are refused.
Fresh catalogs register the actual resolved profile before storing the recovered
asset; they do not invent project metadata. Batch ledger lock sidecars must be
regular, non-symlink, single-link files; unsafe sidecars are refused, not repaired
or followed automatically.

## macOS background mode

`GFLOW_CLI_BROWSER_BACKGROUND=true` minimizes only owned generation windows and
uses headed Chrome; it is **not headless**. Login remains visible. Requested
background mode fails closed if it cannot create/minimize its owned page, rather
than unexpectedly bringing Chrome forward. Set it false for visible troubleshooting.
See [Configuration](CONFIGURATION.md#gflow_cli_browser_background). No protection
from Google automation restrictions or account enforcement is promised.

## Verification and remaining gates — 2026-10-06

- Real-work existing-video recovery passed on macOS and through a remote native
  MCP consumer: outputs matched the original bytes/hashes and H264/AAC 720×1280,
  8-second metadata. No media was generated for those tests.
- A separate opt-in uncatalogued-media recovery regression passed against a fresh
  temporary catalog and verified an existing clip's exact bytes/hash. The repaired
  offline suite passed 4,948 tests with 7 documented skips and 92.47% coverage.
- Offline tests cover null-step responses, empty mention pickers, numeric/Thai
  duration controls, background-window safety, batch resume, catalog reconciliation
  and CLI/MCP parity. Live pre-submit 10-second i2v settings readback passed.
- **Not yet established:** a newly generated 10-second clip, all inherited Flow
  capabilities, new-user account coverage, or production stability. The intended
  production test received exact one-shot approval but returned an indeterminate
  outcome. Output and credit attribution remain unresolved; completed or
  unknown-outcome shots must not be regenerated merely to release code.
- No stable tag, PyPI publishing, registry publishing, unattended retries or
  quota/credit guarantees are part of this source preview.
- The fork retains token-free CI security checks and Python tests. Upstream's
  SonarCloud project is not ours: its hosted analysis is disabled for this fork
  until a separate project/token is configured. A skipped scan is not a Sonar
  quality-gate pass or a merge-ready review.

Flow's private interfaces can change. Keep local state, inspect failures, and use
existing-media recovery first. Follow the [disclaimer](../DISCLAIMER.md) and
[account safety guidance](ACCOUNT_SAFETY.md).
