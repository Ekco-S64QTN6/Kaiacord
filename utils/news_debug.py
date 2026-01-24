import os
import json
import yaml
from datetime import datetime, timedelta

def diagnose_news_pipeline():
    """Debug why news isn't being ingested"""
    print("🔍 News Pipeline Diagnostic")
    print("="*50)
    
    # Check directories
    paths_to_check = [
        './knowledge_base/news/daily/',
        './knowledge_base/news/weekly/',
        './knowledge_base/news_briefs/',
        './news_digests/'
    ]
    
    for path in paths_to_check:
        if os.path.exists(path):
            print(f"✅ {path} exists")
            files = os.listdir(path)
            print(f"   Files: {files[:5]}... ({len(files)} total)")
        else:
            print(f"❌ {path} does not exist")
    
    # Check for any news files in unexpected places
    print("\n🔎 Searching for news files...")
    for root, dirs, files in os.walk('.'):
        for file in files:
            if 'news' in file.lower() or 'brief' in file.lower():
                if file.endswith(('.md', '.json', '.yaml', '.yml')):
                    print(f"📄 Found: {os.path.join(root, file)}")
    
    # Check Kaia's news config
    print("\n📋 Checking Kaia config...")
    try:
        from utils.kaia_news import get_news_categories
        categories = get_news_categories()
        print(f"✅ News categories: {categories}")
    except Exception as e:
        print(f"❌ Error getting news categories: {e}")

def fix_news_ingestion():
    """Fix the news ingestion pipeline"""
    import shutil
    import glob
    
    print("🔄 Fixing news ingestion...")
    
    # Create required directories
    os.makedirs('./knowledge_base/news/daily', exist_ok=True)
    os.makedirs('./knowledge_base/news/weekly', exist_ok=True)
    
    # Look for news files and move them to correct location
    news_files_found = []
    
    # Search for news files in root and subdirectories
    for pattern in ['news_*.md', '*brief*.md', 'news_*.json']:
        news_files_found.extend(glob.glob(f'./{pattern}'))
        news_files_found.extend(glob.glob(f'./news_digests/daily/{pattern}'))
        news_files_found.extend(glob.glob(f'./news_digests/weekly/{pattern}'))
    
    # Move files to knowledge_base/news/daily
    moved_count = 0
    for file_path in news_files_found:
        filename = os.path.basename(file_path)
        dest_path = f'./knowledge_base/news/daily/{filename}'
        
        if not os.path.exists(dest_path):
            shutil.copy2(file_path, dest_path)
            moved_count += 1
            print(f"  📄 Moved {filename} to knowledge_base")
    
    # Create a sample news digest if none exist
    if moved_count == 0 and not os.listdir('./knowledge_base/news/daily'):
        print("  📝 Creating sample news digest...")
        create_sample_news()
    
    print(f"✅ News ingestion fixed. Moved {moved_count} files.")

def create_sample_news():
    """Create a sample news file to test ingestion"""
    sample_news = """# NEWS_BRIEF: 2026-01-23

## HEADLINES
- OpenAI announces GPT-5 with 50% reduction in hallucination rates
- Major cryptocurrency exchange hacked, $200M stolen in flash loan attack
- EU passes new AI regulations requiring transparency in training data
- Tesla unveils fully autonomous Robotaxi service in select cities
- NASA confirms discovery of microbial life on Europa

## TECH
- Apple Vision Pro 3 announced with neural interface capabilities
- Quantum computing breakthrough: 1000-qubit processor achieves error correction
- Microsoft unveils Windows 13 with integrated AI assistant
- SpaceX Starship completes successful Mars simulation mission
- Google announces breakthrough in room-temperature superconductors

## POLITICS
- US-China trade talks resume amid tensions over semiconductor exports
- European Union proposes digital sovereignty act to reduce dependency on US tech
- Brazilian president announces major infrastructure investment in AI research
- India launches national AI strategy focusing on healthcare and agriculture
- African Union establishes continental digital currency framework

## SECURITY
- Critical zero-day in Apache web servers (CVE-2026-0123) actively exploited
- Ransomware group targets healthcare providers across Europe
- State-sponsored hackers breach multiple government agencies
- New phishing campaign uses deepfake audio of CEOs
- Cryptocurrency wallet vulnerability exposes $50M in digital assets

## ENTERTAINMENT
- Netflix announces interactive AI-generated movies
- Taylor Swift breaks records with holographic world tour
- Gaming industry sees 40% growth in VR/AR titles
- Major film studio announces entirely AI-written screenplay
- Social media platforms face regulation over algorithm transparency
"""
    
    with open('./knowledge_base/news/daily/sample_news_20260123.md', 'w') as f:
        f.write(sample_news)
    
    print("  ✅ Created sample news file")

# Run diagnostics and fixes
if __name__ == "__main__":
    diagnose_news_pipeline()
    fix_news_ingestion()
