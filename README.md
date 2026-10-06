# AutoFlow

AutoFlow is an independent, MIT-licensed fork of [ffroliva/gflow-cli](https://github.com/ffroliva/gflow-cli), with native MCP, sequential supplied-image video batches, recovery of existing clips, and minimized macOS generation windows. The Python package/import and `gflow` command names remain compatible with upstream.

**Source preview, not a stable release.** Download recovery has passed real-work MCP tests; 10-second i2v settings have passed live pre-submit readback, but a new 10-second generation has not yet been verified. See [AutoFlow setup and verification](docs/AUTOFLOW.md). Upstream release history and evidence below describe upstream, not a guarantee that every feature has been revalidated in this fork.

> Python CLI and MCP server for Google Flow. Drive [Veo](https://labs.google/fx/tools/flow) (image-to-video, text-to-video) and Imagen (text-to-image) from your terminal: scripted, batched, pipeline-ready.

[![CI](https://github.com/Grunte12/AutoFlow/actions/workflows/ci.yml/badge.svg?branch=feature%2Fautoflow-preview)](https://github.com/Grunte12/AutoFlow/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Status: source preview](https://img.shields.io/badge/status-source_preview-orange.svg)](docs/AUTOFLOW.md)

<!-- Gold sponsors appear here: filled by scripts/ci/update_sponsors.py, empty until there is one. -->
<!-- sponsors-gold:start -->

<!-- sponsors-gold:end -->

> ⚠️ **Read this before you install.** gflow-cli is **alpha and reverse-engineered — not affiliated with Google**. It drives a headed browser on *your own* Google Flow session, so treat it as your own account risk: automation is subject to Google's ToS, and endpoints or UI can change without notice. It works with **any Google account** that has Flow access, and every generation bills against your account's Flow credit allowance. Read the full [DISCLAIMER](DISCLAIMER.md).
>
> 🛡️ **"Will this get my account flagged?"** The honest, specific answer — what the tool does to stay unremarkable (headed real Chrome, randomised interaction timing, paced submissions), what it deliberately does **not** do (no proxies, no fingerprint spoofing, no pretending it isn't automation), what you can tune, and what we cannot promise — is in [docs/ACCOUNT_SAFETY.md](docs/ACCOUNT_SAFETY.md).
>
> 💳 **What failure can cost you.** Generation may consume your Flow allowance; the account UI is authoritative for the current cost. AutoFlow records batch submissions locally and stops on uncertain outcomes rather than automatically resubmitting. A timeout is not proof that Google did not bill or finish a clip. See [KNOWN_ISSUES](KNOWN_ISSUES.md) for the current risk list.
>
> 🌐 **Headed browser today.** gflow drives Flow through a persistent Playwright Chromium profile, because Google's auth and reCAPTCHA gates require it. The [Architecture](#architecture--current-limitations) section shows where you can help.

## Upstream capabilities

You have a Google account with Flow access, you have Veo credits, and you run real batch work. gflow-cli gives you:

- **Batch generation.** Loop prompts straight from the shell: `for p in $(cat prompts.txt); do gflow image t2i "$p"; done`. Image batching plus `gflow video t2v` / `i2v` / `r2v` all ship today, and `gflow video extend` continues an existing clip past Flow's 8s ceiling.
- **Consistent subjects.** `gflow character create` mints a Flow Character (face and body reference) so the same person appears from one generation to the next.
- **Prompt tools.** `--tool creative-director` rewrites a terse prompt into a vivid one (Google's 5-component formula) before generating — on any command. Bring your own with [My Tools](docs/TOOLS.md).
- **Pipelines.** Wire Veo into your content automation, AI-video stack, or batch experiments.
- **Terminal-native.** After one `gflow auth login`, you stay in the shell. No clicking through dialogs.

Same Veo and Imagen models, same quality, same billing against your own Google account, now programmatic.

## Install this fork

```bash
# 1 · Install AutoFlow from its reviewed source branch (not the upstream PyPI package)
git clone --branch feature/autoflow-preview https://github.com/Grunte12/AutoFlow.git
cd AutoFlow
uv sync --frozen --no-dev
uv run --frozen --no-dev playwright install chromium
# Update by reviewing/pulling this fork, reinstalling the same way, then restarting MCP.
# gflow update intentionally refuses source installs.

# 2 · Authenticate (one-time, opens a real Chrome window)
uv run --frozen --no-dev gflow auth login --browser chrome

# Check auth without spending credits; a missing Labs balance token alone is not logout
uv run --frozen --no-dev gflow auth status

# 3 · Register native MCP in your client (see docs/AUTOFLOW.md)
uv run --frozen --no-dev gflow mcp run
# Optional local validation of your supplied-image manifest; no browser or generation:
# gflow video batch shots.json --profile my-profile --out-dir ./out/shots --dry-run --json
```

Outputs land under `$GFLOW_CLI_OUTPUT_DIR`, or you can route them to S3, MinIO, or Google Cloud Storage with [`GFLOW_CLI_STORAGE_URI`](docs/EXTERNAL_STORAGE.md). The first call takes 30 to 90 seconds while Chromium warms up; later calls reuse the warm session.

> **Why `--browser chrome`?** It is the only strategy that marks the profile as a real-Chrome profile, which is what later generation runs open it with. The default `auto` picks it whenever Chrome is installed — see [docs/AUTHENTICATION.md](docs/AUTHENTICATION.md).

> **Installing from a local checkout?** `uv tool install <path>` **ignores `uv.lock`** and resolves dependencies from the `pyproject.toml` ranges, so it can hand you a Playwright build this project has never tested. Playwright ships the browser driver, and an untested minor can wedge a generation silently. Carry the locked version explicitly:
>
> ```bash
> uv tool install --force --with playwright==1.61.0 .
> ```
>
> Installing from PyPI (`uv tool install gflow-cli`) is unaffected — the published range is upper-bounded. Check what you actually have with `uv run --frozen --no-dev python -c "import importlib.metadata as m; print(m.version('playwright'))"`.

For the full 10-minute walkthrough with troubleshooting and multi-account setup, see **[USER_GUIDE: Journey 1](docs/USER_GUIDE.md#journey-1--first-time-setup-10-minutes)**.

## Upstream examples

One command in, real Flow output back. Left: `gflow image t2i` generating a photorealistic scene in your library. Right: a frame-to-frame transform.

![gflow-cli examples: text-to-image generation, and a before/after frame transform](https://raw.githubusercontent.com/ffroliva/gflow-cli/main/docs/assets/examples.webp)

## Upstream demo

![gflow image t2i runs a single 9:16 prompt, streams structlog output, and writes a PNG to disk](https://raw.githubusercontent.com/ffroliva/gflow-cli/main/docs/assets/example-run.gif)

A single `gflow image t2i "..." --aspect 9:16 --model nano2` call against a logged-in Flow profile. The terminal streams the run's `structlog` JSON, then lists the written PNG. Chromium drives the Flow editor silently in the background.

Reproduce the recording with [`scripts/record_demo.ps1`](scripts/record_demo.ps1) (Windows, OBS, ffmpeg, gifski). More formats, including the side-by-side split-screen: **[docs/DEMOS.md](docs/DEMOS.md)**.

## Documentation

[**docs/INDEX.md**](docs/INDEX.md) is the master routing layer. Quick links:

| Topic | Read |
|---|---|
| **AutoFlow fork** | [Setup, MCP, updates and verification limits](docs/AUTOFLOW.md) · [Supplied-image video batches](docs/VIDEO_BATCH.md) |
| 🎯 **Getting started** | [User Guide](docs/USER_GUIDE.md) · [Usage](docs/USAGE.md) · [Configuration](docs/CONFIGURATION.md) |
| **Storage & catalog** | [External Storage](docs/EXTERNAL_STORAGE.md) · [Data Layer](docs/DATA_LAYER.md) |
| 🎭 **Characters** | [Characters](docs/CHARACTER.md), reusable subjects (`gflow character`) |
| 🤖 **Agentic & automation** | [Instructions](docs/INSTRUCTIONS.md) (`gflow instructions`, persistent brief cards) · [Movie](docs/MOVIE.md) (`gflow movie`, multi-scene manifests) · [Tools](docs/TOOLS.md) (`--tool`, prompt rewriting) · [MCP server](docs/MCP.md) (`gflow mcp run` / `gflow serve`) |
| 🔐 **Auth & sessions** | [Authentication](docs/AUTHENTICATION.md) · [Known issues](KNOWN_ISSUES.md) |
| 📣 **Where to install from** | [Marketplaces](docs/MARKETPLACES.md) (every channel and what each actually delivers) · [Container](docs/CONTAINER.md) (why the image introspects but cannot generate) |
| 🏗️ **Internals** | [Architecture](docs/ARCHITECTURE.md) · [Security](docs/SECURITY.md) · [Debugging](docs/DEBUGGING.md) |
| 📦 **Releases** | [Changelog](CHANGELOG.md) · [Roadmap](ROADMAP.md) · [Release protocol](RELEASE.md) · [Project status](docs/PROJECT_STATUS.md) |
| 🤝 **Contributing** | [Contributing](CONTRIBUTING.md) · [Development](docs/DEVELOPMENT.md) · [GitHub workflow](docs/GITHUB.md) |

## For AI agents & LLMs

gflow-cli ships four agent entry points. Pick the one your tool reads first.

| File | Audience | Tools |
|---|---|---|
| [**AGENTS.md**](AGENTS.md) | Universal coding-agent spec | Cursor · Codex · Aider · Antigravity · Jules · Devin · Windsurf · Zed · Warp · opencode · Copilot |
| [**CLAUDE.md**](CLAUDE.md) | Claude Code's auto-loaded memory | Claude Code |
| [**llms.txt**](llms.txt) | LLM-readable summary (llmstxt.org format) | Paste into ChatGPT, Claude, or Gemini to onboard the model |
| [`skills/gflow-cli/SKILL.md`](skills/gflow-cli/SKILL.md) | Claude Code Skill | Symlink into `~/.claude/skills/` |

### Upstream plugin (Claude Code)

For AutoFlow, use native MCP from [AutoFlow setup](docs/AUTOFLOW.md); the block below installs upstream.

One step, and you get the `gflow-cli` and `video-production` skills plus the MCP server:

```
/plugin marketplace add ffroliva/gflow-cli
/plugin install gflow@gflow-cli
```

For this fork, use `/plugin marketplace add Grunte12/AutoFlow#feature/autoflow-preview` instead of the upstream marketplace command above, or register native MCP directly using [AutoFlow setup](docs/AUTOFLOW.md). The upstream marketplace installs upstream, not these repairs.

The plugin ships **disabled**. Claude Code starts a plugin's MCP servers automatically once a
plugin is enabled, with no prompt of its own — and this server drives your own Google account,
where Veo video generation bills your credits. So installing it starts nothing, and enabling it
is a deliberate act. Images and composition are free; only video spends. For a hard guarantee,
register the server yourself with `gflow mcp run --no-spend`, which never registers the
credit-spending tools at all. See [docs/MCP.md](docs/MCP.md) for the details, including which
revision `/plugin marketplace add` gives you.

Codex users: `codex plugin marketplace add .` then `codex plugin add gflow@gflow-cli`.

Onboard any agent in one line. Paste this into your agent of choice:

> *"Read [AGENTS.md](https://github.com/ffroliva/gflow-cli/blob/main/AGENTS.md) and [docs/INDEX.md](https://github.com/ffroliva/gflow-cli/blob/main/docs/INDEX.md), then help me with my Flow batch."*

## Architecture & current limitations

```text
gflow CLI  →  Provider (interchangeable)  →  Flow (ui_automation) / Mock (tests) / [planned: Official Veo]
                                              ↓
                                      Playwright Chromium (headed — login AND generation, by default)
                                              ↓
                              aisandbox-pa.googleapis.com  (Google's private Flow API)
```

**Current transport:** `ui_automation` drives Flow through a persistent Playwright Chromium profile. Historical `LIVE_VERIFICATION_*` files describe upstream releases. This fork's narrower verification and remaining gates are in [AutoFlow setup](docs/AUTOFLOW.md).

**Two Flow frontends:** Google is moving accounts from `labs.google` onto `flow.google.com` ([#639](https://github.com/ffroliva/gflow-cli/issues/639)) — same product, different widget toolkit and wire protocol (`batchexecute` instead of `aisandbox-pa`). The migrated driver covers text-to-video, image-to-video from a local start frame, reference-to-video from local files, text-to-image, and image-to-image from local files. Image generation supports Nano Banana 2 / Pro, the four aspect ratios measured on that host (16:9, 4:3, 1:1, 9:16), and counts 1–4; an existing project is required at the transport boundary. UUID/entity references, instructions, Imagen 4, and the rest of the matrix keep the labs driver until ported (`GFLOW_CLI_FLOW_HOST`, see [CONFIGURATION](docs/CONFIGURATION.md#gflow_cli_flow_host)).

**What's blocked:** a pure HTTP transport for video generation. The video upload endpoint returns HTTP 401 under non-Chrome browsers plus a reCAPTCHA mint we cannot reproduce headlessly. Three earlier HTTP strategies (`evaluate_fetch`, `bearer`, `sapisidhash`) live under `src/gflow_cli/api/transports/experimental/` for research, off the production path.

**How you can help:** if you have driven `aisandbox-pa.googleapis.com` from outside a real Chrome session, or you understand Google's anti-bot stack here, please open an issue. A working REST transport would unlock serverless deployments, true horizontal concurrency, and roughly 10x the project's reach. Details: [docs/ARCHITECTURE.md § Headed-browser dependency](docs/ARCHITECTURE.md#headed-browser-dependency--current-limitation).

## Project status

**Alpha.** Image (t2i, i2i, upload, upscale, batch) and video (t2v, i2v, r2v, chain, extend) run end-to-end on `ui_automation`, with a 5-model Veo picker plus `--duration` and `--count`. Beyond single generations: `gflow movie` renders multi-scene manifests, `gflow instructions` manages persistent Agent-Mode brief cards (credits-free), `gflow character` handles reusable subjects, `gflow scene` does credit-free server-side stitching, `--tool` applies prompt-rewriting tools, and an MCP server (`gflow mcp run` stdio / `gflow serve` Streamable HTTP) exposes the core surface to AI agents with a CI-enforced CLI↔MCP parity contract.

Full milestone history lives in [CHANGELOG.md](CHANGELOG.md). Where the project is heading: [ROADMAP.md](ROADMAP.md).

## Support upstream gflow-cli

gflow-cli is built and maintained by one person. Every release is verified against real Google Flow, which spends real AI credits, and breakages get fixed fast because people run it in their pipelines. Sponsorship pays for both.

[![Sponsor $5 one-time](https://img.shields.io/badge/☕_sponsor-$5_one--time-ea4aaa?logo=githubsponsors&logoColor=white)](https://github.com/sponsors/ffroliva/sponsorships?frequency=one-time&amount=5)
[![Sponsor $5 a month](https://img.shields.io/badge/💖_sponsor-$5_a_month-ea4aaa?logo=githubsponsors&logoColor=white)](https://github.com/sponsors/ffroliva/sponsorships?frequency=monthly&amount=5)

Relying on gflow-cli at work? The monthly company tiers put your logo here, and Silver and above also get priority issues. All tiers and what each one gets: [docs/SPONSORS.md](docs/SPONSORS.md).

Patched gflow-cli in your fork? Please [open an issue](https://github.com/ffroliva/gflow-cli/issues) or a pull request — a fix that lands upstream helps everyone.

### Hall of fame

<!-- sponsors:start -->
No sponsors yet. <a href="https://github.com/sponsors/ffroliva/sponsorships?frequency=one-time&amp;amount=5">Be the first</a> — every public sponsor is listed here.
<!-- sponsors:end -->

## License & legal

[MIT License](LICENSE) © 2026 Flavio Oliva (`ffroliva`). The MIT license covers `gflow-cli`'s code only. It grants no rights to Flow, Veo model output, or any Google service. Google's own terms (Labs Additional Terms and any plan-specific subscription terms) govern your generations. See the [DISCLAIMER](DISCLAIMER.md).

## Acknowledgements

- [`edge-tts`](https://github.com/rany2/edge-tts), design inspiration for community SDKs over private cloud APIs.
- [`googleapis/python-genai`](https://github.com/googleapis/python-genai), the official Veo SDK that a future provider release may alias.
- [Keysight, *Google Labs – Flow AI with Veo3: A Network Traffic Analysis*](https://www.keysight.com/blogs/en/tech/nwvs/2025/08/04/google-flow-ai-har-analysis), an independent capture that helped validate the route patterns.

---

## Upstream stats

[![GitHub stars](https://img.shields.io/github/stars/ffroliva/gflow-cli?style=social&cacheSeconds=3600)](https://github.com/ffroliva/gflow-cli/stargazers)
[![GitHub forks](https://img.shields.io/github/forks/ffroliva/gflow-cli?style=social&cacheSeconds=3600)](https://github.com/ffroliva/gflow-cli/network/members)
[![GitHub watchers](https://img.shields.io/github/watchers/ffroliva/gflow-cli?style=social&cacheSeconds=3600)](https://github.com/ffroliva/gflow-cli/watchers)
[![GitHub issues](https://img.shields.io/github/issues/ffroliva/gflow-cli?cacheSeconds=3600)](https://github.com/ffroliva/gflow-cli/issues)
[![GitHub pull requests](https://img.shields.io/github/issues-pr/ffroliva/gflow-cli?cacheSeconds=3600)](https://github.com/ffroliva/gflow-cli/pulls)
[![GitHub last commit](https://img.shields.io/github/last-commit/ffroliva/gflow-cli?cacheSeconds=3600)](https://github.com/ffroliva/gflow-cli/commits/main)
[![GitHub repo size](https://img.shields.io/github/repo-size/ffroliva/gflow-cli?cacheSeconds=3600)](https://github.com/ffroliva/gflow-cli)
[![PyPI downloads](https://static.pepy.tech/badge/gflow-cli/month)](https://pepy.tech/project/gflow-cli)


Star history and funding for upstream are available from [ffroliva/gflow-cli](https://github.com/ffroliva/gflow-cli).
