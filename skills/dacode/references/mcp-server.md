# MCP server — share the rig's memory with other agents

```bash
dacode --vault <vault> mcp                     # semantic search if an embedder is configured
dacode --vault <vault> mcp --keyword-only      # no network calls
```

Stdlib only: JSON-RPC 2.0 over stdio, protocol `2025-06-18`, one JSON object per
line. `--vault` is a **global** flag: it goes before the `mcp` subcommand
(`dacode --vault PATH mcp`, not `dacode mcp --vault PATH`).

## Tools

| Tool | Arguments | Returns |
|---|---|---|
| `memory_search` | `query`, `limit` (≤20) | lessons from the vault: title, snippet, path, score |
| `run_history` | `query`, `limit` (≤50) | FTS hits over past runs/variants/picks |
| `failures` | `task?`, `limit` (≤100) | failed variants with scores |
| `stats` | — | counts, pass rate, avg/slowest variant, skipped tests |
| `retro` | `days` (≤365), `task?` | the retro report as JSON |

Handlers take a plain dict and return a dict; an exception is reported as a tool
result with `isError: true` rather than crashing the server. Unknown methods get
`-32601`, unknown tools `-32602`, malformed lines `-32700` and the loop carries
on — so a client sending garbage does not kill the session.

## Registering with a client

Hermes (`~/.hermes/config.yaml`):

```yaml
mcp_servers:
  dacode-memory:
    command: /path/to/DaCode/.venv/bin/python
    args: [-m, dacode.cli, --vault, /path/to/vault, mcp, --keyword-only]
    enabled: true
```

Working order: back up the config (`cp ~/.hermes/config.yaml ~/.hermes/config.yaml.bak-<tag>`),
edit the `mcp_servers` block directly, then prove it:

```bash
python3 -c "import yaml;print(list(yaml.safe_load(open('$HOME/.hermes/config.yaml'))['mcp_servers']))"
hermes mcp test dacode-memory     # expect: Connected, 5 tools discovered
```

`hermes mcp add` is interactive and its `--args` handling swallows multi-token
arguments (`-m dacode.cli` arrives mangled), and a failed connect only *offers*
to save the config — so a written entry you never tested is the normal outcome.
Edit the block and let `hermes mcp test` be the proof. The server is keyed by its
YAML key: registering twice leaves two entries, one of which serves stale args.

The `command` must be the venv interpreter that has `dacode` importable (verify
from an unrelated directory: `cd /tmp && /path/.venv/bin/python -c "import
dacode"`), because the client launches it with its own cwd.

Pi or any other stdio MCP client: same command and args. Tools appear as
`mcp__dacode_memory__*` in the client's tool list after a reload.

## Manual smoke test

```bash
printf '%s\n' \
 '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' \
 '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"stats","arguments":{}}}' \
 | dacode --vault <vault> mcp --keyword-only
```

A live session should return the store counts, real vault hits and a retro
report. If `tools/call` returns an error, check `--vault` placement first.

`retro` inside the server honours `DACODE_RUNLOG`; before that fix it read only
the default path, which made the tool disagree with the CLI.
