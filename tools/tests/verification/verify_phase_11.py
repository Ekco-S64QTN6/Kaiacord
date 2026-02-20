import asyncio
import os
import sys
import json
import time
from pathlib import Path

# Add project root to path
sys.path.append(os.getcwd())

from utils.infrastructure.logging.kaia_logger import log_info, log_success, log_error
from utils.core.kaia_rag import KaiaRAG
from utils.core.kaia_intelligence import IntentParser, PersistentStateManager, PersonalizationEngine
from utils.core.kaia_dream import DreamEngine
from utils.infrastructure.system.yaml_config import config

async def verify_hardening():
    log_info("Starting Phase 11 Verification...")
    
    # 1. Verify RAG Manifest
    rag = KaiaRAG(knowledge_base_dir=config.knowledge_base_dir, persist_dir="./memory/rag_storage")
    rag._load_indexed_files()
    if hasattr(rag, 'indexed_files'):
        log_success(f"RAG Manifest loaded: {len(rag.indexed_files)} entries.")
    else:
        log_error("RAG Manifest failed to load or is missing.")

    # 2. Verify Personalization Dirty Tracking
    personalization = PersonalizationEngine()
    personalization.user_profiles["test_user"] = {"conciseness": 0.5, "technicality": 0.5}
    # Initial state should not be dirty unless learned from interaction
    await personalization.learn_from_interaction("test_user", "hello", "hi")
    if "test_user" in personalization.dirty_profiles:
        log_success("Personalization dirty tracking working.")
    else:
        log_error("Personalization dirty tracking FAILED.")

    # 3. Verify State Persistence
    state_mgr = PersistentStateManager(state_dir="./memory/state")
    from unittest.mock import MagicMock
    monitor = MagicMock()
    monitor.metrics = {}
    
    # Trigger safe
    state_mgr.save_state(personalization, monitor)
    profile_path = Path("./memory/state/profiles/test_user.json")
    if profile_path.exists():
        log_success("Individual profile persistence working.")
    else:
        log_error("Individual profile persistence FAILED.")

    # 4. Verify Dream History
    dream_engine = DreamEngine(config_instance=config, rag_instance=rag)
    if hasattr(dream_engine, '_history'):
        log_success("Dream history registry initialized.")
    else:
        log_error("Dream history registry missing.")

    # 5. Verify Clean Shutdown
    log_info("Verifying clean shutdown...")
    from utils.infrastructure.system.shutdown_fixed import shutdown_manager
    await shutdown_manager.async_shutdown()
    log_success("System shutdown logic executed.")

    log_success("Phase 11 Core Logic Verification Complete.")

if __name__ == "__main__":
    asyncio.run(verify_hardening())
