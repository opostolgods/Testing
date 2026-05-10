#!/bin/bash
# CloudVPN deployment script for cloudvpn.best
# Requires: SSH_PASSWORD, TELEGRAM_BOT_TOKEN env vars
set -e

SERVER="${DEPLOY_SERVER:-87.120.187.116}"
DEPLOY_DIR="/opt/cloudvpn-site"

if [ -z "$SSH_PASSWORD" ]; then
  echo "ERROR: SSH_PASSWORD env var is required"
  exit 1
fi

echo "=== Deploying CloudVPN to $SERVER ==="

# Sync project files
rsync -avz --exclude='venv' --exclude='__pycache__' --exclude='.git' \
  -e "sshpass -p '$SSH_PASSWORD' ssh -o StrictHostKeyChecking=no" \
  ./ root@$SERVER:$DEPLOY_DIR/

# Generate SECRET_KEY locally
SECRET_KEY_VAL=$(python3 -c "import secrets; print(secrets.token_hex(32))")

# Setup on server
sshpass -p "$SSH_PASSWORD" ssh -o StrictHostKeyChecking=no root@$SERVER << REMOTE_SCRIPT
set -e

DEPLOY_DIR="/opt/cloudvpn-site"
cd \$DEPLOY_DIR

# Create data directory
mkdir -p /opt/cloudvpn-site/data

# Create .env file (only if not exists to preserve existing config)
if [ ! -f \$DEPLOY_DIR/backend/.env ]; then
cat > \$DEPLOY_DIR/backend/.env << ENVEOF
TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN:-CHANGE_ME}
TELEGRAM_ADMIN_ID=${TELEGRAM_ADMIN_ID:-CHANGE_ME}
DOMAIN=cloudvpn.best
DB_PATH=/opt/cloudvpn-site/data/users.db
SECRET_KEY=${SECRET_KEY_VAL}
XUI_FREE_URL=${XUI_FREE_URL:-CHANGE_ME}
XUI_FREE_USER=${XUI_FREE_USER:-CHANGE_ME}
XUI_FREE_PASS=${XUI_FREE_PASS:-CHANGE_ME}
XUI_PREMIUM_URL=${XUI_PREMIUM_URL:-CHANGE_ME}
XUI_PREMIUM_USER=${XUI_PREMIUM_USER:-CHANGE_ME}
XUI_PREMIUM_PASS=${XUI_PREMIUM_PASS:-CHANGE_ME}
ENVEOF
echo ".env created — please edit with actual credentials"
fi

# Install Python 3.10+ and create venv
apt-get update -qq
apt-get install -y -qq python3-pip python3-venv nginx certbot python3-certbot-nginx > /dev/null 2>&1

cd \$DEPLOY_DIR/backend
python3 -m venv venv
source venv/bin/activate
pip install -q -r requirements.txt

# Create systemd service
cat > /etc/systemd/system/cloudvpn-web.service << 'SVCEOF'
[Unit]
Description=CloudVPN Web Application
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/cloudvpn-site/backend
EnvironmentFile=/opt/cloudvpn-site/backend/.env
ExecStart=/opt/cloudvpn-site/backend/venv/bin/uvicorn app:app --host 127.0.0.1 --port 8000 --workers 1
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SVCEOF

# Configure nginx
cat > /etc/nginx/sites-available/cloudvpn << 'NGINXEOF'
server {
    listen 80;
    server_name cloudvpn.best www.cloudvpn.best;

    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    root /opt/cloudvpn-site/frontend;
    index index.html;

    location /assets/ {
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_http_version 1.1;
    }

    location /sub/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_http_version 1.1;
    }

    location / {
        try_files \$uri \$uri/ /index.html;
    }
}

server {
    listen 127.0.0.1:8443 ssl http2;
    server_name cloudvpn.best;

    ssl_certificate /etc/letsencrypt/live/cloudvpn.best/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/cloudvpn.best/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers off;

    add_header Strict-Transport-Security "max-age=31536000" always;
    add_header X-Content-Type-Options nosniff always;
    add_header X-Frame-Options SAMEORIGIN always;

    root /opt/cloudvpn-site/frontend;
    index index.html;

    location /assets/ {
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_http_version 1.1;
    }

    location /sub/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_http_version 1.1;
    }

    location / {
        try_files \$uri \$uri/ /index.html;
    }

    error_page 404 /index.html;
}
NGINXEOF

mkdir -p /var/www/certbot
ln -sf /etc/nginx/sites-available/cloudvpn /etc/nginx/sites-enabled/cloudvpn
rm -f /etc/nginx/sites-enabled/default 2>/dev/null

# Get SSL certificate if not exists
if [ ! -f /etc/letsencrypt/live/cloudvpn.best/fullchain.pem ]; then
    certbot certonly --webroot -w /var/www/certbot -d cloudvpn.best --non-interactive --agree-tos -m admin@cloudvpn.best || true
fi

# Start services
systemctl daemon-reload
systemctl enable cloudvpn-web
systemctl restart cloudvpn-web
nginx -t && systemctl restart nginx

echo "=== CloudVPN deployed successfully ==="
REMOTE_SCRIPT

echo "=== Deployment complete ==="
