# Graph Report - .  (2026-09-18)

## Corpus Check
- Corpus is ~1,312 words - fits in a single context window. You may not need a graph.

## Summary
- 34 nodes · 55 edges · 8 communities (7 shown, 1 thin omitted)
- Extraction: 93% EXTRACTED · 7% INFERRED · 0% AMBIGUOUS · INFERRED: 4 edges (avg confidence: 0.85)
- Token cost: 58,363 input · 0 output

## Community Hubs (Navigation)
- Gmail IMAP Access Layer
- Poll-Summarize-Telegram Flow
- Poll Endpoint & Auth
- Project Overview & Telegram Setup
- Delivery Dedup State (SQLite)
- Gmail Credentials & Env Config
- Vertex AI / Gemini Setup
- Health Check Route

## God Nodes (most connected - your core abstractions)
1. `poll()` - 7 edges
2. `email-assistant Project` - 7 edges
3. `get_new_emails()` - 6 edges
4. `_parse_message()` - 5 edges
5. `.env Secrets File` - 5 edges
6. `get_latest_emails()` - 4 edges
7. `is_delivered()` - 4 edges
8. `mark_delivered()` - 4 edges
9. `Google Cloud Vertex AI Setup` - 4 edges
10. `/poll Endpoint` - 4 edges

## Surprising Connections (you probably didn't know these)
- `email-assistant Project` --references--> `Flask==3.1.3`  [EXTRACTED]
  README.md → requirements.txt
- `python-dotenv==1.2.3` --shares_data_with--> `.env Secrets File`  [INFERRED]
  requirements.txt → README.md
- `poll()` --calls--> `get_new_emails()`  [EXTRACTED]
  server.py → gmail.py
- `poll()` --calls--> `is_delivered()`  [EXTRACTED]
  server.py → state.py
- `poll()` --calls--> `mark_delivered()`  [EXTRACTED]
  server.py → state.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **README Setup Prerequisites (Gmail, Telegram, Vertex AI)** — readme_gmail_app_password, readme_telegram_bot, readme_google_cloud_vertex_ai, readme_env_file [EXTRACTED 1.00]
- **Project Runtime Dependencies** — requirements_flask, requirements_python_telegram_bot, requirements_python_dotenv, requirements_google_genai [EXTRACTED 1.00]

## Communities (8 total, 1 thin omitted)

### Community 0 - "Gmail IMAP Access Layer"
Cohesion: 0.39
Nodes (8): _connect(), _decode(), _extract_body(), get_latest_emails(), get_new_emails(), _parse_message(), Fetch the latest emails from Gmail (read or unread), most recent first., Fetch and return unseen INBOX emails, marking them as seen. On the very first…

### Community 1 - "Poll-Summarize-Telegram Flow"
Cohesion: 0.70
Nodes (3): poll(), send_telegram_message(), summarize_email()

### Community 2 - "Poll Endpoint & Auth"
Cohesion: 0.50
Nodes (4): baseline_established First-Run Sentinel, /poll Endpoint, POLL_TOKEN Shared Secret, Flask==3.1.3

### Community 3 - "Project Overview & Telegram Setup"
Cohesion: 0.67
Nodes (4): email-assistant Project, Root Health Check Endpoint, Telegram Bot (via BotFather), python-telegram-bot==22.8

### Community 4 - "Delivery Dedup State (SQLite)"
Cohesion: 0.83
Nodes (3): _connect(), is_delivered(), mark_delivered()

### Community 5 - "Gmail Credentials & Env Config"
Cohesion: 0.67
Nodes (3): .env Secrets File, Gmail App Password, python-dotenv==1.2.3

### Community 6 - "Vertex AI / Gemini Setup"
Cohesion: 0.67
Nodes (3): Google Cloud Vertex AI Setup, service-account.json Credentials File, google-genai==2.23.0

## Knowledge Gaps
- **4 isolated node(s):** `service-account.json Credentials File`, `Root Health Check Endpoint`, `python-dotenv==1.2.3`, `google-genai==2.23.0`
  These have ≤1 connection - possible missing edges or undocumented components.
- **1 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `email-assistant Project` connect `Project Overview & Telegram Setup` to `Poll Endpoint & Auth`, `Gmail Credentials & Env Config`, `Vertex AI / Gemini Setup`?**
  _High betweenness centrality (0.075) - this node is a cross-community bridge._
- **Why does `get_new_emails()` connect `Gmail IMAP Access Layer` to `Poll-Summarize-Telegram Flow`?**
  _High betweenness centrality (0.073) - this node is a cross-community bridge._
- **Why does `poll()` connect `Poll-Summarize-Telegram Flow` to `Gmail IMAP Access Layer`, `Delivery Dedup State (SQLite)`, `Health Check Route`?**
  _High betweenness centrality (0.050) - this node is a cross-community bridge._
- **What connects `service-account.json Credentials File`, `Root Health Check Endpoint`, `python-dotenv==1.2.3` to the rest of the system?**
  _4 weakly-connected nodes found - possible documentation gaps or missing edges._