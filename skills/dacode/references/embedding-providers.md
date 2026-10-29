# Wiring an embedder for the `local` memory backend

`dacode/memory/embedder.py` posts `{"model": …, "input": [texts],
"dimensions": N?}` to `$DACODE_EMBED_BASE_URL/embeddings` and expects
`{"data": [{"embedding": [...]}, …]}`. Anything OpenAI-shaped works; anything
else needs a small adapter (see the backend protocol in `dacode/memory/backends`).

| Provider | `DACODE_EMBED_BASE_URL` | `DACODE_EMBED_MODEL` | Dims | Key source |
|---|---|---|---|---|
| Ollama | `http://127.0.0.1:11434/v1` | `bge-m3` (handles Thai), `nomic-embed-text` | model default | none |
| llama.cpp server | `http://127.0.0.1:<port>/v1` | whatever the server started with `--embedding` | model default | none |
| LM Studio | `http://127.0.0.1:1234/v1` | the loaded embedding model | model default | none |
| vLLM | `http://127.0.0.1:8000/v1` | the served embedding model | model default | optional |
| OpenAI | `https://api.openai.com/v1` | `text-embedding-3-small` | `1536` (optional) | `OPENAI_API_KEY` |
| Gemini (OpenAI-compat) | `https://generativelanguage.googleapis.com/v1beta/openai` | `gemini-embedding-2` | `768` (default 3072) | `GEMINI_API_KEY` / `GOOGLE_API_KEY` |

Key resolution: `DACODE_EMBED_API_KEY` → `OPENAI_API_KEY` → `GEMINI_API_KEY` →
`GOOGLE_API_KEY`.

Other knobs: `DACODE_EMBED_BATCH` (texts per request, default 16 — 32 works
against Gemini), `DACODE_EMBED_TIMEOUT` (seconds, default 60), `DACODE_EMBED_DIMS`
(request `dimensions` in the payload), `DACODE_EMBED_DB` (store path, default
`~/.local/state/dacode/embeddings.db`).

```bash
dacode memory index      # incremental by mtime; --rebuild re-embeds everything
dacode memory backends   # model + vector count, or the reason it is off
dacode memory search "…" --backend local
```

Rules worth remembering:

- **Keys come from the process env or the target repo's `.env` only.** DaCode
  never reads `~/.hermes/.env` or Pi's auth store — put the provider key in the
  repo's git-ignored `.env` (any of the four names above).
- **Pin the width with `DACODE_EMBED_DIMS` when comparing stores.** Gemini's
  `gemini-embedding-2` defaults to 3072 and truncates to 768/1536 on request;
  the client raises if the provider ignores the field, so a silent 3072 can't
  sneak in. Verified: 583-note vault indexed at 768 in one pass.
- **Gemini's OpenAI-compat endpoint batches correctly** (`input: [a, b, c]` →
  three vectors, `dimensions` honoured), unlike `google-genai` ≥ 2.3, where a
  list of plain strings collapses into one aggregated vector and each text must
  be wrapped in `types.Content`. If you write a native adapter later, keep that
  wrapper in mind.
- **One model per store.** `memory index` raises when the store's model differs
  and `--rebuild` was not passed — mixing models returns plausible-looking
  nonsense.
- **No embedder configured is not a failure.** `auto` walks local → hermes
  adapter → keyword-only, so a clone with no config still retrieves by TF.
- **A 429 "spending cap" from a hosted provider means auth succeeded** — the
  key and model are right and the account is the blocker, so do not start
  rotating keys on that error.
