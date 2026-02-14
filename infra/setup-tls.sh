#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# Add Let's Encrypt TLS to a running meeple deployment
#
# Usage: sudo ./infra/setup-tls.sh meeple.example.com
# ─────────────────────────────────────────────────────────────
set -euo pipefail
cd "$(dirname "$0")/.."

DOMAIN="${1:?Usage: setup-tls.sh <domain>}"
EMAIL="${2:-admin@$DOMAIN}"
NGINX_CONF="infra/nginx.conf"

echo "Setting up TLS for $DOMAIN..."

# 1. Run certbot to get the certificate
docker compose -f docker-compose.prod.yml run --rm \
    -v "$(pwd)/certbot-webroot:/var/www/certbot" \
    -v "$(pwd)/certbot-certs:/etc/letsencrypt" \
    --entrypoint "" \
    certbot \
    certbot certonly \
        --webroot -w /var/www/certbot \
        -d "$DOMAIN" \
        --email "$EMAIL" \
        --agree-tos \
        --no-eff-email

# 2. Replace nginx config with TLS-enabled version
cat > "$NGINX_CONF" <<NGINXEOF
worker_processes auto;

events {
    worker_connections 1024;
}

http {
    include       /etc/nginx/mime.types;
    default_type  application/octet-stream;

    sendfile    on;
    tcp_nopush  on;
    keepalive_timeout 65;
    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml;

    map \$http_upgrade \$connection_upgrade {
        default upgrade;
        ''      close;
    }

    # HTTP → HTTPS redirect
    server {
        listen 80;
        server_name $DOMAIN;

        location /.well-known/acme-challenge/ {
            root /var/www/certbot;
        }

        location / {
            return 301 https://\$host\$request_uri;
        }
    }

    # HTTPS
    server {
        listen 443 ssl http2;
        server_name $DOMAIN;

        ssl_certificate     /etc/letsencrypt/live/$DOMAIN/fullchain.pem;
        ssl_certificate_key /etc/letsencrypt/live/$DOMAIN/privkey.pem;
        ssl_protocols TLSv1.2 TLSv1.3;
        ssl_ciphers HIGH:!aNULL:!MD5;

        add_header Strict-Transport-Security "max-age=31536000" always;

        location /api/ {
            proxy_pass http://backend:8000;
            proxy_set_header Host \$host;
            proxy_set_header X-Real-IP \$remote_addr;
            proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto \$scheme;
        }

        location /ws/ {
            proxy_pass http://backend:8000;
            proxy_http_version 1.1;
            proxy_set_header Upgrade \$http_upgrade;
            proxy_set_header Connection \$connection_upgrade;
            proxy_set_header Host \$host;
            proxy_set_header X-Real-IP \$remote_addr;
            proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
            proxy_read_timeout 86400;
            proxy_send_timeout 86400;
        }

        location /health {
            proxy_pass http://backend:8000;
        }

        location / {
            proxy_pass http://frontend:3000;
            proxy_set_header Host \$host;
            proxy_set_header X-Real-IP \$remote_addr;
            proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto \$scheme;
        }
    }
}
NGINXEOF

# 3. Add certbot renewal service
if ! grep -q "certbot" docker-compose.prod.yml; then
    echo ""
    echo "NOTE: Add a certbot service to docker-compose.prod.yml for auto-renewal:"
    echo ""
    echo "  certbot:"
    echo "    image: certbot/certbot"
    echo "    volumes:"
    echo "      - certbot-webroot:/var/www/certbot"
    echo "      - certbot-certs:/etc/letsencrypt"
    echo '    entrypoint: "/bin/sh -c '"'"'trap exit TERM; while :; do certbot renew; sleep 12h & wait $${!}; done;'"'"'"'
    echo "    restart: unless-stopped"
fi

# 4. Restart nginx to pick up new config
docker compose -f docker-compose.prod.yml restart nginx

echo ""
echo "TLS enabled! Site is live at https://$DOMAIN"
