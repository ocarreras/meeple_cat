# 04 — Infrastructure & Deployment

> **Note**: This document describes the original Docker Compose design.
> The actual production setup uses **k3s on Hetzner** with **Terraform**
> (IaC) and a **Helm chart**, deployed via **GitHub Actions CI/CD**.
> See `CLAUDE.md` for current infrastructure documentation, and
> `infra/terraform/` + `infra/k8s/meeple/` for the actual configuration.

Single VPS, Docker Compose, under $25/month. Designed for a hobby project
that doesn't sacrifice maintainability.

---

## 1. VPS Selection

**Hetzner CX32** (or equivalent):
- 4 vCPU (shared)
- 8 GB RAM
- 80 GB SSD
- 20 TB traffic
- ~$7-15/month (region-dependent)

This comfortably runs all services. Scaling plan in section 8.

---

## 2. Docker Compose Configuration

```yaml
# docker-compose.yml
version: "3.8"

services:
  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./infra/nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - ./infra/nginx/conf.d:/etc/nginx/conf.d:ro
      - certbot-webroot:/var/www/certbot:ro
      - certbot-certs:/etc/letsencrypt:ro
    depends_on:
      - frontend
      - backend
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "nginx", "-t"]
      interval: 30s
      timeout: 5s

  frontend:
    build:
      context: ./frontend
      dockerfile: ../infra/Dockerfile.frontend
    environment:
      - NEXT_PUBLIC_API_URL=https://meeple.cat/api
      - NEXT_PUBLIC_WS_URL=wss://meeple.cat
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:3000/"]
      interval: 30s
      timeout: 5s
    deploy:
      resources:
        limits:
          memory: 512M
          cpus: "0.5"

  backend:
    build:
      context: .
      dockerfile: infra/Dockerfile.backend
    environment:
      - DATABASE_URL=postgresql+asyncpg://meeple:${DB_PASSWORD}@postgres:5432/meeple
      - REDIS_URL=redis://redis:6379/0
      - JWT_SECRET_KEY=${JWT_SECRET_KEY}
      - GOOGLE_CLIENT_ID=${GOOGLE_CLIENT_ID}
      - GOOGLE_CLIENT_SECRET=${GOOGLE_CLIENT_SECRET}
      - GITHUB_CLIENT_ID=${GITHUB_CLIENT_ID}
      - GITHUB_CLIENT_SECRET=${GITHUB_CLIENT_SECRET}
      - DISCORD_CLIENT_ID=${DISCORD_CLIENT_ID}
      - DISCORD_CLIENT_SECRET=${DISCORD_CLIENT_SECRET}
      - BASE_URL=https://meeple.cat
      - FRONTEND_URL=https://meeple.cat
      - SENTRY_DSN=${SENTRY_DSN}
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 5s
    deploy:
      resources:
        limits:
          memory: 1G
          cpus: "1.5"

  postgres:
    image: postgres:16-alpine
    environment:
      - POSTGRES_USER=meeple
      - POSTGRES_PASSWORD=${DB_PASSWORD}
      - POSTGRES_DB=meeple
    volumes:
      - postgres-data:/var/lib/postgresql/data
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U meeple"]
      interval: 10s
      timeout: 5s
    deploy:
      resources:
        limits:
          memory: 2G
          cpus: "1.0"

  redis:
    image: redis:7-alpine
    command: redis-server --maxmemory 256mb --maxmemory-policy allkeys-lru
    volumes:
      - redis-data:/data
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
    deploy:
      resources:
        limits:
          memory: 512M
          cpus: "0.5"

  certbot:
    image: certbot/certbot
    volumes:
      - certbot-webroot:/var/www/certbot
      - certbot-certs:/etc/letsencrypt
    entrypoint: "/bin/sh -c 'trap exit TERM; while :; do certbot renew; sleep 12h & wait $${!}; done;'"
    restart: unless-stopped

volumes:
  postgres-data:
  redis-data:
  certbot-webroot:
  certbot-certs:
```

---

## 3. Dockerfiles

### 3.1 Backend

```dockerfile
# infra/Dockerfile.backend
FROM python:3.12-slim AS base

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY backend/pyproject.toml backend/uv.lock ./
RUN pip install uv && uv pip install --system -r pyproject.toml

# Copy source
COPY backend/src ./src

# Run
EXPOSE 8000
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
# Single worker because WebSocket sessions are in-process.
# If we need more workers, we'd need Redis pub/sub for WS broadcasting.
```

### 3.2 Frontend

```dockerfile
# infra/Dockerfile.frontend
FROM node:20-alpine AS builder

WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app

COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public

EXPOSE 3000
CMD ["node", "server.js"]
```

---

## 4. Nginx Configuration

```nginx
# infra/nginx/nginx.conf
worker_processes auto;
events {
    worker_connections 1024;
}

http {
    include /etc/nginx/mime.types;
    default_type application/octet-stream;

    # Logging
    log_format main '$remote_addr - $remote_user [$time_local] "$request" '
                    '$status $body_bytes_sent "$http_referer" '
                    '"$http_user_agent" $request_time';
    access_log /var/log/nginx/access.log main;
    error_log /var/log/nginx/error.log warn;

    # Performance
    sendfile on;
    tcp_nopush on;
    keepalive_timeout 65;
    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml;

    # Rate limiting zones
    limit_req_zone $binary_remote_addr zone=api:10m rate=60r/m;
    limit_req_zone $binary_remote_addr zone=auth:10m rate=10r/m;
    limit_req_zone $binary_remote_addr zone=ws:10m rate=5r/s;

    # WebSocket upgrade map
    map $http_upgrade $connection_upgrade {
        default upgrade;
        '' close;
    }

    # Redirect HTTP to HTTPS
    server {
        listen 80;
        server_name meeple.cat;

        location /.well-known/acme-challenge/ {
            root /var/www/certbot;
        }

        location / {
            return 301 https://$host$request_uri;
        }
    }

    # Main HTTPS server
    server {
        listen 443 ssl http2;
        server_name meeple.cat;

        ssl_certificate /etc/letsencrypt/live/meeple.cat/fullchain.pem;
        ssl_certificate_key /etc/letsencrypt/live/meeple.cat/privkey.pem;
        ssl_protocols TLSv1.2 TLSv1.3;
        ssl_ciphers HIGH:!aNULL:!MD5;

        # Security headers
        add_header X-Frame-Options DENY;
        add_header X-Content-Type-Options nosniff;
        add_header X-XSS-Protection "1; mode=block";
        add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

        # Auth endpoints
        location /auth/ {
            limit_req zone=auth burst=5 nodelay;
            proxy_pass http://backend:8000;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }

        # REST API
        location /api/ {
            limit_req zone=api burst=20 nodelay;
            proxy_pass http://backend:8000;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }

        # WebSocket
        location /ws/ {
            limit_req zone=ws burst=10 nodelay;
            proxy_pass http://backend:8000;
            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection $connection_upgrade;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_read_timeout 86400;    # Keep WebSocket alive for 24h
            proxy_send_timeout 86400;
        }

        # Health check (no rate limit)
        location /health {
            proxy_pass http://backend:8000;
        }

        # Frontend (everything else)
        location / {
            proxy_pass http://frontend:3000;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }
    }
}
```

---

## 5. CI/CD Pipeline (GitHub Actions)

```yaml
# .github/workflows/deploy.yml
name: Build & Deploy

on:
  push:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install backend deps
        run: |
          pip install uv
          cd backend && uv pip install --system -r pyproject.toml

      - name: Run backend tests
        run: cd backend && pytest

      - name: Setup Node
        uses: actions/setup-node@v4
        with:
          node-version: "20"

      - name: Install frontend deps
        run: cd frontend && npm ci

      - name: Run frontend tests
        run: cd frontend && npm test

      - name: Type check frontend
        run: cd frontend && npx tsc --noEmit

  deploy:
    needs: test
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v4

      - name: Deploy to VPS
        uses: appleboy/ssh-action@v1
        with:
          host: ${{ secrets.VPS_HOST }}
          username: ${{ secrets.VPS_USER }}
          key: ${{ secrets.VPS_SSH_KEY }}
          script: |
            cd /opt/meeple
            git pull origin main
            docker compose build --parallel
            docker compose up -d
            docker compose exec backend alembic upgrade head
            docker image prune -f
```

**Deployment strategy**: Brief downtime during container restart (acceptable
for hobby project). For zero-downtime, use blue-green with a second compose
file and nginx upstream switching — implement when needed.

---

## 6. Backup Strategy

### 6.1 PostgreSQL Backups

```bash
#!/bin/bash
# scripts/backup-db.sh — Run daily via cron

BACKUP_DIR="/opt/meeple/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
RETAIN_DAYS=14

mkdir -p $BACKUP_DIR

# Dump
docker compose exec -T postgres pg_dump -U meeple meeple | gzip > \
  "$BACKUP_DIR/meeple_${TIMESTAMP}.sql.gz"

# Prune old backups
find $BACKUP_DIR -name "*.sql.gz" -mtime +$RETAIN_DAYS -delete

echo "Backup completed: meeple_${TIMESTAMP}.sql.gz"
```

Cron entry:
```
0 4 * * * /opt/meeple/scripts/backup-db.sh >> /var/log/meeple-backup.log 2>&1
```

Backups stored on the same VPS initially. For offsite, rsync to a second
cheap VPS or object storage (Hetzner Storage Box at ~$4/month for 1TB).

### 6.2 Redis

Redis data is ephemeral (game state, sessions). If Redis is lost, active
games can be reconstructed from Postgres event logs. No separate backup needed.

---

## 7. Monitoring

### 7.1 Lightweight Stack

For a hobby project, full Prometheus + Grafana is overkill for V1. Start with:

1. **Docker healthchecks** (already configured) — restart on failure
2. **Structured logging** (structlog) — write to Docker logs, searchable via `docker logs`
3. **Sentry** (free tier) — error tracking, 5K events/month
4. **Simple uptime check** — UptimeRobot free tier (5-min interval)

### 7.2 Key Metrics (Logged, Not Dashboarded for V1)

Log these as structured JSON, query with `docker logs | jq` when needed:

- Active WebSocket connections
- Games in progress
- API response times (p50, p95)
- Error rates
- DB connection pool usage
- Redis memory usage

### 7.3 Prometheus + Grafana (When Needed)

Add when active user count justifies it:

```yaml
# Add to docker-compose.yml when ready
  prometheus:
    image: prom/prometheus:latest
    volumes:
      - ./infra/prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus-data:/prometheus
    deploy:
      resources:
        limits:
          memory: 256M

  grafana:
    image: grafana/grafana:latest
    volumes:
      - grafana-data:/var/lib/grafana
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=${GRAFANA_PASSWORD}
    deploy:
      resources:
        limits:
          memory: 256M
```

---

## 8. Security

### 8.1 Firewall

```bash
# Initial VPS setup
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp     # SSH
ufw allow 80/tcp     # HTTP (redirect to HTTPS)
ufw allow 443/tcp    # HTTPS
ufw enable
```

### 8.2 Container Isolation

- Containers use Docker's default bridge network — only nginx is exposed
- Postgres and Redis are not accessible from outside Docker
- Backend runs as non-root user inside container

### 8.3 Secret Management

Environment variables via `.env` file (not in git):

```bash
# .env (on server only, chmod 600)
DB_PASSWORD=xxx
JWT_SECRET_KEY=xxx
GOOGLE_CLIENT_ID=xxx
GOOGLE_CLIENT_SECRET=xxx
GITHUB_CLIENT_ID=xxx
GITHUB_CLIENT_SECRET=xxx
DISCORD_CLIENT_ID=xxx
DISCORD_CLIENT_SECRET=xxx
SENTRY_DSN=xxx
```

GitHub Actions secrets for CI/CD deployment credentials.

### 8.4 TLS Setup

Initial certificate:
```bash
docker compose run --rm certbot certonly \
  --webroot -w /var/www/certbot \
  -d meeple.cat \
  --email admin@meeple.cat \
  --agree-tos
```

Auto-renewal handled by the certbot service in docker-compose.

---

## 9. Scaling Plan

### 9.1 When to Scale

| Bottleneck | Threshold | Solution |
|---|---|---|
| WebSocket connections | ~5K concurrent | Add Redis pub/sub, run multiple backend workers |
| CPU (game logic) | Sustained >80% | Upgrade VPS or split game server |
| Database | Slow queries, >80% connections | Add read replicas or optimize queries |
| Memory | >80% usage | Upgrade VPS RAM |

### 9.2 Migration Path

**Step 1**: Vertical scaling — upgrade VPS (Hetzner CX42: 8 vCPU, 16 GB, ~$25/mo).

**Step 2**: Add Redis pub/sub so multiple uvicorn workers can share WebSocket
state. This is the first real architectural change needed.

**Step 3**: Separate game server from REST API into two services. REST scales
horizontally easily; game server is stateful (needs sticky sessions or
Redis-based session sharing).

**Step 4**: Managed database (Hetzner managed Postgres, ~$15/mo) if DB
becomes the bottleneck.

These steps are unlikely to be needed below ~10K registered users / ~1K
concurrent users.

---

## 10. File Structure

```
infra/
├── docker-compose.yml
├── docker-compose.dev.yml      # Dev overrides (hot reload, debug ports)
├── Dockerfile.backend
├── Dockerfile.frontend
├── nginx/
│   └── nginx.conf
├── .env.example                # Template for server .env
└── scripts/
    ├── backup-db.sh
    ├── setup-vps.sh            # Initial VPS provisioning
    └── init-certbot.sh         # First-time TLS setup

.github/
└── workflows/
    └── deploy.yml
```
