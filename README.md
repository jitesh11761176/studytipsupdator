# StudyTips AI Agent 🤖

> Autonomous AI agent for managing [studytips.in](https://studytips.in) — an Indian educational WordPress website. The agent handles content creation, SEO optimisation, design upgrades, page management, and site auditing with minimal human input. **You only press the final approve/publish button.**

[![MIT License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)

---

## Features

- 🧠 **Multi-LLM Brain** — GitHub Copilot, OpenRouter (Claude/GPT-4o), Kimi (128K context), NVIDIA NIM, Local Ollama
- 🔀 **Intelligent Router** — Automatically picks the best LLM per task for cost/quality balance
- 📝 **Content Engine** — Blog post generation, content updates, content calendar planning
- 🔍 **SEO Optimizer** — Meta generation, schema markup, keyword research, internal linking
- 📄 **Page Manager** — Full CRUD with page hierarchy management
- 🎨 **Design Manager** — CSS injection, layout suggestions, responsive audit
- 🖼️ **Media Manager** — Image upload, AI-generated alt text, optimisation
- 📊 **Analytics** — Google Analytics GA4 integration with actionable insights
- 🔎 **Site Auditor** — Broken links, thin content, missing meta, duplicate detection
- 🧭 **Navigation Manager** — Menu and category hierarchy management
- 🤖 **Telegram Bot** — Control the agent from your phone with approve/reject buttons
- ⏰ **Scheduler** — Automated daily/weekly/monthly routines
- 🎛️ **Streamlit Dashboard** — Web UI for interacting with the agent
- 💻 **CLI** — Interactive terminal interface
- 📚 **Self-Learning Memory** — SQLite-backed learning from approvals/rejections

---

## Architecture

```
                    ┌─────────────────────────────────────────┐
                    │          User Interfaces                │
                    │  CLI │ Streamlit Dashboard │ Telegram   │
                    └────────────────┬────────────────────────┘
                                     │
                    ┌────────────────▼────────────────────────┐
                    │          Orchestrator (orchestrator.py) │
                    │  Intent Analysis → Plan → Execute → Review│
                    └────────────────┬────────────────────────┘
                                     │
              ┌──────────────────────▼──────────────────────────┐
              │               Brain Router                      │
              │  Copilot │ OpenRouter │ Kimi │ NVIDIA │ Ollama  │
              └──────────────────────┬──────────────────────────┘
                                     │
    ┌──────────────────────────────── ▼ ─────────────────────────────────┐
    │                            Modules                                │
    │  ContentEngine │ SEOOptimizer │ PageManager │ SiteAuditor │ ...   │
    └──────────────────────────────── ┬ ─────────────────────────────────┘
                                      │
    ┌─────────────────────────────────▼──────────────────────────────────┐
    │                        Integrations                               │
    │  WordPress REST API │ Google Analytics │ Search Console          │
    └────────────────────────────────────────────────────────────────────┘
                                      │
    ┌─────────────────────────────────▼──────────────────────────────────┐
    │                         Memory (SQLite)                           │
    │  action_log │ style_preferences │ content_performance │ knowledge │
    └────────────────────────────────────────────────────────────────────┘
```

---

## Quick Start

### 1. Clone & Install

```bash
git clone https://github.com/chottelal/studytipsengine.git
cd studytipsengine
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your credentials
```

### 3. Set Up WordPress

Create a WordPress Application Password:
- Go to **Users → Profile → Application Passwords**
- Create a new password named "StudyTips Agent"
- Copy it to `WP_APP_PASSWORD` in your `.env`

### 4. Run the Agent

```bash
# Interactive CLI
python run_cli.py

# Web Dashboard
streamlit run dashboard/app.py

# Telegram Bot
python -c "from agent.interfaces.telegram_bot import run_bot; run_bot()"

# Scheduler (background tasks)
python agent/scheduler.py
```

---

## Environment Variables

| Variable | Description | Required |
|---|---|---|
| `WP_SITE_URL` | Your WordPress site URL | ✅ |
| `WP_USERNAME` | WordPress admin username | ✅ |
| `WP_APP_PASSWORD` | WordPress Application Password | ✅ |
| `OPENROUTER_API_KEY` | OpenRouter API key | Optional |
| `GITHUB_COPILOT_TOKEN` | GitHub Copilot Models token | Optional |
| `NVIDIA_API_KEY` | NVIDIA NIM API key | Optional |
| `KIMI_API_KEY` | Kimi / Moonshot AI key | Optional |
| `OLLAMA_HOST` | Ollama server URL | Optional (default: localhost) |
| `OLLAMA_MODEL` | Default Ollama model | Optional (default: llama3.2) |
| `GOOGLE_ANALYTICS_PROPERTY_ID` | GA4 property ID | Optional |
| `GOOGLE_SEARCH_CONSOLE_SITE` | Search Console site URL | Optional |
| `GOOGLE_SERVICE_ACCOUNT_KEY` | Path to Google service account JSON | Optional |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token from @BotFather | Optional |
| `TELEGRAM_ADMIN_CHAT_ID` | Your Telegram chat ID | Optional |
| `DEFAULT_POST_STATUS` | Default WP post status | Optional (default: draft) |

---

## Module Documentation

### `agent/core/orchestrator.py`
Main `StudyTipsAgent` class. Entry point: `agent.process_prompt("your instruction")`.

### `agent/core/brain_router.py`
`BrainRouter` routes tasks to the best LLM. Supports fallback chains.

### `agent/core/memory.py`
`AgentMemory` SQLite store for self-learning. Tracks every interaction.

### `agent/core/config.py`
Loads all environment variables into typed dataclasses.

### `agent/modules/`
| Module | Purpose |
|---|---|
| `content_engine.py` | Blog post & content calendar generation |
| `seo_optimizer.py` | SEO analysis, meta generation, keyword research |
| `page_manager.py` | Page CRUD with hierarchy management |
| `design_manager.py` | CSS, theme, and layout management |
| `media_manager.py` | Image upload and alt text generation |
| `analytics.py` | Google Analytics reporting |
| `site_auditor.py` | Full site health auditor |
| `navigation_manager.py` | Menu and category management |

---

## Running with Docker

```bash
# Build and start all services
docker-compose up --build

# Dashboard available at: http://localhost:8501
```

---

## Deployment

### DigitalOcean App Platform
1. Fork this repo
2. Create a new App from GitHub
3. Set environment variables in the App settings
4. Deploy!

### Railway
```bash
railway login
railway init
railway up
```

### Render
1. Create a new Web Service from GitHub
2. Build command: `pip install -r requirements.txt`
3. Start command: `streamlit run dashboard/app.py`

---

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Commit changes: `git commit -m 'Add my feature'`
4. Push to branch: `git push origin feature/my-feature`
5. Open a Pull Request

Please ensure all new code has docstrings and passes `pytest tests/`.

---

## License

MIT License — see [LICENSE](LICENSE) for details.

Copyright (c) 2026 chottelal
