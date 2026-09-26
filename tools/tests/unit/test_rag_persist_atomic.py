"""An index save that dies partway leaves the last good copy in place."""
import os
import types

import pytest

from utils.core.kaia_rag_persistence import RAGPersistenceMixin


class _Store:
    def __init__(self, fail=False):
        self.fail = fail

    def persist(self, persist_dir):
        os.makedirs(persist_dir, exist_ok=True)
        with open(os.path.join(persist_dir, "docstore.json"), "w") as f:
            f.write('{"new": tru')                        # cut off mid-write
            if self.fail:
                raise OSError("killed mid-save")
        with open(os.path.join(persist_dir, "docstore.json"), "w") as f:
            f.write('{"new": true}')


def _rag(tmp_path, fail):
    rag = RAGPersistenceMixin.__new__(RAGPersistenceMixin)
    rag.persist_dir = str(tmp_path)
    rag.indices = {"knowledge": types.SimpleNamespace(storage_context=_Store(fail))}
    return rag


def test_a_failed_save_keeps_the_old_index(tmp_path):
    live = tmp_path / "knowledge"
    live.mkdir()
    (live / "docstore.json").write_text('{"old": true}')
    with pytest.raises(OSError):
        _rag(tmp_path, fail=True)._persist_index_atomic("knowledge")
    assert (live / "docstore.json").read_text() == '{"old": true}'


def test_a_good_save_replaces_it_and_leaves_no_temporaries(tmp_path):
    live = tmp_path / "knowledge"
    live.mkdir()
    (live / "docstore.json").write_text('{"old": true}')
    (tmp_path / "knowledge_tmp").mkdir()                   # left by an earlier cut-off save
    _rag(tmp_path, fail=False)._persist_index_atomic("knowledge")
    assert (live / "docstore.json").read_text() == '{"new": true}'
    assert sorted(p.name for p in tmp_path.iterdir()) == ["knowledge"]
