#!/usr/bin/env python3
import requests
from bs4 import BeautifulSoup
from pathlib import Path
import os
import sys

# Add project root to path
sys.path.append(os.getcwd())
from utils.infrastructure.logging.kaia_logger import log_info, log_error

WIKI_URLS = [
    "https://wiki.project1999.com/Everquest_Titanium_Installation_Guide",
    "https://wiki.project1999.com/Tech_Support",
    "https://wiki.project1999.com/Getting_Started",
    "https://wiki.project1999.com/WinEQ",
    "https://wiki.project1999.com/Camp_Rules",
    "https://wiki.project1999.com/Camp_Rules_FAQ",
    "https://wiki.project1999.com/Install",
    "https://wiki.project1999.com/Green_UI",
    "https://wiki.project1999.com/Players:Technical",
    "https://wiki.project1999.com/Players:Technical/Affinity",
    "https://wiki.project1999.com/Play_Nice_Policy",
    "https://wiki.project1999.com/Linux",
    "https://wiki.project1999.com/Mac",
    "https://wiki.project1999.com/Enchanter",
    "https://wiki.project1999.com/Resurrection",
    "https://wiki.project1999.com/Pet_Guide",
    "https://wiki.project1999.com/Corpse",
    "https://wiki.project1999.com/Charm",
    "https://wiki.project1999.com/Game_Mechanics",
    "https://wiki.project1999.com/Loraen%27s_Enchanter_Guide",
    "https://wiki.project1999.com/Sesserdrix%27s_All_in_One_Necromancer_Strategy_Guide",
    "https://wiki.project1999.com/Xornns_Enchanter_Guide",
    "https://wiki.project1999.com/Charmed_Pet_Gear",
    "https://wiki.project1999.com/Thrasos%27_Bard_Guide",
    "https://wiki.project1999.com/J.C._Smith%27s_Cleric_Guide",
    "https://wiki.project1999.com/Greyweasel%27s_Shaman_Guide",
    "https://wiki.project1999.com/Guide_to_Canni_Dancing",
    "https://wiki.project1999.com/Going_Solo_Guide",
    "https://wiki.project1999.com/Per-Level_Hunting_Guide",
]

def scrape_wiki():
    print("--- Scraping P99 Wiki for Technical Knowledge ---")
    
    output_dir = Path("./knowledge_base/wiki")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    })
    
    for url in WIKI_URLS:
        print(f"Fetching {url}...")
        try:
            resp = session.get(url, timeout=15)
            resp.raise_for_status()
            
            soup = BeautifulSoup(resp.text, 'html.parser')
            title_tag = soup.find('title')
            title = title_tag.get_text(strip=True).replace(' - Project 1999 Wiki', '') if title_tag else "Wiki Page"
            
            content_div = soup.find('div', id='mw-content-text')
            
            if not content_div:
                print(f"Could not find mw-content-text on {url}")
                continue
                
            # Basic HTML to Markdown formatting
            for h in content_div.find_all(['h1', 'h2', 'h3', 'h4']):
                h.insert_before('\n\n## ' + h.get_text(strip=True) + '\n')
            
            for li in content_div.find_all('li'):
                li.insert_before('\n- ')
            
            for p in content_div.find_all('p'):
                p.insert_before('\n')
                p.insert_after('\n')
                
            text = content_div.get_text()
            
            # Clean up excessive newlines
            lines = text.split('\n')
            clean_lines = []
            for line in lines:
                line = line.strip()
                if line or (clean_lines and clean_lines[-1] != ""):
                    clean_lines.append(line)
                    
            final_text = '\n'.join(clean_lines)
            
            filename = f"wiki_{title.replace(' ', '_').replace('/', '_')}.md"
            filepath = output_dir / filename
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(f"# {title}\n")
                f.write(f"Source: {url}\n\n")
                f.write(final_text)
                
            print(f"  ✓ Saved to {filename}")
            
        except Exception as e:
            print(f"  ✗ Error scraping {url}: {e}")
            
if __name__ == "__main__":
    scrape_wiki()
