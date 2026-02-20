import urllib.request
from bs4 import BeautifulSoup

url = "http://68k.news/"
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
try:
    with urllib.request.urlopen(req) as response:
        html = response.read()
except Exception as e:
    exit(1)

soup = BeautifulSoup(html, 'html.parser')

with open('debug_68k.txt', 'w', encoding='utf-8') as f:
    for a_tag in soup.find_all('a'):
        text = a_tag.get_text(strip=True)
        if len(text) > 25:
            f.write(repr(text) + '\n')
