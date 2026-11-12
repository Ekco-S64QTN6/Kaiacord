# Security Policy

Kaiacord is a self-hosted Discord bot run by one maintainer. It holds a Discord token,
third-party API keys, forum credentials and cookie-based social sessions, fetches URLs that
users supply, and parses files they attach, so reports are welcome.

## Supported versions

Only the current `main` branch is supported. There are no release branches and no backports: a
fix lands on `main`, and a deployment gets it by updating to `main`.

## Reporting a vulnerability

**Do not open a public issue, pull request or discussion for a vulnerability.**

Report it privately through GitHub:
**[Report a vulnerability](https://github.com/Ekco-S64QTN6/Kaiacord/security/advisories/new)**
(the repository's *Security* tab, then *Report a vulnerability*). The report is visible only to
you and the maintainer. There is no security email address; this form is the reporting route.

Please include:

- what is affected: the file, command or integration, and the commit you tested
- what an attacker can do, and what access they need to do it (any Discord user, a server
  member, someone who can post on a scraped forum, local access to the host)
- steps to reproduce, or a proof of concept
- any configuration it depends on (which integrations are enabled)

Do not include live tokens, cookies or other people's messages in a report. If you found a
credential in the repository or its history, say where it is, not what it is.

## What to expect

- **Acknowledgement** within 7 days. This is a one-person project; a report is read by a person,
  not a queue.
- **Triage** follows the acknowledgement: whether it reproduces, how serious it is, and whether a
  fix is planned. You will be told if the report is declined and why.
- **Fix and disclosure**: the fix is developed in the private advisory and merged to `main`. The
  advisory is published once the fix is on `main`, and credits you unless you ask not to be
  named. Please allow 90 days from your report before disclosing it yourself, and say so in the
  report if you need a different date.

## Scope

In scope: this repository's code and its default configuration, including prompt-injection
paths that reach stored memory, another user's private data, or a public post; SSRF in the URL,
image and PDF fetchers; credential or session exposure; and anything a Discord user without
owner rights can do that the owner-only gates are meant to prevent.

Out of scope: vulnerabilities in dependencies with no path through this code (report those
upstream), Discord, Ollama, X or Bluesky themselves, and what the model says in character.
Reports that need an already-compromised host or owner account are read but are unlikely to be
treated as vulnerabilities.

## Credentials

If a credential may have been exposed, rotate it first and report afterwards. Rotation and
storage of the X session cookies is covered in
[X / twikit credentials](docs/07-security/x-twikit-credentials.md); the Discord token and API
keys live in `.env`, which is never committed.
