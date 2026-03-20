# mattermost-owui-bot

![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python&logoColor=white)
![WebSocket](https://img.shields.io/badge/Transport-WebSocket-green)
![Open WebUI](https://img.shields.io/badge/AI-Open%20WebUI-black?logo=openai&logoColor=white)
![Mattermost](https://img.shields.io/badge/Platform-Mattermost-0058CC?logo=mattermost&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-yellow)
![Status](https://img.shields.io/badge/Status-Working-brightgreen)

> Connect any Open WebUI model to Mattermost as a real chatbot — with DMs, thread following, and conversation memory. No plugin required. Pure Python.

---

## Why This Exists

[Open WebUI](https://github.com/open-webui/open-webui) is one of the best self-hosted AI platforms available. It lets you run powerful language models locally — Llama, Mistral, Gemma, and more — through a beautiful web interface backed by Ollama.

The problem: **your team lives in Mattermost, not in a browser tab.**

Every time someone needs to ask the AI something, they have to open a separate browser window, log into Open WebUI, start a new chat. That friction kills adoption.

This project solves that. It bridges Open WebUI directly into Mattermost — so your team can chat with any OWUI model right inside their normal workflow, without ever leaving the app they already use all day.

No enterprise plugin. No complex infrastructure. Just a single Python file that connects the two systems together in under 5 minutes.

---

## What Is Open WebUI?

Open WebUI is a self-hosted, feature-rich web interface for running AI language models locally. It supports:

- Any model available on [Ollama](https://ollama.com) — Llama 3, Mistral, Gemma, DeepSeek, and hundreds more
- Knowledge bases and RAG (retrieval-augmented generation)
- Model customization — system prompts, parameters, personas
- User and group management
- An OpenAI-compatible API — meaning anything that works with OpenAI also works with Open WebUI

This bot uses that OpenAI-compatible API to route Mattermost messages directly to any model you have loaded.

---

## Features

| Feature | Description |
|---|---|
| **Direct Messages** | DM the bot for a private AI conversation with full memory |
| **Thread Following** | Mention the bot once — it follows and replies to the whole thread automatically |
| **Conversation Context** | Full thread and DM history is sent to the model on every reply |
| **Memory Reset** | Type `/reset` in a DM to start fresh |
| **Any OWUI Model** | Switch models by changing one line in your `.env` file |
| **Zero Dependencies** | Only one external library — `websockets` |

---

## How It Works

```
You type in Mattermost
        │
        ▼  WebSocket (real-time event stream)
    bot.py
        │
        ▼  HTTP POST /api/chat/completions  (OpenAI-compatible)
    Open WebUI
        │
        ▼  internal model routing
  Ollama + your LLM model
        │
        ▼  REST API reply
  Your message appears in Mattermost
```

The bot maintains a persistent WebSocket connection to Mattermost. When a message arrives, it fetches the full conversation history and sends it to Open WebUI's OpenAI-compatible endpoint. The AI reply is posted back as a thread reply or DM — exactly where the user expects it.

---

## Prerequisites

- **Python 3.10+**
- **[Open WebUI](https://github.com/open-webui/open-webui)** running with at least one model loaded
- **[Ollama](https://ollama.com)** (or any backend supported by Open WebUI)
- **Mattermost** — Team Edition or higher
- Admin access to Mattermost to create a bot account

---

## Quick Start

### 1. Clone and install

```bash
git clone https://github.com/YOUR_USERNAME/mattermost-owui-bot.git
cd mattermost-owui-bot
pip install -r requirements.txt
```

### 2. Spin up Open WebUI with Ollama

If you don't have Open WebUI running yet, here's the fastest way:

```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Pull a lightweight model (1.3GB, runs on CPU)
ollama pull llama3.2:1b

# Configure Ollama to listen on all interfaces
mkdir -p /etc/systemd/system/ollama.service.d/
echo -e "[Service]\nEnvironment=\"OLLAMA_HOST=0.0.0.0:11434\"" \
  > /etc/systemd/system/ollama.service.d/override.conf
systemctl daemon-reload && systemctl restart ollama

# Run Open WebUI via Docker
docker run -d \
  --name open-webui \
  --network=host \
  -e OLLAMA_BASE_URL=http://127.0.0.1:11434 \
  -v open-webui:/app/backend/data \
  ghcr.io/open-webui/open-webui:main
```

Open WebUI will be at `http://localhost:3000`. Create an admin account on first launch.

### 3. Create a Mattermost bot account

Go to **Main Menu → Integrations → Bot Accounts → Add Bot Account**

| Field | Value |
|---|---|
| Username | `owui-bot` |
| Display Name | `AI Assistant` |
| Role | `Member` |

Save and copy the token — **shown only once**.

Add the bot to your team:

```
System Console → User Management → Users → find owui-bot → Add to Team
```

Add it to channels:

```
Channel → Members → Add → search owui-bot
```

### 4. Configure

```bash
cp .env.example .env
nano .env
```

```env
# Mattermost
MM_URL=http://localhost:8065
MM_WS_URL=ws://localhost:8065/api/v4/websocket
MM_BOT_TOKEN=your-bot-token-here
MM_BOT_USERNAME=owui-bot

# Open WebUI
OWUI_URL=http://localhost:3000
OWUI_MODEL=llama3.2:1b
OWUI_EMAIL=your-owui-admin@email.com
OWUI_PASSWORD=your-owui-password
```

### 5. Run

```bash
python3 bot.py
```

```
🤖 mattermost-owui-bot starting...
   Mattermost : http://localhost:8065
   OWUI       : http://localhost:3000
   Model      : llama3.2:1b
   Bot        : @owui-bot
🚀 Connecting to WebSocket...
✅ Connected! Listening for events...
   · DMs              → reply with conversation memory (/reset to clear)
   · @mention in thread → follow thread, reply without trigger words
```

---

## Usage

### Direct Message

Find `@owui-bot` in Mattermost and send any message. The bot remembers the full conversation.

```
You:       what is machine learning?
owui-bot:  Machine learning is a subset of AI that enables systems to learn...

You:       give me a simple real world example
owui-bot:  A classic example is email spam detection. The model learns...
```

Type `/reset` to clear the history and start fresh.

### Channel Thread

Mention the bot once to start a thread conversation:

```
You:       @owui-bot explain Docker in simple terms
owui-bot:  Docker is a platform that packages applications into containers...

You:       how is it different from a VM?        ← no mention needed
owui-bot:  Unlike VMs, Docker containers share the host OS kernel...

You:       can I run it on Windows?              ← still no mention needed
owui-bot:  Yes, Docker Desktop is available for Windows and Mac...
```

---

## Running in Production

Use systemd to keep the bot running as a background service:

```bash
sudo nano /etc/systemd/system/owui-bot.service
```

```ini
[Unit]
Description=Mattermost OWUI Bot
After=network.target

[Service]
WorkingDirectory=/opt/mattermost-owui-bot
ExecStart=/usr/bin/python3 bot.py
EnvironmentFile=/opt/mattermost-owui-bot/.env
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable owui-bot
sudo systemctl start owui-bot

# View live logs
journalctl -u owui-bot -f
```

---

## Project Structure

```
mattermost-owui-bot/
├── bot.py            main bot — WebSocket listener + OWUI caller
├── requirements.txt  websockets==16.0
├── .env.example      config template
├── .env              your config (gitignored)
├── .gitignore
└── README.md
```

---

## Important Notes

- **Thread state** is in memory — restarting clears active thread tracking
- **DM history** is in memory — use `/reset` or restart to clear
- **Token refresh** — OWUI JWT is refreshed on every request to avoid expiry
- **Multiple models** — run multiple bot instances with different `.env` files

---

## Built With

- [Open WebUI](https://github.com/open-webui/open-webui) — self-hosted AI platform
- [Ollama](https://ollama.com) — local LLM runtime
- [Mattermost](https://mattermost.com) — open source team messaging
- [websockets](https://websockets.readthedocs.io) — Python WebSocket client

---

## License

MIT — free to use, modify, and distribute.

---

Built by [Ashutosh Maske](https://github.com/YOUR_USERNAME) · March 2026
