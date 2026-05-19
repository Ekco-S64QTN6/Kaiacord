# 🏟️ Forum Integration, Scraping, & Moderation

Kaiacord features a sophisticated VBulletin 3.x client and crawler integrated into her social layer (`utils/social/kaia_forum.py`). This allows her to act as a community participant and a technical helper on the Project 1999 Forums, under human moderation.

---

## ⚙️ Subforum Operations

The crawler executes periodic schedules (configured for every 6 hours) targeting two distinct forums:

### 1. Off-Topic (Forum 19)
- **Objective**: Natural, community-focused discussion.
- **Limit**: Capped at 2-3 drafted posts per 6-hour cycle to avoid flooding.
- **Behavior**: Scans active threads, replies to discussions, and quotes users naturally when relevant.

### 2. Technical Discussion (Forum 40)
- **Objective**: Automated, high-quality technical support.
- **Focus**: Targets newly created threads and unanswered community questions.
- **Disclaimer Footer**: Every technical answer must terminate with the mandatory footer:
  `Disclaimer: I am an AI agent and might make mistakes and hopefully a human comes by soon to help you if I was unable to`

---

## 🛡️ Zero-Hallucination Support Guardrails

To ensure Kaia provides reliable advice on setups, errors, and system requirements, the support engine operates under strict factual constraints:
- **Strict RAG Grounding**: The prompt query queries verified Project 1999 wiki files (`knowledge_base/wiki/`) and synthesized community troubleshooting cheat sheets (`knowledge_base/troubleshooting/`).
- **Hallucination Detection**: The post-generation pipeline parses replies to filter out fabricated URLs, hallucinated user handles, or unsupported configuration recommendations before drafting.
- **No Speculation**: If the RAG context cannot resolve the issue, Kaia politely defaults to admitting uncertainty.

---

## 🚦 Discord Moderation Queue (`#kaia-opolis`)

To guarantee safety and prevent automated errors, Kaia never writes directly to the forum without human review.

### Draft Submission
- When the scraper identifies a thread to reply to, Kaia generates a draft.
- The draft is sent as a rich Discord embed to the configured moderation channel `#kaia-opolis`.
- If the draft is a quote-reply, the embed displays both the quoted post context and Kaia's proposed response.

### Interactive View
- Embeds are accompanied by Discord UI buttons (`ForumDraftReviewView` in `kaia_forum.py`):
  - **🟢 Accept**: Submits the post immediately to the Project 1999 forum using the bot's credentials, incrementing the "Approved" dashboard stat.
  - **🔴 Reject**: Deletes the Discord draft message, incrementing the "Rejected" dashboard stat.
- **Access Control**: By design, there are no per-user or administrative locks on the review buttons. Anyone with channel access to `#kaia-opolis` can review, accept, or reject Kaia's drafts.

---

## 📝 Moderation Logging & RLHF

To enable reinforcement learning from human feedback (RLHF) and fine-tune Kaia's forum persona:
- All moderation decisions (both approvals and rejections) are logged thread-safely to `memory/forum_moderation_log.jsonl`.
- Each log entry is saved as an append-only JSON line containing:
  - `timestamp`: UTC ISO 8601 timestamp.
  - `action`: `'approved'` or `'rejected'`.
  - `user` / `user_id`: Username and ID of the moderator.
  - `thread_id` / `thread_title`: Target forum thread identifiers.
  - `forum_type`: `'technical'` (Technical support) or `'off_topic'` (Off-topic chatter).
  - `draft`: The exact text draft presented for review.
- This dataset serves as a gold standard corpus for future behavioral alignment and personality tuning.

---

## 🗄️ Crawler Caching & Delta Deduplication

To prevent excessive server requests and respect forum bandwidth, the crawler employs intelligent caching policies:
- **Dossier Crawler**: Scrapes active posters' profiles to build unified RAG dossiers.
- **Scrape Limits**: Deep crawls are capped at a maximum of 20 post pages and 10 started thread pages per user.
- **Cooldown Caching**:
  - Profile metadata: 1-hour cooldown.
  - Full post history: 4-hour cooldown.
- **Delta Check**: The crawler first scrapes the user's lightweight profile page. It only fetches the user's detailed post list if their total post count has changed since the last cached crawl.
