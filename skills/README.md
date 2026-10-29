# Skills — the agent-facing operating manual

[`dacode/`](dacode/) is the Hermes Agent skill for *driving* this rig: when to
reach for it, the command shapes, the first-week failure triage (127 / 402 / gate
findings), and reference notes on isolation, gate integrity, external audit
packs, and the MCP server. If you run DaCode through an agent, handing the agent
this skill beats handing it the README.

The **canonical copy lives in the `ake117/hermes-custom-skills` repository** and is
what gets installed into an agent's skill directory. This snapshot keeps the
manual versioned next to the code it describes; it is not edited here — changes
flow from the skills repo, and a snapshot that drifted is a bug, not a fork.
