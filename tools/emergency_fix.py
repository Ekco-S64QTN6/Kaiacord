"""
emergency_fix.py - Immediate fixes for hallucination bug
"""

import json
import os
import shutil

def clear_semantic_cache():
    """Clear the semantic cache to break the loop"""
    cache_files = [
        "semantic_cache.json",
        "cache.db",
        "rag_cache.pkl"
    ]
    
    for cache_file in cache_files:
        if os.path.exists(cache_file):
            os.remove(cache_file)
            print(f"✓ Cleared {cache_file}")

def reset_user_profiles():
    """Reset all user profiles to force regeneration"""
    user_logs_dir = "./knowledge_base/user_logs"
    if not os.path.exists(user_logs_dir):
        print(f"Directory {user_logs_dir} not found.")
        return
    
    for user_dir in os.listdir(user_logs_dir):
        user_path = os.path.join(user_logs_dir, user_dir)
        if not os.path.isdir(user_path):
            continue
            
        profile_path = os.path.join(user_path, "user_profile.md")
        if os.path.exists(profile_path):
            # Backup first
            backup_path = profile_path + ".backup"
            if os.path.exists(backup_path):
                os.remove(backup_path)
            os.rename(profile_path, backup_path)
            print(f"✓ Reset profile for {user_dir}")

def create_strict_retrieval_filter():
    """Create a strict filter config for RAG"""
    config_dir = "./config"
    os.makedirs(config_dir, exist_ok=True)
    
    filter_config = {
        "strict_mode": True,
        "required_metadata": ["source_type"],
        "banned_source_types": ["garbage"],
        "minimum_priority": 0.5,
        "identity_query_filters": {
            "require_source": ["persona", "user_logs"],
            "max_results": 3
        }
    }
    
    with open(os.path.join(config_dir, "rag_filters.json"), "w") as f:
        json.dump(filter_config, f, indent=2)
    
    print("✓ Created strict RAG filter config")

def main():
    print("🚨 Applying emergency fixes...")
    clear_semantic_cache()
    reset_user_profiles()
    create_strict_retrieval_filter()
    print("\n✅ Emergency fixes applied.")
    print("\nNext steps:")
    print("1. Run: python scan_knowledge_base.py")
    print("2. Restart Kaiacord")
    print("3. Test with: 'who are you' and 'status'")

if __name__ == "__main__":
    main()
