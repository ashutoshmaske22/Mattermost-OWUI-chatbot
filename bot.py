"""
mattermost-owui-bot
-------------------
A lightweight Python bot that connects Mattermost to Open WebUI (OWUI) models.

Features:
  - DMs with full conversation memory  (/reset to clear)
  - @mention bot once in a channel thread → bot follows thread automatically
  - Full thread context passed to the model on every reply
  - Zero dependencies except websockets

Author: Ashutosh Maske
GitHub: https://github.com/YOUR_USERNAME/mattermost-owui-bot
"""

import json
import asyncio
import os
import urllib.request
import websockets

# ── CONFIG (loaded from .env file) ────────────────────────────────────────────
MM_URL          = "http://localhost:8065"
MM_WS_URL       = "ws://localhost:8065/api/v4/websocket"
MM_BOT_TOKEN    = ""
MM_BOT_USERNAME = "owui-bot"
OWUI_URL        = "http://localhost:3000"
OWUI_MODEL      = "llama3.2:1b"
OWUI_EMAIL      = ""
OWUI_PASSWORD   = ""
# ─────────────────────────────────────────────────────────────────────────────

# In-memory state
active_threads = set()   # thread root IDs where bot was @mentioned
dm_history     = {}      # user_id → conversation history list


def load_env():
    """Load .env file if it exists — no external library needed."""
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    os.environ.setdefault(key.strip(), val.strip())


def mm_request(method, path, data=None):
    """Make an authenticated REST API call to Mattermost."""
    url  = f"{MM_URL}/api/v4{path}"
    body = json.dumps(data).encode() if data else None
    req  = urllib.request.Request(url, data=body, headers={
        "Authorization": f"Bearer {MM_BOT_TOKEN}",
        "Content-Type":  "application/json"
    }, method=method)
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


def get_bot_user_id():
    """Get the bot's own Mattermost user ID."""
    return mm_request("GET", "/users/me")["id"]


def get_owui_token():
    """Fetch a fresh JWT token from OWUI."""
    url  = f"{OWUI_URL}/api/v1/auths/signin"
    data = json.dumps({"email": OWUI_EMAIL, "password": OWUI_PASSWORD}).encode()
    req  = urllib.request.Request(url, data=data,
                                  headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())["token"]


def call_owui(messages: list) -> str:
    """Send conversation history to OWUI and return the AI reply."""
    token = get_owui_token()
    url   = f"{OWUI_URL}/api/chat/completions"
    data  = json.dumps({
        "model":    OWUI_MODEL,
        "messages": messages,
        "stream":   False
    }).encode()
    req = urllib.request.Request(url, data=data, headers={
        "Authorization": f"Bearer {token}",
        "Content-Type":  "application/json"
    })
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read())["choices"][0]["message"]["content"]


def post_reply(channel_id: str, message: str, root_id: str = None):
    """Post a message to Mattermost, optionally as a thread reply."""
    payload = {"channel_id": channel_id, "message": message}
    if root_id:
        payload["root_id"] = root_id
    mm_request("POST", "/posts", payload)


def get_thread_history(root_id: str, bot_id: str) -> list:
    """
    Fetch all posts in a Mattermost thread and build a conversation history
    list in the format OWUI expects: [{"role": "user/assistant", "content": "..."}]
    """
    try:
        data  = mm_request("GET", f"/posts/{root_id}/thread")
        posts = data.get("posts", {})
        order = data.get("order", [])

        messages = []
        for post_id in order:
            post = posts.get(post_id, {})
            text = post.get("message", "").strip()
            uid  = post.get("user_id", "")

            if not text:
                continue

            text = text.replace(f"@{MM_BOT_USERNAME}", "").strip()
            if text.startswith("🤖 "):
                text = text[3:]
            if not text:
                continue

            role = "assistant" if uid == bot_id else "user"
            messages.append({"role": role, "content": text})

        return messages
    except Exception as e:
        print(f"[Warning] Could not fetch thread history: {e}")
        return []


async def handle_event(event: dict, bot_id: str):
    """Process a Mattermost WebSocket event."""
    if event.get("event") != "posted":
        return

    post         = json.loads(event["data"].get("post", "{}"))
    msg          = post.get("message", "").strip()
    channel_id   = post.get("channel_id", "")
    post_id      = post.get("id", "")
    root_id      = post.get("root_id", "") or post_id
    user_id      = post.get("user_id", "")
    channel_type = event["data"].get("channel_type", "")

    # Never respond to own messages
    if user_id == bot_id:
        return

    print(f"[{channel_type}] {user_id[:8]}... → {msg[:80]}")

    # ── Direct Message Handler ─────────────────────────────────────────────────
    if channel_type == "D":
        if msg.lower() == "/reset":
            dm_history.pop(user_id, None)
            post_reply(channel_id, "🔄 Conversation reset! Start fresh.")
            return

        history = dm_history.get(user_id, [])
        history.append({"role": "user", "content": msg})

        try:
            reply = call_owui(history)
            history.append({"role": "assistant", "content": reply})
            dm_history[user_id] = history[-20:]  # keep last 20 messages
            post_reply(channel_id, f"🤖 {reply}")
        except Exception as e:
            print(f"[Error] OWUI call failed: {e}")
            post_reply(channel_id, f"❌ Error: {e}")
        return

    # ── Channel / Thread Handler ───────────────────────────────────────────────
    bot_mentioned = f"@{MM_BOT_USERNAME}" in msg

    if bot_mentioned:
        active_threads.add(root_id)

    if bot_mentioned or root_id in active_threads:
        history = get_thread_history(root_id, bot_id)
        if not history:
            clean = msg.replace(f"@{MM_BOT_USERNAME}", "").strip()
            history = [{"role": "user", "content": clean}]

        try:
            reply = call_owui(history)
            post_reply(channel_id, f"🤖 {reply}", root_id=root_id)
        except Exception as e:
            print(f"[Error] OWUI call failed: {e}")
            post_reply(channel_id, f"❌ Error: {e}", root_id=root_id)


async def run():
    """Connect to Mattermost WebSocket and listen for events forever."""
    global MM_URL, MM_WS_URL, MM_BOT_TOKEN, MM_BOT_USERNAME
    global OWUI_URL, OWUI_MODEL, OWUI_EMAIL, OWUI_PASSWORD

    load_env()

    MM_URL          = os.environ.get("MM_URL",          MM_URL)
    MM_WS_URL       = os.environ.get("MM_WS_URL",       MM_WS_URL)
    MM_BOT_TOKEN    = os.environ.get("MM_BOT_TOKEN",    MM_BOT_TOKEN)
    MM_BOT_USERNAME = os.environ.get("MM_BOT_USERNAME", MM_BOT_USERNAME)
    OWUI_URL        = os.environ.get("OWUI_URL",        OWUI_URL)
    OWUI_MODEL      = os.environ.get("OWUI_MODEL",      OWUI_MODEL)
    OWUI_EMAIL      = os.environ.get("OWUI_EMAIL",      OWUI_EMAIL)
    OWUI_PASSWORD   = os.environ.get("OWUI_PASSWORD",   OWUI_PASSWORD)

    bot_id = get_bot_user_id()
    print(f"🤖 mattermost-owui-bot starting...")
    print(f"   Mattermost : {MM_URL}")
    print(f"   OWUI       : {OWUI_URL}")
    print(f"   Model      : {OWUI_MODEL}")
    print(f"   Bot        : @{MM_BOT_USERNAME}")
    print(f"🚀 Connecting to WebSocket...")

    async with websockets.connect(MM_WS_URL) as ws:
        await ws.send(json.dumps({
            "seq":    1,
            "action": "authentication_challenge",
            "data":   {"token": MM_BOT_TOKEN}
        }))

        print("✅ Connected! Listening for events...")
        print("   · DMs              → reply with conversation memory (/reset to clear)")
        print("   · @mention in thread → follow thread, reply without trigger words")

        async for raw in ws:
            try:
                event = json.loads(raw)
                await handle_event(event, bot_id)
            except Exception as e:
                print(f"[Error] {e}")


if __name__ == "__main__":
    asyncio.run(run())
