# emergency_fix.py
# Run this to apply quick fixes

import os

print("🔧 Applying emergency fixes...")

# Fix 1: Patch Kaiacord.py - Handle string nodes
kaiacord_path = "Kaiacord.py"
with open(kaiacord_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Replace the problematic line
old_code = """content = getattr(node, 'text', '') or getattr(node, 'content', '') or str(node)"""
new_code = '''# SAFE FIX: Handle both strings and node objects
        if hasattr(node, 'text'):
            content = node.text
        elif hasattr(node, 'content'):
            content = node.content
        elif isinstance(node, dict) and 'text' in node:
            content = node['text']
        elif isinstance(node, dict) and 'content' in node:
            content = node['content']
        else:
            content = str(node)

        # Also get metadata safely
        if hasattr(node, 'metadata'):
            metadata = node.metadata
        elif isinstance(node, dict) and 'metadata' in node:
            metadata = node['metadata']
        else:
            metadata = {}'''

if old_code in content:
    content = content.replace(old_code, new_code)
    with open(kaiacord_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("✅ Fixed RAG node handling")
else:
    print("⚠️  Could not find the problematic line")

# Fix 2: Add get_stats() to kaia_rag.py if needed
rag_path = "utils/kaia_rag.py"
if os.path.exists(rag_path):
    with open(rag_path, 'r', encoding='utf-8') as f:
        rag_content = f.read()
    
    if 'def get_stats' not in rag_content:
        # Find the class definition
        lines = rag_content.split('\n')
        in_class = False
        for i, line in enumerate(lines):
            if 'class KaiaRAG' in line:
                in_class = True
            if in_class and line.strip() == '':
                # Insert get_stats method
                get_stats_method = '''
    def get_stats(self) -> Dict[str, Any]:
        """Get RAG statistics for dashboard"""
        total_docs = 0
        for index in self.indices.values():
            total_docs += len(index.docstore.docs)
            
        # Calculate total size of persist_dir
        total_size = 0
        for dirpath, dirnames, filenames in os.walk(self.persist_dir):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                total_size += os.path.getsize(fp)
        
        size_str = f"{total_size / 1024 / 1024:.1f} MB"
        
        return {
            "total_documents": total_docs,
            "index_size": size_str,
            "last_refresh": datetime.now()
        }'''
                
                lines.insert(i + 1, get_stats_method)
                break
        
        rag_content = '\n'.join(lines)
        with open(rag_path, 'w', encoding='utf-8') as f:
            f.write(rag_content)
        print("✅ Added get_stats() method to KaiaRAG")
else:
    print("⚠️  kaia_rag.py not found")

print("\n✅ Emergency fixes applied!")
print("Restart Kaiacord and test.")
