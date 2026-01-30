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
```

---

## How It Works

### Cross-Posting
When Kaia generates an idle quip in Discord, she also posts it to enabled platforms.

### Mention Replies
Every 5 minutes, Kaia checks for mentions on both platforms. When found:
1. Fetches the mention text
2. Generates a response using her AI persona
3. Replies in-thread

### Session Persistence
- **Bluesky**: Uses app password (no session storage needed)
- **X**: Saves session cookies to `storage/x_cookies.json` to avoid re-login

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Bluesky login fails | Verify app password is correct (not your main password) |
| X login fails | Try logging in via browser first, then restart bot |
| X rate limited | Reduce posting frequency, wait 15+ minutes |
| Mentions not detected | Check if `reply_to_mentions: true` in config |
| Bot not responding | Check logs for auth errors, re-verify credentials |

---

## Files Reference

| File | Purpose |
|------|---------|
| `utils/kaia_bluesky.py` | Bluesky API client |
| `utils/kaia_twitter.py` | X API client (twikit) |
| `utils/kaia_social_responder.py` | Mention polling & AI replies |
| `storage/x_cookies.json` | X session cookies (auto-created) |
| `storage/social_replied_ids.json` | Tracks replied mentions |
