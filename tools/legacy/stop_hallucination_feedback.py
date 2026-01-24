"""
EMERGENCY: Stop the hallucination feedback loop
"""

import os
import re
import glob
import shutil
from datetime import datetime

def emergency_clean_all_logs():
    """Remove all hallucinated content from user logs"""
    log_dir = "knowledge_base/user_logs"
    
    if not os.path.exists(log_dir):
        print(f"Directory {log_dir} not found.")
        return 0

    hallucination_keywords = [
        "juanita", "deane", "bonbons", "agency", "agency's", 
        "university network", "behind the curtain", "slow burn",
        "roundabout questions", "internal comms"
    ]
    
    cleaned_files = 0
    
    for user_folder in os.listdir(log_dir):
        user_path = os.path.join(log_dir, user_folder)
        if not os.path.isdir(user_path):
            continue
            
        log_files = glob.glob(os.path.join(user_path, "interactions_*.txt"))
        
        for log_file in log_files:
            with open(log_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            original_content = content
            
            # Remove hallucinated responses
            lines = content.split('\n')
            cleaned_lines = []
            in_hallucination = False
            
            for line in lines:
                # Check if this line starts a hallucinated response
                # Adjusted to match "Kaia: " as well
                if "Got response:" in line or "yeah. what's up." in line or "Kaia:" in line:
                    if any(keyword in line.lower() for keyword in hallucination_keywords):
                        in_hallucination = True
                        # If the keyword is in the header line itself, skip it
                        continue
                    else:
                        # If it's a Kaia line but no keyword yet, we might still be entering a hallucination block
                        # But for now, let's just mark that we are in a response block
                        in_hallucination = True
                        cleaned_lines.append(line)
                        continue
                
                # If we're in a hallucination, check if it contains keywords
                if in_hallucination:
                    if any(keyword in line.lower() for keyword in hallucination_keywords):
                        continue  # Skip this hallucinated line
                    # Check if hallucination has ended (empty line or new timestamp)
                    if not line.strip() or line.startswith('---'):
                        in_hallucination = False
                        cleaned_lines.append(line)
                    else:
                        # This might still be hallucination
                        contains_hallucination = any(keyword in line.lower() for keyword in hallucination_keywords)
                        if not contains_hallucination:
                            cleaned_lines.append(line)
                else:
                    cleaned_lines.append(line)
            
            cleaned_content = '\n'.join(cleaned_lines)
            
            # Also remove any remaining hallucination phrases
            for keyword in hallucination_keywords:
                # Remove the entire line containing the keyword
                pattern = r'^.*' + re.escape(keyword) + r'.*$\n?'
                cleaned_content = re.sub(pattern, '', cleaned_content, flags=re.IGNORECASE | re.MULTILINE)
            
            if cleaned_content != original_content:
                # Backup original
                backup_path = log_file + '.pre_emergency_backup'
                shutil.copy2(log_file, backup_path)
                
                # Write cleaned version
                with open(log_file, 'w', encoding='utf-8') as f:
                    f.write(cleaned_content)
                
                print(f"✓ Cleaned: {log_file}")
                cleaned_files += 1
    
    return cleaned_files

def reset_semantic_cache():
    """Completely clear semantic cache"""
    cache_files = [
        "semantic_cache.json",
        "cache.db",
        "semantic_cache.pkl",
        "rag_cache.json",
        "rag_cache.pkl"
    ]
    
    for cache_file in cache_files:
        if os.path.exists(cache_file):
            os.remove(cache_file)
            print(f"✓ Removed: {cache_file}")

def create_clean_persona_response():
    """Create a clean, correct response for identity queries"""
    clean_response = """yeah. what's up.

coffee's getting cold again. server's humming. cat's judging me from the bookshelf.
logs are... existent. always something to fix.

what do you need?"""
    
    # Save as a reference response
    with open("clean_response.txt", "w", encoding="utf-8") as f:
        f.write(clean_response)
    
    print("✓ Created clean response template")

def add_stop_words_to_rag():
    """Add hallucination stop words to RAG config"""
    stop_words = [
        "juanita", "deane", "bonbons", "agency", 
        "university network", "internal comms", "slow burn",
        "roundabout questions", "terrier with a scent"
    ]
    
    config_data = {
        "rag_filters": {
            "stop_words": stop_words,
            "minimum_relevance": 0.85,
            "max_retrieved_chunks": 3,
            "identity_query_override": {
                "use_only_persona": True,
                "max_chunks": 2
            }
        },
        "cache_settings": {
            "identity_cache_bypass": True,
            "semantic_threshold": 0.95,
            "never_cache": ["who", "what", "status", "identity"]
        }
    }
    
    import json
    with open("rag_emergency_config.json", "w") as f:
        json.dump(config_data, f, indent=2)
    
    print("✓ Created emergency RAG config")

def main():
    print("🚨 EMERGENCY HALLUCINATION FEEDBACK LOOP FIX")
    print("=" * 50)
    
    # 1. Clean all logs
    print("\n1. Cleaning all user logs...")
    cleaned = emergency_clean_all_logs()
    print(f"   Cleaned {cleaned} files")
    
    # 2. Reset cache
    print("\n2. Resetting semantic cache...")
    reset_semantic_cache()
    
    # 3. Create clean response
    print("\n3. Creating clean response template...")
    create_clean_persona_response()
    
    # 4. Add stop words
    print("\n4. Adding hallucination stop words...")
    add_stop_words_to_rag()
    
    print("\n" + "=" * 50)
    print("✅ EMERGENCY FIXES APPLIED")
    print("\nNEXT STEPS:")
    print("1. STOP Kaiacord immediately")
    print("2. Run: python stop_hallucination_feedback.py")
    print("3. Delete all files in ./knowledge_base except:")
    print("   - kaia_persona.md")
    print("   - user_logs/ (which we just cleaned)")
    print("4. Restart Kaiacord")
    print("5. Test with: 'status kaia'")
    print("\n⚠️  DO NOT let Kaia run until you've cleaned the knowledge base!")

if __name__ == "__main__":
    main()
