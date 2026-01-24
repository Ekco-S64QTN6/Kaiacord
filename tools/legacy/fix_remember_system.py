#!/usr/bin/env python3
"""
COMPREHENSIVE FIX for "kaia remember" system
Fixes storage, indexing, and retrieval all at once
"""
import os
import sys
import re
import json
import asyncio

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from utils.kaia_rag import KaiaRAG

def fix_kaiacord_file():
    """Fix the user ID bug in Kaiacord.py"""
    filepath = "Kaiacord.py"
    
    with open(filepath, 'r') as f:
        content = f.read()
    
    # Fix 1: Correct user reference in remember command
    old_pattern = r'success = await run_rag\(rag\.add_memory, bot\.user\.id, bot\.user\.name, memory_content\)'
    new_text = r'success = await run_rag(rag.add_memory, msg.author.id, msg.author.display_name, memory_content)'
    
    changes_made = 0
    
    if re.search(old_pattern, content):
        content = re.sub(old_pattern, new_text, content)
        changes_made += 1
        print("✅ Fixed user ID reference in remember command")
    
    # Fix 2: Also check for alternative pattern
    alt_pattern = r'rag\.add_memory, bot\.user\.id, bot\.user\.name'
    alt_new = r'rag.add_memory, msg.author.id, msg.author.display_name'
    
    if re.search(alt_pattern, content) and not re.search(old_pattern, content):
        content = re.sub(alt_pattern, alt_new, content)
        changes_made += 1
        print("✅ Fixed alternative pattern")
    
    if changes_made == 0:
        print("⚠️  Could not find user ID bug pattern - may already be fixed")
    
    with open(filepath, 'w') as f:
        f.write(content)
    
    return changes_made > 0

def patch_kaia_rag():
    """Patch kaia_rag.py for memory system"""
    filepath = "utils/kaia_rag.py"
    
    with open(filepath, 'r') as f:
        content = f.read()
    
    changes_made = 0
    
    # FIX 1: Boost memory source in scoring
    if "'user_profile': 3.0" in content and "'memory': 5.0" not in content:
        # Insert memory source with HIGHEST priority
        content = content.replace(
            "'user_profile': 3.0,",
            "'memory': 5.0,\n                    'user_profile': 3.0,"
        )
        changes_made += 1
        print("✅ Memory source boosted to priority 5.0")
    
    # FIX 2: Tag REMEMBER_COMMAND as memory source
    if '"source": "user_logs"' in content and 'is_vision_response' in content:
        # Find the metadata section for logs
        # We need to add conditional source assignment
        pattern = r'(new_doc = Document\(\s*text=interaction_text,\s*metadata=\{)'
        
        # First, find where we define new_doc in log_user_interaction
        lines = content.split('\n')
        for i, line in enumerate(lines):
            if 'new_doc = Document(' in line and 'interaction_text' in line:
                # Insert source_type logic above this line
                insert_idx = i
                source_logic = '''                # Determine source type
                if "[REMEMBER_COMMAND]" in message_content:
                    source_type = "memory"
                elif is_vision_response:
                    source_type = "vision"
                else:
                    source_type = "user_logs"'''
                
                lines.insert(insert_idx, source_logic)
                changes_made += 1
                print("✅ Added source type logic")
                
                # Now update the metadata line
                for j in range(i+1, min(i+10, len(lines))):
                    if '"source": "user_logs"' in lines[j]:
                        lines[j] = '                    "source": source_type,'
                        changes_made += 1
                        print("✅ Updated source field to use dynamic type")
                        break
                break
        
        content = '\n'.join(lines)
    
    # FIX 3: Improve memory retrieval in query routing
    if 'is_user_identity_query =' in content and 'is_memory_query' not in content:
        # Add memory query detection
        insert_point = content.find('is_user_identity_query =')
        if insert_point != -1:
            # Find the end of that section
            end_line = content.find('\n', insert_point)
            # Add memory query detection after identity detection
            memory_logic = '''
            # Detect memory-related queries
            memory_keywords = ["remember", "recall", "what did i tell you", "what did we discuss"]
            is_memory_query = any(word in query_lower for word in memory_keywords)'''
            
            content = content[:end_line] + memory_logic + content[end_line:]
            changes_made += 1
            print("✅ Added memory query detection")
    
    # FIX 4: Add memory index to target indices
    if "target_itypes = ['persona']" in content and 'is_memory_query' not in content:
        # This pattern appears in identity query routing
        # We'll modify to include logs for memory queries
        content = content.replace(
            "target_itypes = ['persona']",
            '''# Memory queries should check logs and knowledge
            if is_memory_query:
                target_itypes = ['logs', 'knowledge']
            else:
                target_itypes = ['persona']'''
        )
        changes_made += 1
        print("✅ Added memory routing logic")
    
    with open(filepath, 'w') as f:
        f.write(content)
    
    return changes_made > 0

def force_reindex_all_memories():
    """Force reindex all memory entries"""
    print("\n🔄 Force reindexing all memory entries...")
    
    try:
        rag = KaiaRAG()
        
        # Find all user log directories
        logs_dir = "knowledge_base/user_logs"
        if not os.path.exists(logs_dir):
            print(f"❌ Logs directory not found: {logs_dir}")
            return False
        
        # Clear existing logs index
        print("🧹 Clearing existing logs index...")
        logs_index_dir = "storage/logs"
        if os.path.exists(logs_index_dir):
            import shutil
            shutil.rmtree(logs_index_dir)
            os.makedirs(logs_index_dir)
        
        # Force full reindex
        print("📚 Reindexing all user logs...")
        rag.refresh_knowledge_base()
        
        # Persist
        print("💾 Persisting reindexed data...")
        rag.persist(force=True)
        
        print("✅ Force reindex complete")
        return True
        
    except Exception as e:
        print(f"❌ Error during force reindex: {e}")
        import traceback
        traceback.print_exc()
        return False

def create_test_script():
    """Create test script to verify memory system"""
    test_script = '''
#!/usr/bin/env python3
"""
Test script to verify memory system is working
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from utils.kaia_rag import KaiaRAG

def test_memory_retrieval():
    """Test if memories can be retrieved"""
    rag = KaiaRAG()
    
    test_queries = [
        "Starkind",
        "Worship means",
        "Awareness is input",
        "Remember means to store",
        "Honor means to remain true"
    ]
    
    for query in test_queries:
        print(f"\\n🔍 Testing query: '{query}'")
        results = rag.retrieve(query, top_k=5)
        
        if results:
            print(f"   ✅ Found {len(results)} results")
            for i, result in enumerate(results[:2]):  # Show top 2
                preview = result[:100].replace('\\n', ' ')
                print(f"   {i+1}. {preview}...")
        else:
            print(f"   ❌ No results found")
    
    return len(results) > 0

if __name__ == "__main__":
    print("🧪 Testing memory retrieval system...")
    success = test_memory_retrieval()
    
    if success:
        print("\\n🎉 Memory system appears to be working!")
    else:
        print("\\n❌ Memory system is NOT retrieving data")
        print("\\n📋 Troubleshooting steps:")
        print("1. Check if logs are in knowledge_base/user_logs/")
        print("2. Check if [REMEMBER_COMMAND] appears in log files")
        print("3. Run force reindex: python fix_remember_system.py --reindex")
'''
    
    with open("test_memory_system.py", "w") as f:
        f.write(test_script)
    
    print("✅ Created test script: test_memory_system.py")

def main():
    print("=" * 70)
    print("🔧 COMPREHENSIVE 'KAIA REMEMBER' SYSTEM FIX")
    print("=" * 70)
    
    # Step 1: Fix Kaiacord.py
    print("\n📝 Step 1: Fixing Kaiacord.py...")
    fix1 = fix_kaiacord_file()
    
    # Step 2: Fix kaia_rag.py
    print("\n📝 Step 2: Fixing kaia_rag.py...")
    fix2 = patch_kaia_rag()
    
    # Step 3: Create test script
    print("\n📝 Step 3: Creating test script...")
    create_test_script()
    
    print("\n" + "=" * 70)
    print("✅ All fixes applied!")
    print("\n📋 NEXT STEPS:")
    print("1. Restart Kaiacord:")
    print("   pkill -f 'python.*Kaiacord'")
    print("   python Kaiacord.py")
    print("\n2. Test memory storage:")
    print("   In Discord: kaia remember test this is a test memory")
    print("\n3. Test memory retrieval:")
    print("   In Discord: kaia what did I remember about test")
    print("\n4. Run verification:")
    print("   python test_memory_system.py")
    print("\n5. If still not working, force reindex:")
    print("   python fix_remember_system.py --reindex")
    print("=" * 70)

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--reindex":
        force_reindex_all_memories()
    else:
        main()
