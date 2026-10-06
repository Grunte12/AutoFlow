# Local-image video batches

`gflow video batch` runs one to four supplied local-image shots sequentially,
using one headed Chrome client and one explicitly selected existing Flow project.
It does not create projects, generate replacement images, call prompt tools,
change prompts, or retry uncertain submissions. Each shot requests one output.

```json
{
  "project_id": "11111111-1111-4111-8111-111111111111",
  "defaults": {"model": "veo_3_1_fast", "aspect": "16:9"},
  "shots": [
    {
      "id": "opening",
      "mode": "i2v",
      "prompt_file": "prompts/opening.txt",
      "start_image": "frames/opening.png"
    },
    {
      "id": "reaction",
      "mode": "r2v",
      "prompt": "Hold the supplied composition while the subject looks toward camera.",
      "reference_images": ["references/subject.png", "references/room.png"]
    }
  ]
}
```

Replace the sample project UUID with your existing project's UUID. Relative input
paths resolve against the manifest's directory, not the current working directory.
Every shot needs a unique safe `id`, `mode` (`i2v` or `r2v`), and exactly one of
`prompt` or UTF-8 `prompt_file`. `i2v` requires `start_image` and optionally
`end_image`; `r2v` requires `reference_images`. Only supplied local files are accepted,
with the same format-header/size validation as uploads. Remote names, UUID image
references, characters, prompt tools and cross-shot generated inputs are not supported.

Optional defaults or per-shot overrides: `model`, `aspect` (`16:9`, `9:16`, `1:1`),
`duration`, `resolution`, `seed`, and `count` (must be `1`). Duration and resolution
are omitted by default, leaving Flow's controls untouched. Explicit model/settings
combinations use the existing video-request validation. Unknown keys fail preflight.

For Omni Flash supplied-frame i2v, explicitly request `duration: 10` and
`resolution: "720p"` when required. The shared selector identifies the complete
numeric duration domain, not English unit text. Thai `10 วินาที` is supported
and live settings/readback was verified without generation on Oct6. Ambiguous or
missing controls stop before submission; no automatic downgrade to 8 seconds.
The existing conservative r2v 8-second guard remains; this i2v evidence does not
prove 10-second Ingredients/reference retention.

```bash
gflow video batch shots.json --profile my-profile --out-dir ./out/shots --dry-run --json
gflow video batch shots.json --profile my-profile --out-dir ./out/shots --json
```

The dry run validates all rows without opening Chrome, uploading images, or writing
the ledger. A real run may spend account credits; the result reports `credits`,
`credits_before`, `credits_after`, and `credits_charged` as `null`, plus
`credits_reason`, because this runner does not measure the debit.

## Catalog reconciliation

Completed files are written to the durable ledger before catalog persistence. If the
catalog cannot be updated, the batch remains completed and reports `catalog_pending`
with media handles; the files are still usable. Resume with the same exact manifest,
profile, output/state paths: verified completed shots are skipped and only missing
catalog records are reconciled. Existing catalog metadata is preserved, and conflicting
project/profile/kind records are not overwritten. Do not erase the ledger, change a
shot ID or regenerate to repair a catalog warning.

Recover an already-generated clip missing from your local catalog without generating:

```bash
gflow data download MEDIA_UUID --project PROJECT_UUID --profile my-profile --out ./out
```

Native MCP equivalent: `gflow_download_media(media_id=MEDIA_UUID,
project=PROJECT_UUID, profile="my-profile", out_dir="./out")`. Supply actual Flow
media/project UUIDs, not content hashes or another machine's file paths.

## Resume and stopped runs

The private atomic ledger is `OUT_DIR/video-batch-state.json`; outputs are separated
by shot id. A nonblocking kernel lock prevents simultaneous use of the same ledger.
Intent is saved before browser work; call intent, `submit_attempted` and
`remote_started` are persisted before proceeding. Checkpoint-write failures are fatal.

Repeat the same command to resume. Fingerprints include prompt content, full image
content hashes, all request settings, runtime settings, profile and project identity,
and output directory. Completed files are verified by SHA-256 and skipped. Changed
inputs, missing/changed completed files, or malformed ledgers are rejected before
Chrome launches. Missing output never triggers regeneration.

Any ambiguous call stops later shots, reports `indeterminate`, and blocks automatic
resubmission, including after process interruption. A terminal remote failure also
stops the batch (`partial` if earlier shots completed, otherwise `failed`). Inspect
the existing Flow project and recover already-billed media rather than deleting the
ledger or rerunning a shot under a new id. The result preserves completed files and
known media handles; it contains no prompts, signed download URLs, or raw errors.
Non-completed CLI results exit with status 1; preflight/resume errors exit 11.

## MCP

The native `gflow_generate_video_batch` MCP tool invokes the same preflight and runner, not a new
server. A standalone AutoFlow install needs no LinkHub. In an optional LinkHub deployment,
remote owner-file-ID staging is handled by that tools-only adapter;
arbitrary remote filesystem paths are not a batch input mechanism. Stable MCP state
paths preserve idempotency across jobs, and completed partial outputs remain available
to their owner. Runtime results use `completed`/`not_started` shot-id lists and `files`
records containing `shot_id`, local `path`, `sha256`, `bytes`, and media/project handles.
`catalog_pending` contains shot IDs; the corresponding handles remain in `files`.

Remote file staging, file ACLs and optional queued-job adapters are host-integration
concerns, not native AutoFlow tools. Follow your adapter's contract; a client VM
path cannot identify a file on this server. Never change an operation/state ID to
evade an unknown submission outcome.

Offline tests establish runner and adapter safety, not live generation acceptance.
New paid generation smoke remains subject to explicit user authorization.

## Limits

This runner is not a replacement Flow daemon. Setup/locale
work is reused within one batch; a later batch may open a new client. The caller
selects an existing project, so this runner creates no new projects. It uses the
existing internal generation polling/downloader and scoped browser teardown.

Do not auto-omit requested settings or shorten prompts. Duration/resolution are
left untouched when omitted; account-specific availability is still checked by
the existing UI path when explicitly requested. Local dry-run checks assets and
request structure, not live account controls, authentication or quota. A prior
cookie-seed/Labs-route warning alone does not prove the Flow UI session expired.

Automatic wire retries and regeneration after deleting a completed
output are intentionally not implemented: a parser/network error may follow a
successful billed submit. Inspect/recover instead. No cross-machine SSH/box-path
protocol or arbitrary cleanup endpoint was added. Remote upload/download staging
and file ACLs belong to the integrating host. Credits remain explicitly unknown, with a reason, rather than
an unverified debit estimate. No upstream safety/auth/redirect boundary is relaxed.

The fork preserves the upstream 0.82.1 package identifier during source preview;
pin a reviewed AutoFlow commit to identify the installed repair. A matching version
number alone does not establish source parity. See [AutoFlow setup](AUTOFLOW.md)
for installation, native MCP and the verification limits.
