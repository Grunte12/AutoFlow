# AutoFlow installation and inherited distribution channels

## AutoFlow owner preview

The AutoFlow preview is distributed from [Grunte12/AutoFlow](https://github.com/Grunte12/AutoFlow),
not the upstream PyPI release. Use the owner preview branch that contains the needed
features; this agent-guide change is on `feature/autoflow-agent-guide`.

The curated plugin carries four user skills: `autoflow-mcp`, `project-management`,
`gflow-cli` and `video-production`. The `autoflow-mcp` entrypoint is short; its
Character reference guide loads only for that work. The compatibility plugin name
remains `gflow`. Install the executable from the same owner checkout/version as the
plugin. No additional runtime dependency is needed for the skill.

- Existing MCP connection: updated servers supply short instructions. Read
  `gflow://docs/mcp-guide` only when needed. MCP does not automatically install
  filesystem skills into arbitrary clients.
- Skill-capable client: install the curated plugin from the owner checkout, or
  copy `skills/autoflow-mcp/` into the client's skill directory, including its
  `references/` directory. The separate project-management skill is optional.
- Claude Code's plugin also registers the MCP server; the current Codex manifest
  supplies skills only, so keep its separately configured MCP connection.
- A hub may rename tools and hide schemas until selected. Use the published alias
  and current schema; a skill avoids repeated agent searches, not protocol discovery.

## Inherited upstream channels

The remainder describes the upstream distribution, not publication of this owner preview.

Every place you can install or find gflow-cli, and **what each one actually gives you**. The
channels differ more than they look: some hand you the whole CLI, some only the MCP server, and
one of them hands you a container that starts but cannot generate anything.

> **This page answers "what do I get?".** For whether a listing has been submitted, who is
> reviewing it, and what is blocked, see [DISTRIBUTION.md](DISTRIBUTION.md) — the maintainer's
> operational ledger. Keeping those two questions in separate files is deliberate: status rots
> weekly, what a channel delivers does not.

## The short version

**PyPI is the only authoritative source.** Everything else either installs *from* PyPI, points
at this repository, or is a catalog entry that helps people find it. If two channels ever
disagree, PyPI wins.

```bash
uv tool install gflow-cli                                    # recommended
uv tool run --from gflow-cli playwright install chromium     # one-time, ~150 MB
gflow auth login --browser chrome                            # one-time
```

That is the whole install. Every other row below is a convenience or a discovery surface.

## What each channel delivers

| Channel | CLI | Skills | MCP server | Notes |
|---|:--:|:--:|:--:|---|
| **[PyPI](https://pypi.org/project/gflow-cli/)** | ✅ | — | ✅ | Authoritative. `gflow`, `flow` and `gflow-cli` console scripts. |
| **Claude Code plugin (this checkout)** | — | ✅ 4 | ✅ | Needs `gflow` already on `PATH`. Ships **disabled**. |
| **Codex plugin (this checkout)** | — | ✅ 4 | — | Skills only; Codex loads no MCP server from it. |
| **MCP Registry** | — | — | ✅ | Metadata only — clients build `uvx gflow-cli mcp run` from it. |
| **Glama container** | — | — | ⚠️ | Starts and lists tools. **Cannot generate.** See [CONTAINER.md](CONTAINER.md). |
| **Catalogs** (Glama page, cursor.directory, MCP Market, skills.sh, awesome-lists) | — | — | — | Discovery only. They link here; they install nothing. |

The ⚠️ row is the one that surprises people, and it is covered in full in
[CONTAINER.md](CONTAINER.md).

## Install channels in detail

### PyPI — the real one

```bash
uv tool install gflow-cli     # or: pip install gflow-cli / pipx install gflow-cli
```

Three console scripts are installed, all the same entry point: `gflow` (what you type), `flow`
(short alias) and `gflow-cli` (named for the package, so `uvx gflow-cli mcp run` resolves — the
MCP Registry builds exactly that form and has no field for a different executable name).

Upgrades go through whichever installer put it there: `gflow update`. Source checkouts are
refused with exit `11` on purpose.

### Claude Code plugin

```
/plugin marketplace add ffroliva/gflow-cli
/plugin install gflow@gflow-cli
```

This checkout installs `autoflow-mcp`, `project-management`, `gflow-cli` and
`video-production` skills **and** registers the MCP server. It does
**not** install the CLI — `gflow` must already be on your `PATH`, and you must have run
`gflow auth login --browser chrome` once.

It ships **disabled deliberately**, because Claude Code starts a plugin's MCP servers on enable
with no prompt of its own, and this server spends your Veo credits. The full reasoning, the
`userConfig` acknowledgement, the `--no-spend` hard guarantee, and which git revision you get,
are all in **[MCP.md § 4](MCP.md#4-setup-instructions)** — not repeated here, because a
duplicated consent explanation is one that eventually contradicts itself.

Only **four** of the repository's skills ship in this checkout's plugin. The rest are maintainer workflow
(`release`, `check`, `pr-council-review` …) and would be noise in someone else's session. The
payload is generated, never hand-edited — see [`plugins/README.md`](../plugins/README.md).

### Codex plugin

```bash
codex plugin marketplace add .
codex plugin add gflow@gflow-cli
```

Skills only — select the bundled AutoFlow MCP skill for connected tool use. Codex reserves slash
commands for its own surface, so the `/gflow:*` spelling is intentionally not reproduced. The
Codex IDE extension does not load plugins; include the relevant `skills/<name>/SKILL.md`
directly there.

### MCP clients (no marketplace needed)

Any MCP client can run the server directly without any listing:

```bash
gflow mcp run              # stdio
gflow mcp run --no-spend   # stdio, credit-spending tools never registered
gflow serve                # Streamable HTTP at /mcp
```

Per-client configuration (Claude Desktop, Cursor, the HTTP daemon, authentication) lives in
[MCP.md § 4](MCP.md#4-setup-instructions).

## Discovery catalogs

These list gflow-cli so people can find it. **None of them installs anything** — each links back
to PyPI or this repository.

| Catalog | What it is |
|---|---|
| [Glama](https://glama.ai/mcp/servers/ffroliva/gflow-cli) | MCP directory with automated build + quality checks. Also builds the container — [CONTAINER.md](CONTAINER.md). |
| cursor.directory | Cursor's community MCP directory. |
| MCP Market, skills.sh | Listed us without being asked, by scanning the repository. |
| `awesome-mcp-servers` and friends | Curated GitHub lists. |

Because several of these scan the repository rather than read a manifest, they sometimes
advertise things we did not offer them — notably maintainer-only skills picked up by walking the
`skills/` directory. Where a catalog has a manual submission path, we use it.

## What no channel gives you

Worth stating plainly, because each of these is a reasonable thing to expect and none exists:

- **A hosted/remote gflow server.** Every generation runs a real Chrome session against *your*
  Google account. Hosting that would mean holding other people's Google sessions. There is no
  public Flow API or OAuth flow to build a legitimate remote server on.
- **A working Docker image.** See [CONTAINER.md](CONTAINER.md) — the container is a health-check
  artifact, not a product.
- **A Docker MCP Catalog entry, an Anthropic connector, or a ChatGPT app.** All three need
  something we cannot supply: shareable test credentials, an endpoint we own, or both.
  [DISTRIBUTION.md](DISTRIBUTION.md) records the specific reason per channel.

## Verifying a channel is really us

Anything claiming to be gflow-cli should trace back to **`github.com/ffroliva/gflow-cli`** or
**`pypi.org/project/gflow-cli`**. The project is MIT-licensed, so mirrors and forks are allowed —
but they are not us, and we cannot vouch for what they ship. If you find a listing that looks
wrong or stale, [open an issue](https://github.com/ffroliva/gflow-cli/issues).
