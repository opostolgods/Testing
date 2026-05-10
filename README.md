# CloudVPN — Web Application

VPN web application with Raycast-inspired dark design, Telegram authentication, and 3X-UI integration.

## Features

- **Landing page** — Raycast-style dark design with VPN features, pricing
- **Telegram Login** — Authentication via Telegram Login Widget
- **User Dashboard** — VPN key management, auto-import into V2RayNG/Happ/Streisand
- **Tutorials** — Step-by-step guides for all platforms
- **Support** — FAQ, bug reports, Telegram support (@colnyso)
- **Admin Panel** — User management, statistics, key management

## Architecture

- **Frontend**: Static HTML/CSS/JS with Raycast design tokens
- **Backend**: FastAPI (Python) with SQLite
- **VPN**: VLESS + Reality via 3X-UI panels on 2 servers
  - Free server: 144.31.151.253
  - Premium server: 87.120.187.116

## Deployment

```bash
chmod +x deploy.sh
./deploy.sh
```

The script will:
1. Sync files to the server
2. Set up Python venv and install dependencies
3. Configure nginx with SSL
4. Create systemd service for the backend
5. Start everything

## Environment Variables

| Variable | Description |
|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | Telegram bot token |
| `TELEGRAM_ADMIN_ID` | Admin Telegram user ID |
| `DOMAIN` | Domain name (cloudvpn.best) |
| `SECRET_KEY` | Session encryption key |
| `DB_PATH` | SQLite database path |

## Tech Stack

- FastAPI + Uvicorn
- SQLite (users, keys, subscriptions)
- 3X-UI API integration
- Telegram Login Widget
- Pure HTML/CSS/JS (no framework)
