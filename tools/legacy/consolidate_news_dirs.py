#!/usr/bin/env python3
"""
Consolidate duplicate news directories into a single structure
Moves all news files to: knowledge_base/news/
"""

import os
import shutil
from pathlib import Path
import sys

def consolidate_news_directories():
    """Merge all news directories into a clean structure"""
    base_path = Path("./knowledge_base")
    
    # Define target structure
    target_dir = base_path / "news"
    target_daily = target_dir / "daily"
    target_weekly = target_dir / "weekly"
    target_archive = target_dir / "archive"
    
    # Create target directories
    target_daily.mkdir(parents=True, exist_ok=True)
    target_weekly.mkdir(parents=True, exist_ok=True)
    target_archive.mkdir(parents=True, exist_ok=True)
    
    print("📁 Consolidating news directories...")
    
    # Source directories to scan
    source_dirs = [
        base_path / "news_briefs",
        base_path / "news" / "daily",
        base_path / "news" / "weekly",
        base_path / "daily",
        base_path / "weekly"
    ]
    
    moved_count = 0
    duplicate_count = 0
    
    for source_dir in source_dirs:
        if not source_dir.exists():
            continue
        
        print(f"  🔍 Scanning {source_dir}")
        
        # Collect all files
        for ext in ["*.md", "*.json", "*.yaml", "*.yml", "*.txt"]:
            for file_path in source_dir.rglob(ext):
                if file_path.is_file():
                    # Skip if already in target (avoid moving file to itself)
                    if target_dir in file_path.parents:
                        continue

                    # Determine target subdirectory based on filename
                    filename = file_path.name
                    if "weekly" in filename.lower() or "weekly" in str(file_path.parent).lower():
                        target_subdir = target_weekly
                    elif "daily" in filename.lower() or "daily" in str(file_path.parent).lower():
                        target_subdir = target_daily
                    else:
                        target_subdir = target_daily  # Default
                    
                    target_path = target_subdir / filename
                    
                    # Handle duplicates
                    if target_path.exists():
                        # Add timestamp to duplicate
                        timestamp = os.path.getmtime(file_path)
                        from datetime import datetime
                        dt = datetime.fromtimestamp(timestamp)
                        new_name = f"{file_path.stem}_{dt.strftime('%Y%m%d_%H%M')}{file_path.suffix}"
                        target_path = target_subdir / new_name
                        duplicate_count += 1
                    
                    # Move file
                    try:
                        shutil.move(str(file_path), str(target_path))
                        moved_count += 1
                    except shutil.Error as e:
                        print(f"  ⚠️ Error moving {file_path}: {e}")

    
    # Clean up empty source directories
    for source_dir in source_dirs:
        if source_dir.exists() and source_dir != target_dir and not (target_dir in source_dir.parents):
            try:
                # Check if directory is empty
                if not any(source_dir.iterdir()):
                    source_dir.rmdir()
                    print(f"  🗑️ Removed empty directory: {source_dir}")
            except Exception as e:
                print(f"  ⚠️ Could not remove {source_dir}: {e}")
    
    # Remove the duplicate news_briefs directory if it's empty
    news_briefs_dir = base_path / "news_briefs"
    if news_briefs_dir.exists() and news_briefs_dir != target_dir:
        try:
            if not any(news_briefs_dir.iterdir()):
                news_briefs_dir.rmdir()
                print(f"  🗑️ Removed empty news_briefs directory")
            else:
                print(f"  ⚠️ news_briefs directory still has files")
        except Exception as e:
            print(f"  ⚠️ Could not remove news_briefs: {e}")
    
    print(f"\n✅ Consolidation complete:")
    print(f"   📄 Moved {moved_count} files")
    print(f"   🔄 Renamed {duplicate_count} duplicates")
    print(f"   🎯 Target structure:")
    print(f"      - {target_daily}/")
    print(f"      - {target_weekly}/")
    print(f"      - {target_archive}/")
    
    # List contents
    print(f"\n📋 Current contents:")
    for subdir in [target_daily, target_weekly, target_archive]:
        if subdir.exists():
            files = list(subdir.glob("*"))
            print(f"  {subdir.name}/: {len(files)} files")
            for f in files[:5]:  # Show first 5 files
                print(f"    - {f.name}")
            if len(files) > 5:
                print(f"    ... and {len(files) - 5} more")

if __name__ == "__main__":
    consolidate_news_directories()
