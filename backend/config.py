import os
from dotenv import load_dotenv

load_dotenv()

# Telegram Bot
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
BOT_USERNAME = os.getenv("TELEGRAM_BOT_USERNAME", "CloudVPN_bestbot")

# Admin
ADMIN_IDS = [int(x) for x in os.getenv("TELEGRAM_ADMIN_ID", "7307243710").split(",") if x.strip()]

# Free server 3X-UI
FREE_SERVER_IP = os.getenv("FREE_SERVER_IP", "144.31.151.253")
FREE_XUI_URL = os.getenv("FREE_XUI_URL", "")
FREE_XUI_USER = os.getenv("FREE_XUI_USER", "")
FREE_XUI_PASS = os.getenv("FREE_XUI_PASS", "")
FREE_INBOUND_ID = int(os.getenv("FREE_INBOUND_ID", "3"))

# Premium server 3X-UI
PREMIUM_SERVER_IP = os.getenv("PREMIUM_SERVER_IP", "87.120.187.116")
PREMIUM_XUI_URL = os.getenv("PREMIUM_XUI_URL", "")
PREMIUM_XUI_USER = os.getenv("PREMIUM_XUI_USER", "")
PREMIUM_XUI_PASS = os.getenv("PREMIUM_XUI_PASS", "")
PREMIUM_INBOUND_ID = int(os.getenv("PREMIUM_INBOUND_ID", "2"))

# Subscription
FREE_TRIAL_DAYS = 7
SUBSCRIPTION_DAYS = 365

# Support
SUPPORT_USERNAME = "@colnyso"

# Domain
DOMAIN = os.getenv("DOMAIN", "cloudvpn.best")

# Secret key for session
SECRET_KEY = os.getenv("SECRET_KEY", "cloudvpn-secret-key-change-me")

# Database
DB_PATH = os.getenv("DB_PATH", "/opt/cloudvpn-site/data/users.db")
