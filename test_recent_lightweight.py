import os
from typing import List, Dict

# Mocking the folder structure for testing the logic
knowledge_base_dir = "./knowledge_base"

def mock_get_recent_files(limit: int = 5) -> List[Dict[str, str]]:
    """Test version of the get_recent_files logic"""
    files = []
    for root, _, filenames in os.walk(knowledge_base_dir):
        context_prefix = ""
        is_log = "user_logs" in root
        is_news = "news" in root
        
        if is_log:
            folder_name = os.path.basename(root)
            if "_" in folder_name:
                username = folder_name.split("_")[0]
                context_prefix = f"Log ({username}): "
            else:
                context_prefix = f"Log ({folder_name}): "
        elif is_news:
            context_prefix = "News: "
        
        for f in filenames:
            path = os.path.join(root, f)
            if f.startswith('.') or not f.endswith(('.txt', '.md', '.pdf', '.docx')):
                continue
                
            mtime = os.path.getmtime(path)
            weight = mtime
            if "daily" in root and f.startswith("news_brief"):
                weight += 3600 * 24
            
            files.append({
                "filename": f,
                "path": path,
                "mtime": mtime,
                "weight": weight,
                "context": context_prefix
            })
    
    files.sort(key=lambda x: x["weight"], reverse=True)
    
    recent_with_snippets = []
    for f_info in files[:limit]:
        snippet = ""
        try:
            if f_info["filename"].endswith(('.txt', '.md')):
                with open(f_info["path"], 'r', encoding='utf-8') as f:
                    content = f.read(500)
                    if "User Log" in content or "Interaction" in content:
                       snippet = content[-300:].strip().replace("\n", " ") + "..."
                    else:
                       snippet = content[:300].strip().replace("\n", " ") + "..."
            elif f_info["filename"].endswith('.pdf'):
                snippet = "[PDF Content Indexed]"
            else:
                snippet = "[Document Indexed]"
        except Exception as e:
            snippet = f"[Error reading: {e}]"
        
        display_name = f_info["filename"]
        if f_info["context"]:
            display_name = f_info["context"] + f_info["filename"]
            
        recent_with_snippets.append({
            "filename": display_name,
            "snippet": snippet
        })
        
    return recent_with_snippets

if __name__ == "__main__":
    recent = mock_get_recent_files(limit=10)
    print("--- Recent Files (Lightweight Test) ---")
    for item in recent:
        print(f"File: {item['filename']}")
        print(f"Snippet: {item['snippet'][:150]}...")
        print("-" * 20)
