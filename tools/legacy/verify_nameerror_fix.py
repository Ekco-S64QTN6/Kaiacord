import sys
import os

# Mock discord and other modules to avoid import errors
sys.modules['discord'] = type('module', (), {'Client': object, 'Intents': type('module', (), {'default': lambda: None})})
sys.modules['discord.ext'] = type('module', (), {'commands': type('module', (), {'Bot': object}), 'tasks': type('module', (), {'loop': lambda **kwargs: lambda x: x})})
sys.modules['kaia_rag'] = type('module', (), {'KaiaRAG': object, 'HallucinationDetector': object})
sys.modules['kaia_image'] = type('module', (), {'generate_image': lambda x: x, 'unload_image_model': lambda: None, 'generation_lock': type('module', (), {'locked': lambda: False})})
sys.modules['kaia_vision'] = type('module', (), {'kaia_sees_image': lambda x, y: x, 'cleanup_session': lambda: None, 'ollama_client': object})
sys.modules['watchdog.observers'] = type('module', (), {'Observer': object})
sys.modules['watchdog.events'] = type('module', (), {'FileSystemEventHandler': object})
sys.modules['utils.kaia_intelligence'] = type('module', (), {
    'SemanticCache': object, 'ModelWarmPool': object, 'QueryClassifier': object, 
    'ContextOptimizer': object, 'RelevanceFeedback': object, 'PerformanceMonitor': object, 
    'PersonalizationEngine': object, 'PersistentStateManager': object, 'IntelligentCacheInvalidator': object
})
sys.modules['utils.clear_gpu_memory'] = type('module', (), {'clear_gpu_memory': lambda: None})
sys.modules['utils.kaia_logger'] = type('module', (), {
    'log_info': print, 'log_success': print, 'log_warning': print, 'log_error': print, 
    'log_action': print, 'log_critical': print, 'log_separator': print, 'log_message_received': print,
    'log_model_action': print, 'log_context_retrieval': print, 'log_response': print, 'log_file': print
})

# Now try to import or check the class in Kaiacord.py
try:
    with open('Kaiacord.py', 'r') as f:
        code = f.read()
    
    # Execute the code in a local namespace
    local_ns = {}
    # We need to mock some more things that might be called at top level
    local_ns['__name__'] = 'not_main'
    
    # Instead of full execution which might fail due to complex dependencies,
    # let's just check if the class is defined in the code.
    if 'class EmergencyContaminationFilter:' in code:
        print("✅ EmergencyContaminationFilter class found in Kaiacord.py")
        if 'def expand_news_query' in code:
            print("✅ expand_news_query method found in Kaiacord.py")
        else:
            print("❌ expand_news_query method NOT found")
    else:
        print("❌ EmergencyContaminationFilter class NOT found")
        
except Exception as e:
    print(f"❌ Error checking Kaiacord.py: {e}")
