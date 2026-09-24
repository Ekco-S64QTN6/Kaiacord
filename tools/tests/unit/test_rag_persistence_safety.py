"""An index write killed partway through must not cost the index."""
import os


def test_an_index_left_in_old_is_restored_at_load(tmp_path):
    """persist() renames <itype> to <itype>_old, then <itype>_tmp to <itype>.
    Killed between the two, <itype> is missing and the last good copy sits in
    _old; loading used to start an empty index there and re-embed everything."""
    from llama_index.core import VectorStoreIndex
    from utils.core.kaia_rag import KaiaRAG

    rag = KaiaRAG(persist_dir=str(tmp_path / "rag"))
    base = rag.persist_dir
    for itype in ("persona", "user_profiles", "knowledge", "logs", "dreams"):
        VectorStoreIndex.from_documents([]).storage_context.persist(
            persist_dir=os.path.join(base, itype))
    os.rename(os.path.join(base, "knowledge"), os.path.join(base, "knowledge_old"))
    marker = os.path.join(base, "knowledge_old", "MARKER")
    open(marker, "w").close()

    rag._initialize_indices()

    assert os.path.exists(os.path.join(base, "knowledge", "MARKER")), "the old copy was not restored"
    assert not os.path.exists(os.path.join(base, "knowledge_old"))
