# Telegram Channel Bot

A mini social media bot — users send messages, bot posts them to your channel.

---

## Setup

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Create your bot
- Open Telegram, talk to **@BotFather**
- Send `/newbot`, follow the steps
- Copy the token it gives you

### 3. Configure
Open `config.py` and fill in:
```python
BOT_TOKEN = "your token here"
CHANNEL_ID = "@yourchannel"   # or -100xxxxxxxxxx for private channels
```

### 4. Add bot as admin to your channel
- Go to your channel → Admins → Add Admin
- Search for your bot
- Give it **Post Messages** permission (minimum required)

### 5. Run
```bash
python bot.py
```

---

## How to get your Channel ID (private channels)
1. Forward any message from the channel to **@userinfobot**
2. It will show the channel ID (starts with -100...)

---

## Admin Commands (only works for your account)
| Command | What it does |
|---|---|
| `/admin` or `/stats` | Show dashboard: users, posts, bans |
| `/ban <user_id>` | Ban a user from posting |
| `/unban <user_id>` | Unban a user |
| `/users` | List all registered users |

---

## How it works
1. User sends `/start` → saved to `bot.db` (SQLite)
2. User sends a message → bot asks: **Post as Name** or **Post Anonymously**
3. Named post → channel gets: `message — [FirstName](profile link) posted`
4. Anon post → channel gets: `message — Anonymous posted`

- If user has @username → link goes to `t.me/username`
- If no @username → link uses `tg://user?id=...` (tappable in Telegram)

---

## Running 24/7 (free options)
- **Railway.app** — connect your GitHub repo, deploy for free
- **Render.com** — same, free tier available
- **VPS** (Hetzner/DigitalOcean ~$4/mo) — run with `screen` or `systemd`
