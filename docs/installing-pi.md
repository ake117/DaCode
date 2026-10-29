# Installing Pi

`pip install -e` installs DaCode only. **Pi is a separate Node.js program** — without
it on `PATH` the Pi executor exits `127` and the run looks like a mysterious failure.

```bash
curl -fsSL https://pi.dev/install.sh | sh     # pinned install; update with `pi update`
# or, if you manage Node yourself:
# npm install -g --ignore-scripts @earendil-works/pi-coding-agent

pi --version                                   # 1.2 or newer
```

Pi requires Node.js 22.19 or newer (the installer can install Node for you). The
managed install lives under `~/.pi/agent/` with a launcher symlinked onto `PATH` —
the sandbox resolves it to its real path, because a trial's home is an empty tmpfs
and a symlink into `$HOME` would dangle inside it.

## Authentication

```bash
pi auth check --provider openrouter
```

Under `--isolate bwrap` (the default) DaCode masks `~/.pi/agent/auth.json` inside the
sandbox and hands Pi the provider key through the environment instead. Use
`--isolate-network` and keep the provider key (`OPENROUTER_API_KEY`, or `GLM_API_KEY`
for the z.ai route) in the environment or in the target repository's `.env` — without
a key *or* network, the trial fails. Note the trade-off the current isolation makes:
`~/.pi` is mounted **writable** (pi 1.4 takes lock files next to everything it reads)
while `auth.json` is masked by an empty file, so credential reads return nothing
rather than failing and the key must come from the environment.

## Triage

| Symptom | Meaning |
|---|---|
| `exit 127` | Pi is not on `PATH` |
| `pi auth check` says `ready`, but `pi --print` answers **402** | the provider account is out of credits — Pi requests a large `max_tokens`, so a small balance is not enough. Cap it in `~/.pi/agent/models.json`, **under the provider key** (a top-level `modelOverrides` is silently ignored) — the recipe is in the [FAQ](FAQ.md) |
| `Unknown option: --system-prompt=` | a pre-1.4 DaCode against Pi 1.4+ — update DaCode; prompts travel as separate argv items now |
| `Credential store read failed ... EACCES` | an old mask binding `/dev/null` denies reads outright — update DaCode |

None of these are DaCode gate verdicts — they are environment failures that happen
before or around the rig.

## Where else Pi shows up

- The [FAQ](FAQ.md) covers the 402/`models.json` recipe in full.
- [SECURITY.md](../SECURITY.md) records what the sandbox hides from Pi — and the
  `~/.pi` writable trade-off above.
