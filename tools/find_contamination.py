"""
Find EXACT contamination in logs
"""

import re
from pathlib import Path

def find_elena_contamination():
    """Find all instances of 'Elena' and similar hallucinations"""
    log_dir = Path("./knowledge_base/user_logs")
    
    contamination_patterns = [
        (r'\belena\b', "Elena (fictional character)"),
        (r'\bjuanita\b', "Juanita (fictional character)"),
        (r'\bdeane\b', "Deane (fictional character)"),
        (r'\bbonbons\b', "Bonbons (fictional reference)"),
        (r'agency', "Agency (fictional reference)"),
        (r'university network', "University network (fictional story)"),
        (r'behind the curtain', "Behind the curtain (fictional phrase)"),
        (r'slow burn', "Slow burn (fictional phrase)"),
        (r'roundabout questions', "Roundabout questions (fictional phrase)"),
        (r'terrier with a scent', "Terrier with a scent (fictional phrase)"),
        (r'think tank', "Think tank (often fictional in logs)"),
        (r'middle eastern affairs', "Middle eastern affairs (fictional reference)"),
    ]
    
    print("🔍 Searching for contamination...")
    print("=" * 80)
    
    found_any = False
    
    if not log_dir.exists():
        print("❌ User logs directory not found")
        return
        
    for user_folder in log_dir.iterdir():
        if not user_folder.is_dir():
            continue
        
        user_name = user_folder.name.split('_')[0]
        user_found = False
        
        log_files = list(user_folder.glob("interactions_*.txt"))
        
        for log_file in log_files:
            with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read().lower()
                lines = content.split('\n')
            
            for line_num, line in enumerate(lines, 1):
                for pattern, description in contamination_patterns:
                    if re.search(pattern, line, re.IGNORECASE):
                        if not user_found:
                            print(f"\n👤 USER: {user_name}")
                            user_found = True
                            found_any = True
                        
                        print(f"  📄 {log_file.name}:{line_num}")
                        print(f"     {description}: {line.strip()[:100]}...")
    
    if not found_any:
        print("✅ No contamination found in user logs!")
    else:
        print("\n" + "=" * 80)
        print("🚨 CONTAMINATION FOUND!")
        print("\nThese fictional elements are STILL in your logs.")
        print("Run the nuclear reset to remove them completely.")

def check_persona_for_fiction():
    """Check the persona file for any fictional elements"""
    persona_path = Path("./kaia_persona.md") # Fixed path based on project structure
    
    if not persona_path.exists():
        persona_path = Path("./knowledge_base/kaia_persona.md")
        
    if not persona_path.exists():
        print("❌ Persona file not found!")
        return
    
    print(f"\n🔍 Checking persona file: {persona_path}")
    
    with open(persona_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Check for specific fictional names
    fictional_names = ["Elena", "Juanita", "Deane", "Gwaihir", "Reiwa", "Starkond"]
    
    found = False
    for name in fictional_names:
        if name.lower() in content.lower():
            print(f"🚨 Found fictional name in persona: {name}")
            found = True
    
    if not found:
        print("✅ Persona file is clean!")
    else:
        print("\n⚠️  Remove these fictional references from your persona file!")

def main():
    print("🧪 CONTAMINATION DIAGNOSTIC TOOL")
    print("=" * 80)
    
    find_elena_contamination()
    check_persona_for_fiction()
    
    print("\n" + "=" * 80)
    print("💡 RECOMMENDATION:")
    print("If you found contamination, run: python nuclear_reset.py")
    print("Then restart Kaiacord.")

if __name__ == "__main__":
    main()
