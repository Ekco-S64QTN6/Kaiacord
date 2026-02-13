import sys
import os
from typing import List, Dict, Any

def test_import(module_path, names=None):
    try:
        if names:
            exec(f"from {module_path} import {', '.join(names)}")
            print(f"✅ {module_path} ({', '.join(names)}) - OK")
        else:
            exec(f"import {module_path}")
            print(f"✅ {module_path} - OK")
        return True
    except ImportError as e:
        print(f"❌ {module_path} - FAILED: {e}")
        return False
    except Exception as e:
        print(f"⚠️ {module_path} - ERROR: {e}")
        return False

print("--- Auditing Logic Layer Imports ---")
results = [
    test_import("utils.infrastructure.system.yaml_config", ["config"]),
    test_import("utils.infrastructure.system.bot_state", ["bot_state"]),
    test_import("utils.infrastructure.system.rate_limiter", ["RateLimiter"]),
    test_import("utils.infrastructure.system.messaging", ["send_kaia_response"]),
    test_import("utils.infrastructure.system.dashboard_manager", ["DashboardManager"]),
    test_import("utils.core.kaia_rag", ["KaiaRAG"]),
    test_import("utils.core.kaia_dream", ["DreamEngine"]),

    test_import("utils.core.performance_monitor", ["PerformanceMonitor"]),
    test_import("utils.core.kaia_intelligence", ["ModelWarmPool", "ContextOptimizer", "RelevanceFeedback", "QueryClassifier"]),
    test_import("utils.infrastructure.system.performance_optimizer", ["ResponseOptimizer", "timed_response"]),
    test_import("utils.core.response_filter", ["HallucinationDetector", "EmergencyContaminationFilter"]),
    test_import("utils.core.message_processor", ["MessageProcessor"]),
    test_import("utils.social.kaia_social_responder", ["load_persona_async"]),
    test_import("utils.news.kaia_news", ["NewsRetrievalEnhancer", "NewsManager", "RAGEnhancer"]),
    test_import("utils.core.background_tasks", ["run_news_update"]),
    test_import("utils.commands.registry", ["dispatch_command"])
]

if all(results):
    print("\n🎉 ALL CORE IMPORTS SUCCESSFUL")
else:
    print(f"\n🛑 {results.count(False)} IMPORTS FAILED")
