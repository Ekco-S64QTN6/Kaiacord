# Configuration and operations

Settings resolve in order: environment variables, then `config/kaia.yaml` (your overrides), then
`config/default_config.yaml` (the defaults). Edit `kaia.yaml` and leave the defaults file alone.

| Key | Default | Effect |
|:--|:--|:--|
| `performance.max_context_tokens` | `16384` | The context window. Larger costs VRAM; check `nvidia-smi` after changing it. |
| `features.constitution_injection` | `true` | Injects her constitution, about 2,400 tokens a turn that would otherwise go to retrieval. |
| `features.self_model_injection` | `false` | Injects her self-model, about 900 tokens a turn. |
| `generation.max_response_tokens` | `1024` | Reserved for the reply every turn. |
| `generation.base_temperature` / `rag_temperature` | `0.70` / `0.35` | Conversation, and answers grounded in documents. |
| `unprompted.sources.<name>` | all on | Which kinds of unprompted post may appear. A kind switched off still runs; nobody sees it. |
| `unprompted.max_per_day` / `min_interval_minutes` | `8` / `90` | Daily posts across every source / each source's own gap. |
| `unprompted.shared_gap_minutes` | `10` | Spacing between any two posts; a post held by it queues. |
| `unprompted.per_source.<source>` | — | Per-source `min_interval_minutes` and `max_per_day`. |
| `unprompted.bluesky.<name>` | `quip` only | Which kinds are also posted to Bluesky. |
| `desires.gate_enabled` / `initiate_threshold` | `true` | Whether, and how readily, she speaks first. |
| `bluesky.enabled` / `x_twitter.enabled` | `false` | Turns each integration on. Credentials alone do nothing. |
| `sky.location` | unset | `"lat, lon"`; a city is enough. ISS passes and `!sky` need it. |
| `radio.hfgcs_windows_utc` / `radio.follow` | four windows / E07, V07, S11a, M12, E11 | When she records the HFGCS net, and which number stations she tunes in for — one recording per station a day, six in all, rotating. |
| `radio.overnight_time` | `08:30` | When the morning write-up of her night shift is posted. |
| `radio.poll_hours` | `6` | How often the volunteer radio feeds are polled. |
| `radio.local.hours` / `gain` / `ppm` | `00:00-06:00` / `40` / `0` | When the local scanner watches (local time), the dongle's gain, and its frequency correction. |
| `radio.local.channels` / `nets` | empty | Local repeaters to name in the ledger, and nets to sit on for their whole window. |

## Hardware budget

The build targets one 12 GB card. Embeddings are pinned to the CPU so the whole card belongs to
the chat model and its context.

| Model | Role | Device | Memory |
|:--|:--|:--:|:--|
| `gemma3:12b` | Chat, narration, vision | GPU | about 9.1 GB at 24,576 context, 9.4 GB at 32,768 (q8_0 KV cache) |
| `nomic-embed-text-cpu` | Retrieval embeddings | CPU | about 500 MB of RAM |
| faster-whisper `large-v3` | Radio transcription (int8) | CPU | about 2.3 GB of RAM while loaded; released after 15 idle minutes |

## Operations

Most maintenance is behind one interactive menu:

```bash
bash scripts/kaia-tools.sh
```

The direct commands:

```bash
venv/bin/python3 tools/maintenance/health_check.py          # venv and packages, Ollama, models, GPU, knowledge base
venv/bin/python3 tools/maintenance/reindex_rag.py --trigger # incremental re-index of the running bot
venv/bin/python3 tools/maintenance/reindex_rag.py --clear   # full rebuild; refused while she is running
venv/bin/python3 tools/maintenance/audit_knowledge_base.py  # every known corpus fault, read-only
```

A full rebuild with the bot stopped embeds on the GPU (about 14 minutes on the current corpus,
against about two hours on the CPU).

## Adding books and documents

Use `kaia-tools.sh` → Documents & Ingestion, or convert directly:

```bash
venv/bin/python3 tools/maintenance/ebook_to_kb_md.py ~/Downloads/book.epub \
  --outdir knowledge_base/books --category "Science Fiction" \
  --title "Title" --author "Author" --summary "One paragraph…" --keywords "a,b,c"
```

The converter removes pandoc and Calibre artefacts, rebuilds paragraphs and chapters, and writes
the project's frontmatter. Books are named `Book - <Title> by <Author>.md`, documents
`<Topic> - <Title>.md`. A hand-written summary retrieves much better than the automatic one.
In Discord, `!download <url>` and `!youtube <url>` stage a page or transcript and file it straight
away; the hourly ingest pass retries anything that failed.

## Testing

```bash
venv/bin/python3 -m pytest -q -m "not ollama and not gpu and not slow"
```

Only a handful of tests need Ollama or the GPU; the rest run anywhere. Test runs log to
`logs/kaiacord.test.log`, never to the production log.

**A passing suite and a clean log are not proof that a feature works.** Both were trusted here for
months while features logged success over wrong output: recordings of pure static "kept",
invented transcripts filed as voice, a repair the running bot quietly undid. To verify a
feature, open what it actually wrote — the file under `memory/` or `knowledge_base/`, the
database row, the audio clip, the message in the channel — and check it against what it should
hold. [CLAUDE.md](../../CLAUDE.md) §9 has the routine.
