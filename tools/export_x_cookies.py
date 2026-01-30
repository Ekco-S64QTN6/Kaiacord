#!/usr/bin/env python3
"""
Export X (Twitter) Cookies from Browser
========================================

Extracts authenticated cookies from your browser for use with twikit.

Usage:
    python tools/export_x_cookies.py

Requirements:
    - browser_cookie3 installed
    - Chrome or Firefox with active X login session
"""

import json
import sys
from pathlib import Path

def export_x_cookies():
    """Export X cookies from browser to storage/x_cookies.json"""
    try:
        import browser_cookie3
    except ImportError:
        print("ERROR: browser_cookie3 not installed. Run: pip install browser_cookie3")
        sys.exit(1)
    
    output_path = Path("storage/x_cookies.json")
    output_path.parent.mkdir(exist_ok=True)
    
    print("Searching for X cookies in browsers...")
    
    # Try Chrome first, then Firefox
    browsers = [
        ("Chrome", browser_cookie3.chrome),
        ("Firefox", browser_cookie3.firefox),
        ("Edge", browser_cookie3.edge),
        ("Chromium", browser_cookie3.chromium),
    ]
    
    for browser_name, browser_fn in browsers:
        try:
            print(f"  Trying {browser_name}...")
            cj = browser_fn(domain_name=".x.com")
            
            cookies = {}
            for cookie in cj:
                cookies[cookie.name] = cookie.value
            
            if cookies:
                print(f"  Found {len(cookies)} cookies from {browser_name}")
                
                # Save in twikit-compatible format
                with open(output_path, 'w') as f:
                    json.dump(cookies, f, indent=2)
                
                print(f"\n✅ Exported cookies to {output_path}")
                print(f"   Restart the bot to use these cookies.\n")
                return True
                
        except Exception as e:
            print(f"  {browser_name}: {e}")
            continue
    
    print("\n❌ Could not find X cookies in any browser.")
    print("   Make sure you're logged into x.com in Chrome or Firefox.")
    return False


if __name__ == "__main__":
    success = export_x_cookies()
    sys.exit(0 if success else 1)
