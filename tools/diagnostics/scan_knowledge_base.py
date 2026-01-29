"""
scan_knowledge_base.py - Find and quarantine problematic files
"""

import os
import shutil
import re
from pathlib import Path

def scan_for_phantom_names():
    """Scan knowledge base for phantom names that shouldn't be there"""
    knowledge_base_dir = Path("./knowledge_base")
    config_dir = Path("./config")
    quarantine_dir = knowledge_base_dir / "quarantine"
    quarantine_dir.mkdir(exist_ok=True)
    
    # Names that definitely shouldn't be in Kaia's knowledge base
    phantom_names = [
        "juanita", "deane", "bonbons", "agency", 
        "ekco", "gwaihir", "reiwa", "starkond", "starkind"
    ]
    
    # File extensions to check
    extensions = ['.txt', '.md', '.pdf', '.docx', '.json']
    
    found_files = []
    
    for ext in extensions:
        for file_path in knowledge_base_dir.rglob(f"*{ext}"):
            # Skip quarantine and user logs (those should stay)
            if "quarantine" in str(file_path) or "user_logs" in str(file_path):
                continue
                
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read().lower()
                    
                    for name in phantom_names:
                        if name in content:
                            found_files.append((file_path, name))
                            break
            except:
                continue
    
    # Move problematic files to quarantine
    moved_files = []
    for file_path, found_name in found_files:
        quarantine_path = quarantine_dir / file_path.name
        counter = 1
        while quarantine_path.exists():
            quarantine_path = quarantine_dir / f"{file_path.stem}_{counter}{file_path.suffix}"
            counter += 1
            
        shutil.move(str(file_path), str(quarantine_path))
        moved_files.append((file_path.name, found_name))
    
    return moved_files

def check_persona_integrity():
    """Ensure kaia_persona.md is properly indexed and has priority"""
    persona_path = Path("knowledge_base/kaia_persona.md")
    
    if not persona_path.exists():
        print("❌ CRITICAL: kaia_persona.md not found in config/")
        return False
    
    # Check if persona contains any phantom names
    with open(persona_path, 'r', encoding='utf-8') as f:
        content = f.read().lower()
        
    phantom_names = ["juanita", "deane", "agency", "bonbons"]
    for name in phantom_names:
        if name in content:
            print(f"⚠️  WARNING: Phantom name '{name}' found in persona file!")
            return False
    
    print("✓ Persona file integrity check passed")
    return True

def main():
    print("🔍 Scanning knowledge base for phantom content...")
    
    # Check persona first
    if not check_persona_integrity():
        print("\n⚠️  Please fix kaia_persona.md before continuing")
        return
    
    # Scan for phantom names
    moved_files = scan_for_phantom_names()
    
    if moved_files:
        print(f"\n🚨 Found {len(moved_files)} problematic files:")
        for filename, found_name in moved_files:
            print(f"  - {filename} (contains '{found_name}') -> moved to quarantine")
        
        print("\n⚠️  These files were moved to ./knowledge_base/quarantine/")
        print("⚠️  Review them and either delete or clean them before re-adding")
    else:
        print("\n✓ No phantom content found in knowledge base")
    
    # List remaining files for verification
    print("\n📁 Remaining files in knowledge base:")
    kb_dir = Path("./knowledge_base")
    for item in kb_dir.iterdir():
        if item.is_file() and item.suffix in ['.txt', '.md', '.pdf']:
            print(f"  - {item.name}")
        elif item.is_dir() and item.name not in ['quarantine', 'user_logs']:
            print(f"  📂 {item.name}/")

if __name__ == "__main__":
    main()
