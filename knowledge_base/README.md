# knowledge_base

Everything Kaia can retrieve, plus the three staging areas that she cannot.

Restructured 2026-09-19. It had grown to sixteen top-level folders one at a
time, and the shape no longer said anything about the contents: `corrupt_files`
(0 files) sat beside `quarantine` (868), `snapshots` (0) beside `system_logs`
(1), and `documents/tech_updates` (121) beside a separate `news/` (250).

## Indexed

| Folder | What it is | Naming |
|:--|:--|:--|
| `books/` | Full texts, ingested from EPUB/PDF | `Book - <Title> by <Author>.md` |
| `documents/` | Essays, blog posts, reports, specs — prose from the web | `<Topic> - <Title>.md` |
| `news/` | Daily briefs (`news/daily/`) and tech updates (`news/tech_updates/`) | dated |
| `wiki/` | Project 1999 wiki articles | as scraped |
| `troubleshooting/` | P99 technical guides, synthesised from the forum | `Troubleshooting_<Category>.md` |
| `transcripts/` | Podcast and talk transcripts | `<Topic> - <Title>.md` |
| `kaia_dreams/` | Her own reflections. `consolidated/` holds one document per subject | see below |
| `user_logs/` | Per-user interaction history and profiles | `interactions_<date>.md` |
| `runtime/` | What the running bot wrote about itself: `snapshots/`, `system_logs/` | timestamped |

`kaia_persona.md` and `identity_registry.json` sit at the root and are special —
the persona is never truncated and never indexed as a document.

## Not indexed

| Folder | Why |
|:--|:--|
| `_ingress/` | Staging. `!download` and `!youtube` write here; `process_ingress.py` files each document into an allow-listed folder. The exclusion is what makes those commands safe to leave open to everyone. |
| `_quarantine/` | Files pulled out of the corpus: unparseable (`corrupt_files/`), and 868 dream files that were chat transcripts and scraped prose rather than reflections. Nothing here is deleted. |
| `forum_posts/` | 9,236 scraped threads. Excluded from *global* retrieval so strangers' claims cannot surface as fact in an unrelated conversation; the drafting path reads the one thread it is posting in directly. |
| `.compacted_backup/`, `.dream_archive/`, `.test/` | Working data. **Any dot-directory is skipped** — these hold the originals that compaction and consolidation superseded, and indexing them handed her the summary *and* everything it summarised. |

## The two folding tools

`kaia_dreams/` and `user_logs/forum_*/` both accumulate one small file per event,
which is right for writing and wrong for retrieving. Two tools fold them, both
dry-run by default, both reachable from `kaia-tools.sh` → Dreams & Curation:

- `triage_dreams.py` — sorts `kaia_dreams/`, quarantines what is not a reflection.
- `consolidate_dreams.py` — one document per book, person and topic. **Extends**
  an existing document rather than replacing it.
- `compact_forum_profiles.py` — one profile per forum user, identity-aware.

They run weekly from `_make_dream_curation_task` (`dream_mode.auto_curate`).

## Adding a folder

A new top-level folder has to be added in four places or it will half-work:

1. `process_ingress.ALLOWED_FOLDERS` — or a sidecar naming it is silently ignored
2. `knowledge_boundary` — or she will not vouch for anything in it
3. `enrich_metadata.knowledge_dirs` — or its frontmatter is never backfilled
4. `kaia_rag_indexer` — only if it needs a `source_type` of its own

`tools/tests/unit/test_kb_structure.py` checks 1 and 2 against what is on disk.
