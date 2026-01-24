import asyncio
import os
import sys
from unittest.mock import MagicMock, patch

# Add the project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Mock dependencies that might be missing in the environment
sys.modules['pypdf'] = MagicMock()
sys.modules['docx2txt'] = MagicMock()
sys.modules['llama_index'] = MagicMock()
sys.modules['llama_index.core'] = MagicMock()
sys.modules['llama_index.llms.ollama'] = MagicMock()
sys.modules['llama_index.embeddings.ollama'] = MagicMock()
sys.modules['llama_index.core.node_parser'] = MagicMock()

from utils.kaia_rag import KaiaRAG

async def verify_isolation():
    print("--- Starting User Isolation Verification ---")
    
    # Mock the index and retriever to avoid needing a real vector store/embedding model
    with patch('kaia_rag.VectorStoreIndex'), \
         patch('kaia_rag.OllamaEmbedding'), \
         patch('kaia_rag.Ollama'), \
         patch('kaia_rag.SentenceSplitter'), \
         patch('kaia_rag.StorageContext'), \
         patch('kaia_rag.load_index_from_storage'):
        
        rag = KaiaRAG()
        rag.index = MagicMock()
        
        # Define some mock nodes
        class MockNode:
            def __init__(self, content, metadata):
                self.content = content
                self.metadata = metadata
            def get_content(self):
                return self.content
        
        class MockNodeResult:
            def __init__(self, node, score):
                self.node = node
                self.score = score

        # User A: Ekco (177011971818782721)
        # User B: Gwaihir (470028550951403531)
        # User C: Starkond (random)
        
        node_a = MockNode("Ekco's secret software project.", {"source": "user_logs", "user_id": "177011971818782721", "user_name": "Ekco", "file_path": "user_logs/Ekco_177011971818782721/log.txt"})
        node_b = MockNode("Gwaihir's thoughts on eagles.", {"source": "user_logs", "user_id": "470028550951403531", "user_name": "Gwaihir", "file_path": "user_logs/Gwaihir_470028550951403531/log.txt"})
        node_c = MockNode("Starkond's prion research.", {"source": "user_logs", "user_id": "999", "user_name": "Starkond", "file_path": "user_logs/Starkond_999/log.txt"})
        node_lore = MockNode("The history of the world.", {"source": "lore", "file_path": "lore.txt"})
        
        mock_retriever = MagicMock()
        rag.index.as_retriever.return_value = mock_retriever
        
        # Test Case 1: User A talking, no mentions. Should NOT see User B or C.
        print("\nTest 1: User A talking, no mentions.")
        mock_retriever.retrieve.return_value = [
            MockNodeResult(node_a, 0.9),
            MockNodeResult(node_b, 0.8),
            MockNodeResult(node_c, 0.7),
            MockNodeResult(node_lore, 0.6)
        ]
        
        results = rag.retrieve("what do you think of software?", user_id="177011971818782721", user_name="Ekco")
        print(f"Results: {results}")
        
        has_a = any("Ekco" in r for r in results)
        has_b = any("Gwaihir" in r for r in results)
        has_c = any("Starkond" in r for r in results)
        
        print(f"Has User A: {has_a}")
        print(f"Has User B: {has_b} (Expected: False)")
        print(f"Has User C: {has_c} (Expected: False)")
        
        assert has_a == True
        assert has_b == False
        assert has_c == False
        
        # Test Case 2: User A talking, mentions User B. Should see User A and B, but NOT C.
        print("\nTest 2: User A talking, mentions User B.")
        # Mocking the known users check in retrieve
        with patch('os.path.exists', return_value=True), \
             patch('os.scandir') as mock_scandir:
            
            mock_dir_b = MagicMock()
            mock_dir_b.is_dir.return_value = True
            mock_dir_b.name = "Gwaihir_470028550951403531"
            mock_scandir.return_value = [mock_dir_b]
            
            results = rag.retrieve("what does Gwaihir think?", user_id="177011971818782721", user_name="Ekco")
            print(f"Results: {results}")
            
            has_a = any("Ekco" in r for r in results)
            has_b = any("Gwaihir" in r for r in results)
            has_c = any("Starkond" in r for r in results)
            
            print(f"Has User A: {has_a}")
            print(f"Has User B: {has_b} (Expected: True)")
            print(f"Has User C: {has_c} (Expected: False)")
            
            assert has_a == True
            assert has_b == True
            assert has_c == False

    print("\n--- All Isolation Tests Passed! ---")

if __name__ == "__main__":
    asyncio.run(verify_isolation())
