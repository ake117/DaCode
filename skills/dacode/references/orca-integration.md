# Running DaCode under Orca (ADE)

Verified pilot (Oct 2026): `orca serve` (headless) → `repo add --path` →
`worktree create --repo path:<repo> --name <slug>` → `terminal create
--worktree name:<slug> --command '<dacode run …>'`. The full rig passes
end-to-end and the lesson lands in the vault.

To pair a browser or phone to the Orca server (web client on :6768) without the
mobile app, see the `orca-remote-access` skill.

## Rules

- **Single worktree owner.** Orca owns the task worktree; point DaCode at
  `--sandbox-root <orca-worktree>/.dacode/worktrees` (global flag — before the
  `run` subcommand) so trials live inside Orca's worktree and die with it.
- `terminal send` does not submit by itself — pass `--enter`. A lone
  `provider: unsupported` in the response is just agent-turn tracking on plain
  shells; the text still lands.
- `terminal read` without `--cursor` shows a stale window: capture `latest
  cursor` once, then poll `read --cursor <n>` for the exit marker. `tui-idle`
  false-positives on silent CLIs (the rig buffers output until the end) — do not
  use it for completion detection.
- Trial worktree names are reused per task slug: clean with
  `dacode sandbox clean` (plus `git worktree prune` for strays) or the next run
  dies with `SandboxError: worktree already exists`.
- `orcad` binds `0.0.0.0:6768` — reachable from the LAN; the pair code protects
  it, but check the host firewall on shared networks.
- Gate gotcha fixed in code (do not regress): the critic runs
  `sys.executable -m pytest -q -o addopts=` — repo `addopts` must not leak into
  the gate, and `with pytest.raises(...)` counts as an assertion.
