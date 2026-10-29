# Isolation — bubblewrap for trials and the gate

A worktree separates branches, not processes. Without isolation a trial (model
written code) can read `~/.ssh`, read the vault, write outside the checkout and
open sockets.

```bash
dacode run "<task>" --executor pi --isolate bwrap --isolate-network \
  --test-command "${VIRTUAL_ENV}/bin/python -m pytest -q -o addopts="
```

## What the policy does

| Aspect | Behaviour |
|---|---|
| Host filesystem | mounted read-only (`--ro-bind / /`) |
| Home | replaced by an empty tmpfs, then re-bound per path |
| Workspace | the only read-write bind |
| Network | `--unshare-net` by default |
| Environment | `--clearenv`, rebuilt from `BASE_ENV` + allow-list |
| Process | `--unshare-pid --unshare-ipc --unshare-uts --unshare-cgroup-try --die-with-parent --new-session` |

`allowed_env()` adds provider keys **only** when `network=True`, so an unrelated
`AWS_SECRET_ACCESS_KEY` in the shell can never reach a trial.

## Executor vs gate

- **Executor (Pi)** needs the network and its own binary/config: `PiExecutor`
  adds `~/.pi` and the resolved `pi` directory to the read-only binds, and the
  caller passes `--isolate-network`.
- **Gate (critic)** never gets the network: a test suite has no business opening
  sockets. It wraps the test command *and* the `-o addopts=` retry.

## Mount order matters

`--proc /proc --dev /dev --tmpfs /tmp` must come **before** the workspace bind:
with a repository under `/tmp` (a scratch clone, `tmp_path` in tests) the tmpfs
otherwise mounts over the workspace and bwrap dies with
`Can't chdir to /tmp/…: No such file or directory`. `TMPDIR` is pinned to `/tmp`
inside the sandbox because the host value may point into the home tmpfs.

`$HOME` and any ancestor of it are refused as read-only binds — binding one would
re-mount the entire home back over the tmpfs that hides `~/.ssh`.

## The gate gets its own policy

The executor needs the network and its provider key; the gate needs neither. They
are separate `IsolationPolicy` objects (`rig.isolation` vs `rig.gate_isolation`);
sharing one gave the test gate sockets whenever `--isolate-network` was on.

## The venv trap

A trial's venv usually lives under `$HOME`, which is now an empty tmpfs, and
`.venv/bin/python` is a symlink into a base install that may also live under
`$HOME`. Binding only the symlink leaves a dangling target:
`bwrap: execvp …: No such file or directory` and the gate reads 0 tests.

`interpreter_binds(command)` binds the interpreter, its venv root (found via
`pyvenv.cfg`), the `home =` base prefix from that file, and the resolved target.
`_bind_candidates()` resolves symlinks for any configured read-only path.

## Fail closed

- bwrap missing + `--isolate bwrap` → `RuntimeError` at rig construction with an
  actionable message (`--isolate none` is the explicit opt-out).
- An executor that cannot be sandboxed returns **exit 126**; the critic returns
  **exit 125** with "isolation unavailable" and the gate fails.
- Never "fall back to unsandboxed" silently: a green run that quietly had host
  access is worse than a failed gate.

## Verification recipe

```bash
dacode run "smoke" --llm stub --executor script --isolate bwrap \
  --script-command '{ echo "ssh=$(cat ~/.ssh/id_rsa >/dev/null 2>&1 && echo LEAK || echo BLOCKED)";
                      echo "env=$(cat ~/.hermes/.env >/dev/null 2>&1 && echo LEAK || echo BLOCKED)";
                      echo "net=$(curl -s --max-time 3 -o /dev/null -w %{http_code} https://example.com || echo BLOCKED)"; } > probe.log; echo ok > inside.txt' \
  --test-command "${VIRTUAL_ENV}/bin/python -m pytest -q -o addopts="
```

Expected: `ssh=BLOCKED env=BLOCKED net=BLOCKED`, `inside.txt` present (workspace
writable), and the suite still runs to completion inside the sandbox.
`dacode layers` reports the policy on a `5b. Isolation` row.

## Masking beats denying

`IsolationPolicy.hidden_files` binds `/dev/null` over a file: the parent stays
readable, the file is invisible. The orchestrator hides `<repo>/.env` (a `ro-bind /`
otherwise exposes it) and `~/.pi/agent/auth.json` — the provider key arrives through
`--setenv`, and a real Pi run still passes with the auth file masked
(`DACODE_PI_AUTH=bind` restores the old behaviour). `/run` and `/var/tmp` are empty
tmpfs, which removes `/run/user/$UID` sockets (D-Bus, ssh-agent, docker.sock).

`available()` runs a real namespace probe once: bwrap on `PATH` is not proof that
user namespaces work (Ubuntu 24.04 AppArmor, containers), and without the probe
every run failed with bwrap's exit 1 instead of failing closed.

## Isolation is the default

`DaCodeConfig.isolate` and `DACODE_ISOLATE` default to `bwrap`; `--isolate none` is
the explicit opt-out. A host without bubblewrap fails closed (126 executor, 125 gate)
instead of quietly running model-written code on the bare machine. Tests that mean
"run on the host" pass `isolate="none"` in the config they build — never inherit it.

Both policies must hide the same files. The executor's policy masked `<repo>/.env`
and the gate's did not, which left the repository's provider keys readable by the
tests that decide the verdict. When you add a hidden file, add it to
`_isolation_policy()` **and** `_gate_isolation()`.
