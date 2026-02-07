#!/usr/bin/env python3
"""
Log Sanitization Script - Purge RAG-Contaminated Entries

This script scans user interaction logs for entries where Kaia incorrectly
attributed or confused documents (e.g., mixing Deus Ex with Dune).

It will:
1. Scan all user log files for confusion patterns
2. Quarantine (move) or redact contaminated entries
3. Optionally trigger a RAG re-index to flush stale data

Usage:
    python purge_confused_logs.py --dry-run     # Preview what would be purged
    python purge_confused_logs.py --purge       # Actually purge/quarantine entries
    python purge_confused_logs.py --reindex     # Trigger RAG refresh after purge
"""

import os
import re
import sys
import shutil
import argparse
from datetime import datetime
from pathlib import Path

# Configuration
KNOWLEDGE_BASE_DIR = Path(__file__).parent.parent.parent / "knowledge_base"
USER_LOGS_DIR = KNOWLEDGE_BASE_DIR / "user_logs"
QUARANTINE_DIR = KNOWLEDGE_BASE_DIR / "quarantine"
STORAGE_DIR = Path(__file__).parent.parent.parent / "storage"

# Confusion patterns: (wrong attribution, correct source)
# Format: List of tuples (pattern_regex, description)
CONFUSION_PATTERNS = [
    # Dune/Deus Ex confusion
    (r"(?i)herbert.*deus\s*ex", "Herbert attributed to Deus Ex"),
    (r"(?i)deus\s*ex.*herbert", "Deus Ex attributed to Herbert"),
    (r"(?i)dune.*jc\s*denton", "Dune mixed with JC Denton"),
    (r"(?i)arrakis.*unatco", "Arrakis mixed with UNATCO"),
    (r"(?i)spice.*nano.*aug", "Spice mixed with nano-augmentation"),
    (r"(?i)fremen.*nanotech", "Fremen mixed with nanotech"),
    (r"(?i)paul\s*atreides.*majestic", "Paul Atreides mixed with Majestic-12"),
    
    # General misattribution patterns
    (r"(?i)Kaia:.*wrong\s*book", "Kaia acknowledged wrong book"),
    (r"(?i)Kaia:.*different\s*story", "Kaia acknowledged different story"),
    (r"(?i)Kaia:.*my\s*apologies.*thinking\s*of\s*something\s*else", "Kaia acknowledged confusion"),
    
    # Specific to the incident - Herbert themes applied to Deus Ex
    (r"(?i)deus\s*ex.*revolution.*power\s*structures.*herbert", "Herbert themes on Deus Ex"),
]

# Blocklist: Entries containing these exact phrases should be quarantined
BLOCKLIST_PHRASES = [
    "Herbert wrote Dune. It's more about highlighting",  # The exact confused response
    "Right you are. My apologies. I was thinking of something else",  # Acknowledgment of error
]


def scan_log_file(filepath: Path, dry_run: bool = True) -> list:
    """Scan a single log file for contaminated entries."""
    contaminated = []
    
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
    except Exception as e:
        print(f"  [ERROR] Could not read {filepath}: {e}")
        return []
    
    # Split by interaction blocks (--- timestamp ---)
    blocks = re.split(r'(--- \d{8}_\d{6} ---)', content)
    
    # Reconstruct blocks with their headers
    entries = []
    i = 0
    while i < len(blocks):
        if re.match(r'--- \d{8}_\d{6} ---', blocks[i]):
            header = blocks[i]
            body = blocks[i+1] if i+1 < len(blocks) else ""
            entries.append((header, body))
            i += 2
        else:
            # Orphan content (before first timestamp)
            if blocks[i].strip():
                entries.append(("", blocks[i]))
            i += 1
    
    for header, body in entries:
        full_entry = header + body
        
        # Check blocklist first (exact phrase match)
        for phrase in BLOCKLIST_PHRASES:
            if phrase in full_entry:
                contaminated.append({
                    "file": str(filepath),
                    "header": header.strip(),
                    "reason": f"Blocklist: '{phrase[:50]}...'",
                    "content": full_entry[:300] + "..." if len(full_entry) > 300 else full_entry
                })
                break
        else:
            # Check regex patterns
            for pattern, description in CONFUSION_PATTERNS:
                if re.search(pattern, full_entry):
                    contaminated.append({
                        "file": str(filepath),
                        "header": header.strip(),
                        "reason": description,
                        "content": full_entry[:300] + "..." if len(full_entry) > 300 else full_entry
                    })
                    break
    
    return contaminated


def scan_all_logs(dry_run: bool = True) -> list:
    """Scan all user log directories for contaminated entries."""
    all_contaminated = []
    
    if not USER_LOGS_DIR.exists():
        print(f"[ERROR] User logs directory not found: {USER_LOGS_DIR}")
        return []
    
    print(f"[SCAN] Scanning user logs in: {USER_LOGS_DIR}")
    print(f"[SCAN] Patterns loaded: {len(CONFUSION_PATTERNS)}")
    print(f"[SCAN] Blocklist phrases: {len(BLOCKLIST_PHRASES)}")
    print()
    
    for user_dir in USER_LOGS_DIR.iterdir():
        if not user_dir.is_dir():
            continue
        
        print(f"  Scanning {user_dir.name}...")
        
        for log_file in user_dir.glob("*.txt"):
            contaminated = scan_log_file(log_file, dry_run)
            if contaminated:
                print(f"    [!] Found {len(contaminated)} contaminated entries in {log_file.name}")
                all_contaminated.extend(contaminated)
    
    return all_contaminated


def quarantine_entries(contaminated: list) -> int:
    """Move contaminated log files to quarantine and redact entries."""
    if not contaminated:
        return 0
    
    # Create quarantine directory
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    quarantine_path = QUARANTINE_DIR / f"purge_{timestamp}"
    quarantine_path.mkdir(parents=True, exist_ok=True)
    
    # Group by file
    files_affected = {}
    for entry in contaminated:
        filepath = entry["file"]
        if filepath not in files_affected:
            files_affected[filepath] = []
        files_affected[filepath].append(entry)
    
    purged_count = 0
    
    for filepath, entries in files_affected.items():
        filepath = Path(filepath)
        
        # Backup original file
        backup_name = f"{filepath.parent.name}_{filepath.name}"
        backup_path = quarantine_path / backup_name
        shutil.copy2(filepath, backup_path)
        print(f"  [BACKUP] {filepath.name} -> quarantine/{backup_name}")
        
        # Read and redact
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            # Redact each contaminated entry
            for entry in entries:
                header = entry["header"]
                if header:
                    # Find and remove the entire block
                    # Match from header to next header or EOF
                    pattern = re.escape(header) + r'.*?(?=--- \d{8}_\d{6} ---|$)'
                    redacted = f"{header}\n[REDACTED: {entry['reason']}]\n\n"
                    content = re.sub(pattern, redacted, content, flags=re.DOTALL)
                    purged_count += 1
            
            # Write redacted content
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            
            print(f"  [REDACT] {len(entries)} entries redacted in {filepath.name}")
            
        except Exception as e:
            print(f"  [ERROR] Failed to redact {filepath}: {e}")
    
    return purged_count


def nuke_storage_index():
    """Remove the RAG storage index to force a full re-index."""
    logs_index = STORAGE_DIR / "logs"
    
    if logs_index.exists():
        print(f"[NUKE] Removing logs index: {logs_index}")
        shutil.rmtree(logs_index)
        print(f"[NUKE] Logs index removed. RAG will rebuild on next startup.")
    else:
        print(f"[NUKE] Logs index not found at {logs_index}")


def main():
    parser = argparse.ArgumentParser(description="Purge RAG-contaminated log entries")
    parser.add_argument("--dry-run", action="store_true", help="Preview what would be purged")
    parser.add_argument("--purge", action="store_true", help="Actually purge/redact entries")
    parser.add_argument("--reindex", action="store_true", help="Nuke logs index to force rebuild")
    parser.add_argument("--all", action="store_true", help="Purge and reindex in one step")
    
    args = parser.parse_args()
    
    if not any([args.dry_run, args.purge, args.reindex, args.all]):
        parser.print_help()
        print("\n[INFO] Use --dry-run to preview, --purge to execute, --all for full cleanup")
        return
    
    print("=" * 60)
    print("RAG Log Sanitization Script")
    print("=" * 60)
    print()
    
    # Scan
    contaminated = scan_all_logs(dry_run=not args.purge and not args.all)
    
    print()
    print(f"[RESULT] Found {len(contaminated)} contaminated entries")
    
    if contaminated:
        print()
        print("Contaminated entries:")
        for i, entry in enumerate(contaminated[:10]):  # Show first 10
            print(f"  {i+1}. [{entry['reason']}]")
            print(f"     File: {Path(entry['file']).name}")
            print(f"     Header: {entry['header']}")
            print()
        
        if len(contaminated) > 10:
            print(f"  ... and {len(contaminated) - 10} more")
    
    # Purge
    if args.purge or args.all:
        print()
        print("[PURGE] Starting purge operation...")
        purged = quarantine_entries(contaminated)
        print(f"[PURGE] Redacted {purged} entries")
    
    # Reindex
    if args.reindex or args.all:
        print()
        nuke_storage_index()
    
    print()
    print("=" * 60)
    print("Done. Restart Kaia to apply changes.")
    print("=" * 60)


if __name__ == "__main__":
    main()
