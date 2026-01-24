
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.proper_news_reader import ProperNewsReader

def test_reader():
    reader = ProperNewsReader()
    print("Scanning files...")
    reader.scan_news_files()
    
    categories = ["technology", "politics", "security", "business", "science", "general"]
    for cat in categories:
        items = reader.get_news_by_category(cat)
        print(f"Category: {cat}, Items found: {len(items)}")
        if items:
            print(f"  Sample: {items[0]['text'][:100]}...")

if __name__ == "__main__":
    test_reader()
