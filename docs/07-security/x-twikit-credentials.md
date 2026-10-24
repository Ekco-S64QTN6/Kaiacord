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

## Cookie Helper

`tools/social/export_x_cookies.py` writes `memory/x_cookies.json` from a
logged-in browser session. With no arguments it tries Chrome, Firefox, Edge and
Chromium; `--cookie-file <cookies.sqlite>` reads one Firefox-family profile
(Firedragon, LibreWolf); `--manual <auth_token> <ct0>` writes the two cookies
that matter, copied from the browser's dev tools. The script holds no
credentials and is safe to commit; its output is not.

## If Cookies Are Compromised

1. Log into X from a browser
2. Go to Settings → Security → Sessions → Sign out all other sessions
3. Delete the leaked cookie file
4. Re-export fresh cookies using `tools/social/export_x_cookies.py`

## Recommendations

- **Never** commit cookie files to version control
- Rotate cookies periodically (re-export from browser)
- Consider switching to OAuth 2.0 if/when twikit supports it
