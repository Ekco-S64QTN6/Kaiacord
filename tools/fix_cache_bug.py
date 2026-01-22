"""
Fix semantic cache keyword pollution bug
"""

import json
import os
import re
from typing import Dict, List, Optional

class CacheBugFixer:
    def __init__(self):
        self.cache_file = "semantic_cache.json"
        self.rogue_keywords = ["68k.news", "juanita", "deane", "agency", "bonbons"]
        
    def analyze_cache(self) -> Dict:
        """Analyze cache for keyword pollution"""
        if not os.path.exists(self.cache_file):
            return {"error": "Cache file not found"}
        
        with open(self.cache_file, 'r', encoding='utf-8') as f:
            cache_data = json.load(f)
        
        pollution_report = {
            "total_entries": len(cache_data),
            "polluted_entries": 0,
            "keywords_found": {},
            "problematic_entries": []
        }
        
        for query, entry in cache_data.items():
            found_keywords = []
            for keyword in self.rogue_keywords:
                if keyword.lower() in query.lower():
                    found_keywords.append(keyword)
            
            if found_keywords:
                pollution_report["polluted_entries"] += 1
                pollution_report["problematic_entries"].append({
                    "query": query[:100] + "..." if len(query) > 100 else query,
                    "keywords": found_keywords,
                    "response_preview": entry.get("response", "")[:200] + "..." if len(entry.get("response", "")) > 200 else entry.get("response", "")
                })
                
                for keyword in found_keywords:
                    pollution_report["keywords_found"][keyword] = pollution_report["keywords_found"].get(keyword, 0) + 1
        
        return pollution_report
    
    def fix_cache(self, mode: str = "selective") -> Dict:
        """Fix the cache by removing polluted entries"""
        if not os.path.exists(self.cache_file):
            return {"error": "Cache file not found"}
        
        with open(self.cache_file, 'r', encoding='utf-8') as f:
            cache_data = json.load(f)
        
        original_count = len(cache_data)
        
        # Different cleaning modes
        if mode == "nuclear":
            # Remove all entries with rogue keywords
            cleaned_cache = {}
            for query, entry in cache_data.items():
                has_rogue_keyword = any(keyword.lower() in query.lower() for keyword in self.rogue_keywords)
                if not has_rogue_keyword:
                    cleaned_cache[query] = entry
        elif mode == "aggressive":
            # Remove entries where rogue keywords dominate
            cleaned_cache = {}
            for query, entry in cache_data.items():
                # Count rogue keywords vs total words
                words = query.lower().split()
                rogue_count = sum(1 for keyword in self.rogue_keywords if keyword.lower() in query.lower())
                
                # If more than 30% of the query is rogue keywords, remove it
                if rogue_count == 0 or (rogue_count / max(len(words), 1)) < 0.3:
                    cleaned_cache[query] = entry
        else:  # selective mode (default)
            # Only remove entries where ALL keywords are rogue
            cleaned_cache = {}
            for query, entry in cache_data.items():
                words = query.lower().split()
                rogue_words = [w for w in words if any(kw in w for kw in [k.lower() for k in self.rogue_keywords])]
                
                # If less than half the query consists of rogue keywords, keep it
                if len(rogue_words) / max(len(words), 1) < 0.5:
                    cleaned_cache[query] = entry
        
        # Save cleaned cache
        with open(self.cache_file, 'w', encoding='utf-8') as f:
            json.dump(cleaned_cache, f, indent=2)
        
        return {
            "original_entries": original_count,
            "remaining_entries": len(cleaned_cache),
            "removed_entries": original_count - len(cleaned_cache),
            "mode": mode
        }
    
    def create_cache_exceptions(self):
        """Create exceptions list for problematic keywords"""
        exceptions = {
            "never_cache": [
                "68k.news",
                "headlines from",
                "january", "february", "march", "april", "may", "june",
                "july", "august", "september", "october", "november", "december",
                "2025", "2026", "2027"
            ],
            "always_regenerate": [
                "news", "headline", "article", "report",
                "update", "breaking", "latest"
            ],
            "keyword_blacklist": self.rogue_keywords
        }
        
        with open("cache_exceptions.json", "w") as f:
            json.dump(exceptions, f, indent=2)
        
        return exceptions

def main():
    fixer = CacheBugFixer()
    
    print("🔍 Analyzing semantic cache for keyword pollution...")
    report = fixer.analyze_cache()
    
    if "error" in report:
        print(f"❌ Error: {report['error']}")
        # Still create exceptions list even if cache doesn't exist
        exceptions = fixer.create_cache_exceptions()
        print(f"\n📋 Created cache exceptions list anyway.")
        return
    
    print(f"\n📊 Cache Analysis Report:")
    print(f"   Total entries: {report['total_entries']}")
    print(f"   Polluted entries: {report['polluted_entries']}")
    
    if report['keywords_found']:
        print(f"\n🚨 Found polluted keywords:")
        for keyword, count in report['keywords_found'].items():
            print(f"   - {keyword}: {count} entries")
    
    if report['problematic_entries']:
        print(f"\n📝 Sample problematic entries:")
        for i, entry in enumerate(report['problematic_entries'][:3], 1):
            print(f"\n   {i}. Query: {entry['query']}")
            print(f"      Keywords: {', '.join(entry['keywords'])}")
            print(f"      Response: {entry['response_preview']}")
    
    # In non-interactive mode for the agent, we'll default to aggressive as per plan
    print("\n" + "="*50)
    print("Running aggressive cleanup as per implementation plan...")
    result = fixer.fix_cache("aggressive")
    
    if result.get("mode") != "exceptions_only":
        print(f"\n✅ Cache cleanup complete:")
        print(f"   Original entries: {result.get('original_entries', 'N/A')}")
        print(f"   Remaining entries: {result.get('remaining_entries', 'N/A')}")
        print(f"   Removed entries: {result.get('removed_entries', 'N/A')}")
        print(f"   Mode: {result.get('mode', 'N/A')}")
    
    # Create exceptions list
    exceptions = fixer.create_cache_exceptions()
    print(f"\n📋 Created cache exceptions list:")
    print(f"   Never cache: {len(exceptions['never_cache'])} keywords/phrases")
    print(f"   Always regenerate: {len(exceptions['always_regenerate'])} categories")
    print(f"   Keyword blacklist: {len(exceptions['keyword_blacklist'])} terms")
    
    print("\n" + "="*50)
    print("✅ Fix applied.")

if __name__ == "__main__":
    main()
