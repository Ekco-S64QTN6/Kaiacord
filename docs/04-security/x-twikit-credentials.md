# X/Twitter (twikit) Credential Security

## Risk Summary

Kaiacord uses [twikit](https://github.com/d60/twikit) for X/Twitter integration. Twikit authenticates via browser session cookies (not OAuth), which means:

> [!CAUTION]
> Cookie files (`cookies.json`, `x_cookies.json`) contain **live session tokens**. If leaked, an attacker has full access to the X account until the session expires or is manually revoked.

## What's Protected

| File/Pattern | Status | Notes |
|---|---|---|
| `.env` | ✅ `.gitignore` | API keys, Discord token |
| `cookies.json` | ✅ `.gitignore` | Twikit session cookies |
| `x_cookies.json` | ✅ `.gitignore` | Alternate cookie filename |
| `*.cookies` | ✅ `.gitignore` | Catch-all for cookie exports |

## Cookie Helper Scripts

These scripts in `tools/social/` are utilities for extracting/managing X cookies:

- `export_x_cookies.py` — Exports cookies from browser via `browser_cookie3`
- `extract_firedragon_cookies.py` — Extracts cookies from Firedragon browser
- `manual_x_cookies.py` — Manual cookie entry tool

These scripts are **safe to commit** — they don't contain credentials, only the logic to extract them.

## If Cookies Are Compromised

1. Log into X from a browser
2. Go to Settings → Security → Sessions → Sign out all other sessions
3. Delete the leaked cookie file
4. Re-export fresh cookies using `tools/social/export_x_cookies.py`

## Recommendations

- **Never** commit cookie files to version control
- Rotate cookies periodically (re-export from browser)
- Consider switching to OAuth 2.0 if/when twikit supports it
