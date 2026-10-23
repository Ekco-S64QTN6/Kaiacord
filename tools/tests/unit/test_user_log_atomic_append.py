"""Concurrent first writes must not duplicate transcript front matter."""

from utils.core.kaia_rag_persistence import RAGPersistenceMixin


def test_stale_new_file_metadata_writes_front_matter_once(tmp_path):
    path = str(tmp_path / "interactions_20261023.md")
    stale_args = {
        "path": path,
        "is_new": True,
        "header": '---\nsummary: ""\nkeywords: []\ndocument_type: Transcript\n---\n\n',
        "user_name": "pytest",
        "text": "[2026-10-23 12:00:00] Alice: first message\n\n",
    }

    # Simulate two writers that both prepared arguments before the first
    # append created the file. Both carry the stale is_new=True snapshot.
    assert RAGPersistenceMixin._write_interaction_to_disk(None, stale_args)
    second = dict(stale_args, text="[2026-10-23 12:00:01] Alice: second message\n\n")
    assert RAGPersistenceMixin._write_interaction_to_disk(None, second)

    content = (tmp_path / "interactions_20261023.md").read_text(encoding="utf-8")
    assert content.count("document_type: Transcript") == 1
    assert "Alice: first message" in content
    assert "Alice: second message" in content
