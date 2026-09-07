# Ingress

Staging area for documents submitted through `!download`. **Not indexed by RAG.**

Files land here as raw markdown with a `.meta.json` sidecar recording who
submitted them and from where. `tools/maintenance/process_ingress.py` runs
hourly (and on demand from `kaia-tools.sh` → Knowledge Base → Process ingress),
normalises each one to the knowledge-base format, adds frontmatter, files it
into the right folder, and triggers a reindex.

Anything that fails processing is left here with a `.error` sidecar rather than
being silently dropped.
