# Memory — backends, embeddings, lesson notes

## DaCode owns its memory; other agents are adapters

`local` is the default backend: embeddings from any OpenAI-compatible
`/v1/embeddings` endpoint (Ollama, llama.cpp, vLLM, LM Studio, OpenAI, Gemini
compat, …) stored in `~/.local/state/dacode/embeddings.db` — exact cosine in
SQLite, no ChromaDB, no vector service.

- `hermes` ships as one **example** adapter (subprocess → external search script,
  JSON `{rel_path, title, similarity, excerpt}`).
- `DACODE_SEMANTIC_BACKEND=module:factory` lets anyone plug their own.
- `auto` order is local → hermes → keyword, so a public clone works with zero
  config and never depends on another agent being installed.

Keep it that way: a rig that needs someone else's agent is not shareable.

## The local backend speaks the OpenAI `/v1/embeddings` shape only

No native Gemini/Anthropic adapter — but that is enough in practice. Gemini's
OpenAI-compat endpoint (`.../v1beta/openai`, model `gemini-embedding-2`) returns
one vector per input for a string list **and** honours `dimensions`, so
`DACODE_EMBED_DIMS=768` keeps the store at 768 instead of the model's 3072
default. The client fails loudly if a provider ignores `dimensions`.

Key resolution: `DACODE_EMBED_API_KEY` → `OPENAI_API_KEY` → `GEMINI_API_KEY` →
`GOOGLE_API_KEY`. Only an allow-listed set of names is read from the target
repo's `.env` (provider keys plus the embedding *model* knobs); base URL and
vault location are deliberately excluded, because either one lets a checkout
redirect where prompts and memory go. See `gate-integrity.md` → "Hostile
repository".

Provider-specific details: `embedding-providers.md` beside this file.

## Indexing

```bash
dacode memory backends                 # OK/off per backend + detail
dacode memory index                    # embed changed notes (incremental by mtime)
dacode memory index --rebuild          # re-embed everything
```

- **`memory index` refuses to mix embedding models.** Rows carry `model`; a
  different model without `--rebuild` raises. Two models in one store give
  plausible-looking but meaningless scores.
- ~583 notes index in ~2.5 s with `gemini-embedding-2` (batch 32); the second run
  embeds 0 and prunes deleted notes.
- The suite never reaches an embedder: conftest sets `DACODE_SEMANTIC=off`,
  `DACODE_EMBED_DB=<tmp>`, and deletes every `DACODE_EMBED_*` var. A test that
  exercises local retrieval injects `embedder=` and `store=` explicitly.

## Generated lesson notes

Lessons are written to `<vault>/Projects/DaCode/Lessons/` after a passing run.

- **Redaction is at the boundary now.** `dacode/redact.py` replaces provider tokens
  and known key values in `runlog.record`, in the SQLite mirror and in the lesson
  text, and the state directory is `0700`. A key echoed into a task string, or
  instructions injected by
  a hostile repository, survive into the vault and into later runs of *other*
  repositories. That is a known open item — do not describe lessons as sanitised.

- **Machine-agnostic.** `_build_lesson` writes only the trial worktree *name*,
  never the absolute path — scratch worktrees are ephemeral and per-machine, and
  the vault is synced.
- **Frontmatter scalars must be JSON-quoted.** A task string containing `: `
  (e.g. `...bands.py: band(value, lo, hi...)`) written unquoted parses as a
  nested mapping: `yaml.safe_load` raises `mapping values are not allowed here`
  and the note disappears from Obsidian properties while `git status` looks
  clean. Emit `title` and `source_task` via
  `json.dumps(value, ensure_ascii=False)` (valid YAML double-quoted style, keeps
  Thai readable). Fix the *writer*, not just the broken note; then round-trip a
  nasty sample through `ingest()` and assert `safe_load(...)` returns the
  original strings.

## Retrieved paths are untrusted input

Every relative path this layer receives — a semantic hit from a backend, a row in
`embeddings.db`, an entry in a search index — is untrusted. `vault / rel_path` on
its own accepts `../…` and absolute paths, and the note reader will happily put
the head of any host file into an LLM prompt.

Resolve, then require containment:

```python
resolved = (vault / rel_path).resolve()
if not resolved.is_relative_to(vault.resolve()):
    continue          # never read, never log the path content
```

Apply it at every site that joins a stored or backend-supplied path (`search`,
`_blend`, `_iter_notes`). A future backend is one more untrusted source.

## Search behaviour

- `VaultMemory.retrieve(query, limit, min_score)` blends keyword TF with optional
  semantic hits; `ingest(lesson)` writes the note and makes it retrievable.
- The state store keeps its own FTS5 index: **trigram tokenizer, tokens ≥ 3
  chars**, shorter queries fall back to `LIKE`. Trigram is what makes Thai
  substring search work — do not "simplify" it to `unicode61`, which treats a
  spaceless Thai sentence as a single token.
- `memory.db` is derived state; the JSONL runlog is the source of truth. Wipe
  corruption with `dacode state rebuild` (deletes the DB and replays the log).

## Secrets

`.env` files are read-protected: `read_file` refuses secret-bearing `.env`. Use
`grep -oE '^[A-Za-z_]+=' <file>` to list key *names*. Never print or commit
values; DaCode reads only the real process env and `<repo>/.env` — never
`~/.hermes/.env` or `~/.pi/agent/auth.json` (locked by `tests/test_llm_auth.py`).
