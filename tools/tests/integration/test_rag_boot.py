"""KaiaRAG constructs without touching Ollama or the on-disk index.

The previous version caught its own exception, printed the traceback and
returned — so a constructor that raised still produced a passing test. It was
also an unmarked `async def`, which pytest-asyncio in strict mode skips
silently.
"""
import pytest

from utils.core.kaia_rag import KaiaRAG


@pytest.mark.integration
def test_kaia_rag_constructs():
    rag = KaiaRAG()
    assert rag is not None
    # Construction must stay cheap: indices are built by _initialize_indices()
    # / pre_warm(), not by __init__, so boot does not block on embedding.
    assert not getattr(rag, "_initialized", False)


@pytest.mark.integration
def test_kaia_rag_persist_dir_is_configurable():
    """Tests and tooling override persist_dir; it must not be a constant."""
    rag = KaiaRAG()
    original = rag.persist_dir
    rag.persist_dir = "/tmp/kaia-rag-probe"
    assert rag.persist_dir != original
