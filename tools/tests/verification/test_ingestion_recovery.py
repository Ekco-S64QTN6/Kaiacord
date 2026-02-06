import os
import sys
import shutil
import tempfile
from unittest.mock import MagicMock, patch

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

from utils.core.kaia_rag import KaiaRAG
from utils.infrastructure.logging.kaia_logger import log_info, log_success

def test_ingestion_recovery_fix():
    print("=== Testing Ingestion Recovery Fix ===")
    
    # Create temp directory for testing
    with tempfile.TemporaryDirectory() as temp_dir:
        kb_dir = os.path.join(temp_dir, "kb")
        persist_dir = os.path.join(temp_dir, "storage")
        os.makedirs(kb_dir)
        os.makedirs(persist_dir)
        
        # Create a "corrupt" file
        corrupt_file_path = os.path.join(kb_dir, "corrupt.pdf")
        with open(corrupt_file_path, "w") as f:
            f.write("This is not a real PDF")
            
        # Initialize RAG with temp dirs
        # Mocking Ollama/Settings to avoid actual LLM calls during init
        with patch('utils.core.kaia_rag.OllamaEmbedding'), \
             patch('utils.core.kaia_rag.Ollama'), \
             patch('utils.core.kaia_rag.SentenceSplitter'), \
             patch('utils.core.kaia_rag.Settings'), \
             patch('utils.core.kaia_rag.load_index_from_storage'), \
             patch('utils.core.kaia_rag.VectorStoreIndex'), \
             patch('utils.infrastructure.gpu.gpu_manager.OllamaGPUManager'):
             
            rag = KaiaRAG(knowledge_base_dir=kb_dir, persist_dir=persist_dir)
            
            # Mock the parts that would fail
            # We want to trigger line 719: log_warning(f"No data loaded from file. Moving to corrupt_files.")
            # and line 726: log_critical(f"MOVED EMPTY/CORRUPT FILE TO: {dest_path}")
            
            with patch('utils.core.kaia_rag.SimpleDirectoryReader') as mock_reader_cls:
                mock_reader = MagicMock()
                mock_reader.load_data.return_value = [] # Simulate empty/corrupt load
                mock_reader_cls.return_value = mock_reader
                
                print("Running refresh_knowledge_base()...")
                try:
                    rag.refresh_knowledge_base()
                    print("✓ refresh_knowledge_base() completed without NameError.")
                except NameError as ne:
                    print(f"✗ FAILED: NameError encountered: {ne}")
                    sys.exit(1)
                except Exception as e:
                    print(f"Caught expected or other exception: {e}")
                
                # Verify the file was moved to corrupt_files
                corrupt_dir = os.path.join(kb_dir, "corrupt_files")
                if os.path.exists(corrupt_dir) and len(os.listdir(corrupt_dir)) > 0:
                    print(f"✓ File successfully moved to {corrupt_dir}.")
                else:
                    print(f"✗ FAILED: File was not moved to corrupt_files.")
                    sys.exit(1)

    print("=== Verification Complete: Fix Confirmed ===")

if __name__ == "__main__":
    test_ingestion_recovery_fix()
