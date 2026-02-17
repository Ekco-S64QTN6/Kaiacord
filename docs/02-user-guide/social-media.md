# Social Media Setup Guide

Set up Bluesky and X accounts for Kaia to post and reply.

## Bluesky Setup

### 1. Create Account
1. Go to [bsky.app](https://bsky.app) and sign up
2. Pick a handle (e.g., `kaiakuroshi.bsky.social`)

### 2. Create App Password
1. Go to **Settings** → **Privacy and Security** → **App Passwords**
2. Click **Add App Password**
3. Name it something like `kaia-bot`
4. Copy the generated password (looks like `xxxx-xxxx-xxxx-xxxx`)

### 3. Add to `.env`
```env
BLUESKY_HANDLE=yourhandle.bsky.social
BLUESKY_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx
```

---

## X (Twitter) Setup

### 1. Create Account
1. Go to [x.com](https://x.com) and sign up
2. Complete phone/email verification
3. Note your username (without @)

### 2. Security Settings
- **2FA**: If you have 2FA enabled, you may need to log in manually in a browser first
- **CAPTCHA**: First-time bot login may require solving a CAPTCHA in browser

### 3. Add to `.env`
```env
X_USERNAME=YourUsername
X_PASSWORD=YourPassword
X_EMAIL=YourEmail        # Optional: used as secondary auth info
```

> ⚠️ **Note**: Kaia uses [twikit](https://github.com/d60/twikit), an unofficial library. 
> This works like a normal user login, so avoid excessive posting to prevent rate limits.

---

## Configuration

Enable/disable features in `config/kaia.yaml`:

```yaml
bluesky:
  enabled: true
  cross_post_quips: true    # Post idle quips to Bluesky
  reply_to_mentions: true   # Reply when mentioned

x_twitter:
  enabled: true
  cross_post_quips: true    # Post idle quips to X
  reply_to_mentions: true   # Reply when mentioned

social:
  poll_interval_minutes: 1  # How often to check for mentions
  mention_lookback_hours: 3 # How far back to scan for missed mentions
```

---

## How It Works

### Cross-Posting
When Kaia generates an idle quip in Discord, she also posts it to enabled platforms.

### Mention Replies
At the configured polling interval, Kaia checks for mentions on both platforms. When found:
1. Fetches the mention text and thread context (parent/root posts)
2. Generates a response using her full AI persona pipeline (RAG, memory, persona)
3. Replies in-thread

### Thread Safety
- **Per-User Caps**: Maximum 5 replies per user per thread to prevent bot loops.
- **Admin Override**: Handles in `social.admin_handles` bypass thread limits.
- **History Reconstruction**: On startup, Kaia reconstructs thread state from recent posts (Bluesky + X run concurrently via `asyncio.gather`).

### Session Persistence
- **Bluesky**: Uses app password (no session storage needed)
- **X**: Saves session cookies to `memory/x_cookies.json` to avoid re-login

### Resilience

#### Circuit Breakers
Both platforms have independent `CircuitBreaker` instances:
- Opens after 3 consecutive API failures
- Auto-resets after 5-minute timeout
- Prevents cascade failures from blocking the main bot loop

#### 401 Auto-Recovery (X)
If X returns 401/Unauthorized:
1. Cookies are automatically cleared
2. Fresh login is attempted
3. If Cloudflare blocks direct login, browser cookie extraction is attempted (Chrome, Firefox, Firedragon)
4. Extracted cookies are verified for `auth_token` before injection

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Bluesky login fails | Verify app password is correct (not your main password) |
| X login fails | Try logging in via browser first, then restart bot |
| X Cloudflare block | Ensure `browser_cookie3` is installed; log into X in Chrome/Firefox first |
| X rate limited | Reduce posting frequency, wait 15+ minutes |
| Mentions not detected | Check if `reply_to_mentions: true` in config |
| Bot not responding | Check logs for auth errors, re-verify credentials |
| Thread limit reached | Expected behavior — Kaia stops after 5 replies per user per thread |

---

## Files Reference

| File | Purpose |
|------|---------|
| `utils/social/kaia_bluesky.py` | Bluesky API client |
| `utils/social/kaia_twitter.py` | X API client (twikit, lazy-loaded to avoid startup stalls) |
| `utils/social/kaia_social_responder.py` | Mention polling, thread tracking, circuit breakers, AI replies |
| `memory/x_cookies.json` | X session cookies (auto-created) |
| `memory/social_replied_ids.json` | Tracks replied mentions and per-user thread counts |
