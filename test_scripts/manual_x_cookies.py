import json
from pathlib import Path
import sys

def create_manual_cookies(auth_token, ct0):
    output_path = "memory/x_cookies.json"
    
    # Twikit 2.x expects a flat dictionary of {name: value}
    twikit_cookies = {
        "auth_token": auth_token,
        "ct0": ct0
    }
    
    Path("memory").mkdir(exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(twikit_cookies, f, indent=2)
    
    print(f"SUCCESS: Created manual cookies at {output_path}")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python3 manual_cookies.py <auth_token> <ct0>")
    else:
        create_manual_cookies(sys.argv[1], sys.argv[2])
