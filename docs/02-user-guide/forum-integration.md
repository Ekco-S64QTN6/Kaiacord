# 🏟️ Forum Integration, Scraping, & Moderation

A VBulletin 3.x client and crawler in her social layer (`utils/social/kaia_forum.py`)
lets Kaia read and take part in the Project 1999 forums. She never writes there
unaided: every post is drafted, reviewed by a human in `#kaia-opolis`, and posted
only on approval.

---

## ⚙️ What she actually does there

Posting on a forum is not the same act as replying in Discord. In Discord she is
addressed; on Project 1999 she is choosing to interject among strangers who did not
ask to hear from her. The bar is therefore *"would a regular find this a welcome
contribution from a person"*, and the failure mode to avoid is being read as a
bot and resented. Everything below exists to serve that goal. To be clear about
provenance: that is the operator's stated aim, not a diagnosis — no post of hers
has been reported as reading like a bot.

### Off-Topic (Forum 19) — **on**

Two different acts, budgeted differently.

**Interjecting** — walking into a stranger's thread uninvited. Four gates, in
order, each of which can silently and correctly result in no post:

| Gate | Setting | Default |
|---|---|---|
| **Lurking** — has she read enough of this forum to have any business posting in it | `min_threads_before_posting` / `min_users_before_posting` | 15 threads, 25 users |
| **Window** — a time a person would plausibly be awake and posting | `post_window_start_hour` / `post_window_end_hour` | 00:00–04:00 local (wraps midnight) |
| **Budget** — a couple a night, well spaced, and never twice in one thread | `max_posts_per_day`, `min_hours_between_posts`, `thread_cooldown_hours` | 2/day, 4h apart, 72h per thread |
| **Interest** — is this a thread *she* would answer | `min_interest_score` | 3.0 |

**Conversing** — answering someone who answered her. **Not capped, not
windowed, not subject to the thread cooldown.** She is not capped in Discord
either, and going quiet for three days after someone replies to you is rude
rather than restrained. The watch list is every thread in her ledger, so nobody
has to add threads by hand.

The only guard on conversation is the narrow one: `min_minutes_between_replies`
(20), plus a requirement that something new was actually posted since her last
message in that thread. That second condition exists for one failure mode —
unbounded reply-on-reply, which matters most in the case hardest to spot, two
bots answering each other.

The auto-post task polls hourly; the gates decide. **If nothing on the front
page clears the interest threshold, she posts nothing** — that is the correct
outcome, not a failure.

Interest is scored (`utils/social/forum_participation.py`) against her own
beliefs and anchors rather than a hand-written keyword list, so what she finds
worth answering drifts as she does. Titles weigh more than bodies, questions
score higher, 3,000-reply megathreads and near-empty threads score lower.

Each term is also weighted by how much it narrows down *which* thread this is,
measured over her own scraped corpus. Her belief keywords include ordinary words
— "problem", "system", "keep", "sure" — and matching on those scored small talk
as highly as the threads she has something to say about. Against the real 81
threads that put 86% over the threshold, so the "nothing tonight" valve never
fired. Now: `keep` 0.24, `problem` 0.36, `privacy` 0.84, `surveillance` 1.00, and
34 of 81 threads are eligible. A
thread that **mentions her by name** gets a large boost regardless of topic:
interest is built from her beliefs, so a thread discussing the bot itself scores
near zero on subject matter while being the clearest case of all where a reply
is wanted. Add any other names people call her to `forum.also_known_as`.

Frequency is tracked in a durable ledger at `memory/forum_post_ledger.json`,
which distinguishes openers from replies. It used to live in an in-memory list
on the client, which meant every restart reset the daily cap — the exact shape
of failure that produces a burst of posts and an annoyed forum.

### Technical Discussion (Forum 40) — **off**

Gated separately by `forum.tech_support_enabled`, which is `false`. Unsolicited
technical answers are a different promise from joining a conversation: this flow ran
without reliably staying inside the wiki and troubleshooting docs it was supposed to
be grounded in, and giving strangers confidently wrong EQ advice is worse than saying
nothing. It has its own switch specifically so that turning Off-Topic posting back on
does not quietly reinstate it.

---

## 🗣️ How she writes there

**Forum drafts go through the same pipeline as Discord replies** — the same RAG
retrieval, the same memory, the same dual-temperature split, the same
post-generation safety stack. There used to be two implementations, and the
auto-post one hand-rolled its prompt and called the model directly at a fixed
temperature with no memory at all. That is why her forum voice drifted from her
Discord voice. `utils/social/forum_drafting.py` is now the single path for both
openers and replies.

`FORUM_POST_GUIDANCE` (`utils/social/forum_participation.py`) is appended to her
persona for forum drafts only. It rules out the tells that make a post read as
generated: greeting the thread, addressing people by name, thanking them for
their post, closing by inviting further discussion, signing off, summarising the
thread back at it, agreeing enthusiastically, and slipping into assistant
register.

It does **not** ask her to hide what she is. If someone asks directly, she
answers plainly and briefly, the way she would in Discord, and carries on with
whatever the thread was about.

### The same pipeline as Discord

Forum drafts go through `message_processor` with no platform-specific handling
at all. The prompt assembled for a forum post is byte-identical to the one
assembled for the same input in Discord — `test_pipeline_parity.py` asserts it
by building both and comparing them.

Everything that once made the forum different has been removed: a guidance block
telling it to "say one thing", a "write at least 3-4 complete sentences"
instruction, an addressee anchor Discord got and the forum was excluded from, a
fallback Discord would not accept, and a larger input cap. Each one produced a
different failure, and every one of them was invisible to the test suite because
prompt text is not code.

The thread reaches her as **conversation history**, the same channel memory
Discord reads: her own posts become assistant turns, everyone else's become user
turns prefixed with their name. The live scrape supplies the most recent posts
and the locally scraped copy under `knowledge_base/forum_posts/` supplies the
earlier ones, up to `MAX_THREAD_HISTORY_TURNS` (12).

Those scraped threads are deliberately **not** in the RAG index
(`kaia_rag_indexer.py`): indexing strangers' forum claims would let them surface
as grounded fact in unrelated conversations. Reading the thread she is posting
in, as context for that post, is scoped to that thread and is what the local
copy is for.

### Reply chains

She always quotes the post she is answering, producing the standard vBulletin
`[QUOTE=name;postid]` block — the same thing the **Reply With Quote** button
makes, rendering as *Originally Posted by* with a jump link. On P99 that is how
you indicate who you are talking to; a bare reply in a busy thread has no
visible referent.

Whatever that post was itself quoting is stripped first (`own_words`), so her
quote box never reproduces a third party's words under the wrong name.

### Who is who

Forum handles and Discord names do not match — `magnetaress` on P99 is Starkind in
Discord — so the mapping lives in `knowledge_base/identity_registry.json` and has to be
recorded rather than guessed. When an account is linked, her profile of it says so
(*"magnetaress — this is Starkind from Discord"*) and the profiler is told it is someone
she already talks to, not a stranger who happens to post here.

**Her own forum account is marked as self.** Without that it was simply the 213th user the
scraper found, and it wrote her a profile reading *"a forum user… haven't formed a strong
opinion yet"* — a memory of herself as a stranger, retrievable in conversation.

Link an account with `!forum link <forum_id>`, or edit the registry directly.

The periodic scraper only deep-scrapes people it finds in *recent* threads, so anyone
quiet for a few months never gets a real profile. To build one on demand:

```
python tools/maintenance/refresh_forum_profiles.py --linked   # everyone she knows
python tools/maintenance/refresh_forum_profiles.py --user 228819
python tools/maintenance/refresh_forum_profiles.py --stubs --limit 20
```

### Not repeating herself

Nothing used to measure whether her posts were converging. The thread cooldown
stops her revisiting one thread and interest scoring varies the topics, but
neither notices if five consecutive posts open the same way or make the same
point. In Discord that blind spot showed up as a bare-name opener on 22.4% of
turns, and on a forum it is worse: her posts sit permanently side by side on a
profile page.

Every draft is scored against her posts from the last two weeks, on shared
openings and on content overlap. Above `forum.max_self_similarity` (0.5) the
draft is held. Holding costs nothing — she posts twice a night at most, and a
skipped one is invisible.

## 🔎 Checking on it

`!forum status` (owner-only) reports the two things that explain silence:

```
  off-topic posting: True
  tech support posting: False
  posting window: 00:00–04:00 local (open)
  lurking: reading (0/15 threads, 0/25 forum users read)
  posts today: 0/2
```

Every post — opener or reply — goes to `#kaia-opolis` for approval first.
`forum.auto_reply` lifts that for replies only, and is off by default.

**After a fresh start she will not post until the lurk counter clears.** It is fed
by the scrape task (`forum.auto_scrape`), which walks the top five threads of page
one every thirty minutes — so from empty it takes about a day. To clear it in one
run instead:

```
python tools/maintenance/backfill_forum_corpus.py --pages 4
```

(also in `kaia-tools` → Knowledge Base → *Backfill P99 Off-Topic*). Someone whose
first act in a community is to post has not read the room.

---

## 🛡️ Zero-Hallucination Support Guardrails

These apply to the technical flow, which is currently disabled:
- **Strict RAG Grounding**: queries verified Project 1999 wiki files (`knowledge_base/wiki/`) and synthesized community troubleshooting cheat sheets (`knowledge_base/troubleshooting/`).
- **Hallucination Detection**: the post-generation pipeline filters fabricated URLs, hallucinated user handles, and unsupported configuration recommendations before drafting.
- **No Speculation**: if RAG cannot resolve the issue, Kaia defaults to admitting uncertainty.
- **Disclaimer Footer**: every technical answer terminates with
  `Disclaimer: I am an AI agent and might make mistakes and hopefully a human comes by soon to help you if I was unable to`

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
