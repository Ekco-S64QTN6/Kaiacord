import browser_cookie3
import json
from pathlib import Path

def extract_x_cookies():
    cookie_file = "/home/ekco/.var/app/org.garudalinux.firedragon/.firedragon/zgc5mher.default-release/cookies.sqlite"
    output_path = "memory/x_cookies.json"
    
    print(f"Attempting to extract cookies from: {cookie_file}")
    
    try:
        # browser_cookie3.firefox can take a cookie_file argument
        domains = ['twitter.com', 'x.com', '.twitter.com', '.x.com']
        twikit_cookies = []
        
        for domain in domains:
            try:
                cj = browser_cookie3.firefox(cookie_file=cookie_file, domain_name=domain)
                for cookie in cj:
                    twikit_cookies.append({
                        "name": cookie.name,
                        "value": cookie.value,
                        "domain": cookie.domain,
                        "path": cookie.path,
                        "expires": cookie.expires,
                        "secure": cookie.secure,
                        "httpOnly": cookie.has_nonstandard_attr('httponly') if hasattr(cookie, 'has_nonstandard_attr') else False
                    })
            except:
                continue
        
        if twikit_cookies:
            Path("memory").mkdir(exist_ok=True)
            with open(output_path, 'w') as f:
                json.dump(twikit_cookies, f, indent=2)
            print(f"SUCCESS: Extracted {len(twikit_cookies)} cookies to {output_path}")
            return True
        else:
            print("FAILED: No twitter.com cookies found in that database.")
            return False
            
    except Exception as e:
        print(f"ERROR: {e}")
        return False

if __name__ == "__main__":
    extract_x_cookies()
