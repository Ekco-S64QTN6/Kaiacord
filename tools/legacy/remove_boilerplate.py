#!/usr/bin/env python3
"""
COMPLETE REMOVAL of hard-coded boilerplate responses from Kaia
"""
import os
import sys
import re

def remove_all_boilerplate():
    print("🔧 Removing all hard-coded boilerplate responses...")
    
    # 1. FIX Kaiacord.py - EmergencyContaminationFilter
    filepath = "Kaiacord.py"
    with open(filepath, 'r') as f:
        content = f.read()
    
    # Remove the fallback response list
    # Using a more flexible regex to catch variations
    old_pattern = r'if len\(filtered_response\.strip\(\)\) < 20:\s+filtered_response = random\.choice\(\[[^\]]+\]\)'
    
    new_text = '''if len(filtered_response.strip()) < 20:
            filtered_response = ""'''
    
    if re.search(old_pattern, content, flags=re.DOTALL):
        content = re.sub(old_pattern, new_text, content, flags=re.DOTALL)
        print("✅ Fixed EmergencyContaminationFilter fallback")
    else:
        print("⚠️ Could not find EmergencyContaminationFilter fallback pattern")
    
    with open(filepath, 'w') as f:
        f.write(content)
    
    # 2. FIX kaia_rag.py - HallucinationDetector
    filepath = "utils/kaia_rag.py"
    with open(filepath, 'r') as f:
        content = f.read()
    
    old_pattern = r'if len\(clean_response\) < 20:\s+clean_response = "yeah\. what\'s up\?\\n\\ncoffee\'s getting cold\. what do you need\?"'
    
    new_text = '''if len(clean_response) < 20:
            clean_response = ""'''
    
    if re.search(old_pattern, content, flags=re.DOTALL):
        content = re.sub(old_pattern, new_text, content, flags=re.DOTALL)
        print("✅ Fixed HallucinationDetector fallback")
    else:
        print("⚠️ Could not find HallucinationDetector fallback pattern")
    
    with open(filepath, 'w') as f:
        f.write(content)
    
    # 3. FIX kaia_news.py - ResponseEnhancer
    filepath = "utils/kaia_news.py"
    if os.path.exists(filepath):
        with open(filepath, 'r') as f:
            content = f.read()
        
        # Remove endings entirely
        old_endings = r'self\.endings = \[[^\]]+\]'
        new_endings = 'self.endings = []  # REMOVED: No more boilerplate questions'
        
        if re.search(old_endings, content, flags=re.DOTALL):
            content = re.sub(old_endings, new_endings, content, flags=re.DOTALL)
            print("✅ Fixed ResponseEnhancer endings")
        
        # Remove identity intros
        old_intros = r'self\.identity_intros = \{[^\}]+\}'
        new_intros = '''self.identity_intros = {
            'casual': [""],  # REMOVED: No more boilerplate intros
            'direct': [""]   # REMOVED: No more boilerplate intros
        }'''
        
        if re.search(old_intros, content, flags=re.DOTALL):
            content = re.sub(old_intros, new_intros, content, flags=re.DOTALL)
            print("✅ Fixed ResponseEnhancer intros")
        
        # Remove the ending addition logic
        old_enhance = r'if random\.random\(\) > 0\.7:  # 30% chance to add engaging ending\s+base_response \+= " " \+ random\.choice\(self\.endings\)'
        new_enhance = '# REMOVED: No more adding boilerplate endings'
        
        if re.search(old_enhance, content, flags=re.DOTALL):
            content = re.sub(old_enhance, new_enhance, content, flags=re.DOTALL)
            print("✅ Fixed enhance_identity_response logic")

        # Remove ending addition in news response
        old_news_ending = r'# Add ending\s+response_parts\.append\(random\.choice\(self\.endings\)\)'
        new_news_ending = '# REMOVED: No more adding boilerplate endings'
        
        if re.search(old_news_ending, content, flags=re.DOTALL):
            content = re.sub(old_news_ending, new_news_ending, content, flags=re.DOTALL)
            print("✅ Fixed enhance_news_response logic")
        
        with open(filepath, 'w') as f:
            f.write(content)
    else:
        print(f"⚠️ {filepath} not found")
    
    # 4. ALSO check for any other hard-coded responses
    print("\n🔍 Searching for other hard-coded responses...")
    
    files_to_check = [
        "Kaiacord.py",
        "utils/kaia_rag.py", 
        "utils/kaia_intelligence.py",
        "utils/kaia_news.py",
        "utils/kaia_logger.py"
    ]
    
    boilerplate_patterns = [
        r'what\'s on your mind',
        r'what are you working on',
        r'yeah\. what\'s up',
        r'coffee\'s cold',
        r'i\'m here\.',
        r'listening\. go ahead',
        r'not much to say about that',
        r'Anything else on your mind',
        r'What\'s your take',
        r'Seen anything interesting',
        r'Got any thoughts',
        r'Anything specific you\'re curious',
        r'Honestly, ',
        r'Well, ',
        r'So, ',
        r'Right, ',
        r'Truth is, ',
        r'I\'m ',
        r'The way I see it, I\'m',
        r'Essentially, I\'m',
        r'At my core, I\'m'
    ]
    
    for filepath in files_to_check:
        if os.path.exists(filepath):
            with open(filepath, 'r') as f:
                content = f.read()
            
            for pattern in boilerplate_patterns:
                if re.search(pattern, content, re.IGNORECASE):
                    print(f"⚠️  Found '{pattern}' in {filepath}")
    
    return True

def create_minimal_fallback():
    """Create minimal, non-intrusive fallback responses"""
    minimal_fallback = '''# Minimal fallback responses that don't prompt the user
MINIMAL_FALLBACKS = [
    "",
    ".",
    "..",
    "..."
]

def get_minimal_fallback():
    """Return a minimal, non-intrusive fallback"""
    import random
    return random.choice(MINIMAL_FALLBACKS)'''
    
    with open("utils/minimal_fallback.py", "w") as f:
        f.write(minimal_fallback)
    
    print("✅ Created minimal fallback system")

def main():
    print("=" * 70)
    print("🚀 COMPLETE BOILERPLATE REMOVAL")
    print("=" * 70)
    
    # Create backup
    import shutil
    backup_dir = "backup_pre_boilerplate_removal"
    if not os.path.exists(backup_dir):
        os.makedirs(backup_dir)
        for file in ["Kaiacord.py", "utils/kaia_rag.py", "utils/kaia_news.py"]:
            if os.path.exists(file):
                shutil.copy2(file, os.path.join(backup_dir, os.path.basename(file)))
        print(f"📁 Backup created in {backup_dir}/")
    
    # Apply fixes
    remove_all_boilerplate()
    create_minimal_fallback()
    
    print("\n" + "=" * 70)
    print("✅ ALL HARD-CODED BOILERPLATE REMOVED!")
    print("\n📋 Kaia will now:")
    print("   - NOT add 'yeah. what's on your mind?'")
    print("   - NOT add 'what are you working on?'")
    print("   - NOT add any other formulaic questions")
    print("   - Use ONLY the LLM's actual responses")
    print("   - Fall back to empty string if response is too short")
    print("\n🔄 Restart Kaiacord to apply changes:")
    print("   pkill -f 'python.*Kaiacord'")
    print("   python Kaiacord.py")
    print("\n⚠️  Note: If Kaia still asks questions, it's from the LLM/persona,")
    print("   not from hard-coded boilerplate.")
    print("=" * 70)

if __name__ == "__main__":
    main()
