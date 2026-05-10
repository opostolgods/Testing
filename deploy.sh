#!/bin/bash
# CloudVPN deployment script for cloudvpn.best (87.120.187.116)
set -e

SERVER="87.120.187.116"
DEPLOY_DIR="/opt/cloudvpn-site"

echo "=== Deploying CloudVPN to $SERVER ==="

# Sync project files
rsync -avz --exclude='venv' --exclude='__pycache__' --exclude='.git' \
  -e "sshpass -p 'AzanovDED_21212827m' ssh -o StrictHostKeyChecking=no" \
  ./ root@$SERVER:$DEPLOY_DIR/

# Setup on server
sshpass -p 'AzanovDED_21212827m' ssh -o StrictHostKeyChecking=no root@$SERVER << 'REMOTE_SCRIPT'
set -e

DEPLOY_DIR="/opt/cloudvpn-site"
cd $DEPLOY_DIR

# Create data directory
mkdir -p /opt/cloudvpn-site/data

# Create .env file
cat > $DEPLOY_DIR/backend/.env << 'ENVEOF'
TELEGRAM_BOT_TOKEN=8799265922:AAGcRbD-H9Yx90UNzIlkVzk3G4KOkH_alNk
TELEGRAM_ADMIN_ID=7307243710
DOMAIN=cloudvpn.best
DB_PATH=/opt/cloudvpn-site/data/users.db
SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
ENVEOF

# Install Python 3.10+ and create venv
apt-get update -qq
apt-get install -y -qq python3-pip python3-venv nginx certbot python3-certbot-nginx > /dev/null 2>&1

cd $DEPLOY_DIR/backend
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
Environment=PATH=/opt/cloudvpn-site/backend/venv/bin:/usr/bin:/bin
ExecStart=/opt/cloudvpn-site/backend/venv/bin/uvicorn app:app --host 127.0.0.1 --port 8000 --workers 2
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

    location / {
        return 301 https://$host$request_uri;
    }
}

server {
    listen 443 ssl http2;
    server_name cloudvpn.best www.cloudvpn.best;

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

    # Static files
    location /assets/ {
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    # API proxy
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # SPA fallback
    location / {
        try_files $uri $uri/ /index.html;
    }
}
NGINXEOF

mkdir -p /var/www/certbot
ln -sf /etc/nginx/sites-available/cloudvpn /etc/nginx/sites-enabled/cloudvpn
rm -f /etc/nginx/sites-enabled/default 2>/dev/null

# Get SSL certificate if not exists
if [ ! -f /etc/letsencrypt/live/cloudvpn.best/fullchain.pem ]; then
    # Start nginx with HTTP only first for cert challenge
    cat > /tmp/nginx-http.conf << 'HTTPEOF'
server {
    listen 80;
    server_name cloudvpn.best www.cloudvpn.best;
    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }
    location / {
        return 200 'CloudVPN Setup';
    }
}
HTTPEOF
    cp /etc/nginx/sites-available/cloudvpn /tmp/cloudvpn-ssl-backup
    cp /tmp/nginx-http.conf /etc/nginx/sites-available/cloudvpn
    nginx -t && systemctl restart nginx
    certbot certonly --webroot -w /var/www/certbot -d cloudvpn.best -d www.cloudvpn.best --non-interactive --agree-tos -m admin@cloudvpn.best || true
    cp /tmp/cloudvpn-ssl-backup /etc/nginx/sites-available/cloudvpn
fi

# Start services
systemctl daemon-reload
systemctl enable cloudvpn-web
systemctl restart cloudvpn-web
nginx -t && systemctl restart nginx

echo "=== CloudVPN deployed successfully ==="
echo "=== Site should be available at https://cloudvpn.best ==="
REMOTE_SCRIPT

echo "=== Deployment complete ==="
