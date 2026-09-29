# 📺 JioHotstar + MX Player Leech Bot V2

A Telegram bot that downloads videos from **JioHotstar** and **MX Player** with interactive quality, audio, and subtitle selection — and uploads them directly to you.

---

## ✨ Features

| Feature | Details |
|---|---|
| 🟢 JioHotstar | Full support with cookie-based authentication |
| 🔵 MX Player | Free and authenticated content |
| 📺 Quality selection | Pick 1080p / 720p / 480p / 360p via buttons |
| 🔊 Audio selection | Choose Hindi / Tamil / English / etc. |
| 🔤 Subtitle selection | Embed your preferred subtitle language |
| 📤 Live progress | Real-time download & upload progress bar |
| 🚫 Cancel | Cancel any in-progress download |
| 🔁 Mirror | Optionally mirror files to a dump channel |
| 🔐 Access control | Whitelist specific user IDs |

---

## 🤖 How It Works

1. Send a JioHotstar or MX Player link
2. Bot shows video info + quality buttons `[1080p] [720p] [480p]`
3. Tap your quality → audio language buttons appear `[Hindi] [English]`
4. Tap audio → subtitle buttons appear `[English] [Hindi] [None]`
5. Bot downloads with your selections and uploads to Telegram

---

## ⚙️ Setup

### Prerequisites
- **Python 3.10+**
- **FFmpeg** in PATH → [Download](https://ffmpeg.org/download.html)
- **Telegram Bot Token** → [@BotFather](https://t.me/BotFather)
- **Telegram API ID & Hash** → [my.telegram.org](https://my.telegram.org)

### Install
```bash
pip install -r requirements.txt
```

### Configure
```bash
copy .env.example .env
# Edit .env with your BOT_TOKEN, API_ID, API_HASH
```

### Hotstar Cookies (for premium content)
1. Install "Get cookies.txt LOCALLY" browser extension
2. Log in to hotstar.com in your browser
3. Export cookies and save the file in the project folder
4. Set the path in .env: `JIOHOTSTAR_COOKIES=./your_cookies.txt`

### Run
```bash
python bot.py
```

---

## 📁 Project Structure

```
hotstar-leech-bot/
├── bot.py              ← Main entry + all commands + inline keyboard flow
├── config.py           ← Env var loading & validation
├── downloader.py       ← yt-dlp wrapper with format parsing & selection
├── uploader.py         ← Pyrogram file uploader with progress
├── utils.py            ← URL validation, formatting helpers
├── platforms/
│   ├── __init__.py     ← Platform registry & detection
│   ├── base.py         ← Abstract Platform interface
│   ├── hotstar.py      ← JioHotstar handler
│   └── mxplayer.py     ← MX Player handler
├── .env.example        ← Config template
├── requirements.txt
└── README.md
```

---

## 📋 Bot Commands

| Command | Description |
|---|---|
| `/start` | Welcome message |
| `/leech <url>` | Download a video with interactive selection |
| `/cancel` | Cancel active download |
| `/help` | Show help |

You can also **paste a URL directly** without any command.

---

## ⚠️ Limitations

| Limitation | Notes |
|---|---|
| 2 GB upload cap | Telegram bot limit (configurable via `MAX_FILESIZE_MB`) |
| DRM content | Widevine-protected streams cannot be decrypted by yt-dlp |
| Geo-restriction | Both platforms are India-only; use an Indian IP or VPN |

---

## 📜 License

MIT — free to use, modify, and self-host.
