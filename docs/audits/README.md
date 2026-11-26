# Repository file-review ledger

This ledger is an **inventory and review tracker**, not a code-quality verdict.

## Snapshot and scope

The inventory was taken from the complete recursive Git tree on `main` at:

`b91c34f9807acb3c669b8a85c529dc680b1b63a1`

GitHub returned an untruncated tree containing **776 tracked file blobs: 684 Python files and 92 non-Python files**. The CSV carries the Git blob ID for each inventoried path so that a later content change can be detected rather than inheriting an obsolete “reviewed” mark.

The ledger contains one row for every tracked file in the snapshot except the ledger CSV itself (a file cannot contain its own stable blob ID). It also includes the audit-support README, validator and tests added in the same change set. The validator excludes only the ledger CSV from its self-completeness comparison.

## Review status

Every initial row is `not_reviewed`. No file is marked reviewed by this inventory-generation pass. The risk tier is a **triage heuristic based on path and file type**, not a security finding or assurance result.

Allowed states:

- `not_reviewed`: no complete file-level review has been recorded.
- `reviewed`: a reviewer completed the file review; set `reviewed_blob_sha` to the exact `blob_sha` and record concise supporting evidence.
- `not_applicable`: the file was examined and a code-quality review is not applicable; explain why in `evidence`.

When a tracked file changes, update its `blob_sha` and reset its review status to `not_reviewed` unless the new blob has itself been reviewed. A review must not carry forward across a blob change.

## Validate the inventory

Run from the repository root:

```bash
python tools/maintenance/check_review_manifest.py
```

The checker compares the ledger with `git ls-files`, rejects missing/new/deleted paths, duplicate rows, stale blob IDs, invalid status values and “reviewed” rows without matching blob identity and evidence. It deliberately does not claim that a row marked `reviewed` is correct; a reviewer must supply that evidence.

## Remaining audit work

The manifest is only the coverage ledger. The file-by-file review, relevant test review, security/concurrency/persistence analysis, frontend/API route audit, shared-sibling check and environment-dependent acceptance remain outstanding until their individual rows contain review evidence. **Do not close #366 because this manifest exists or because its completeness check passes.**
