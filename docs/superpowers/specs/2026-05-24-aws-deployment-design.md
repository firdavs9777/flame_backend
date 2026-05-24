# AWS Deployment Design — Flame Backend

**Date:** 2026-05-24
**Status:** Approved

---

## Overview

Deploy the Flame FastAPI backend to a single AWS EC2 instance using Docker Compose, with GitHub Actions for automated CI/CD. MongoDB stays on Atlas, file storage stays on DigitalOcean Spaces.

**Target scale:** MVP / early users (hundreds of users, low concurrent load)
**Estimated cost:** ~$20–22/month

---

## Infrastructure

### EC2 Instance
- **Type:** t3.small (2 vCPU, 2GB RAM)
- **OS:** Ubuntu 22.04 LTS
- **Elastic IP:** One static IP attached — survives instance restarts
- **DNS:** User's existing domain A record → Elastic IP

### Security Group
| Port | Protocol | Source | Purpose |
|------|----------|--------|---------|
| 22 | TCP | Your IP only | SSH access |
| 80 | TCP | 0.0.0.0/0 | HTTP (redirects to HTTPS) |
| 443 | TCP | 0.0.0.0/0 | HTTPS + WebSocket |

All other ports closed. Redis (6379) and app (8000) are internal to Docker only.

---

## Docker Compose

Three containers on a shared internal Docker network:

### `app`
- Builds from `Dockerfile` in repo root
- Base image: `python:3.12-slim`
- Runs: `uvicorn app.main:app --host 0.0.0.0 --port 8000`
- Reads secrets from `.env` file on server (never in repo)
- Depends on `redis`

### `redis`
- Image: `redis:7-alpine`
- Internal only — not bound to host ports
- Data persisted via named Docker volume `redis_data`

### `nginx`
- Image: `nginx:alpine`
- Binds host ports 80 and 443
- Mounts: nginx config + Let's Encrypt certs (read-only)
- Handles SSL termination and WebSocket proxying

---

## Nginx Configuration

- HTTP (port 80) → redirect to HTTPS
- HTTPS (port 443) → proxy to `app:8000`
  - Standard proxy headers: `X-Real-IP`, `X-Forwarded-For`, `Host`
- `/ws` route → WebSocket proxy with `Upgrade` and `Connection` headers

### SSL
- Provider: Let's Encrypt via Certbot (installed on host)
- Certs stored at `/etc/letsencrypt/` on host, mounted read-only into Nginx container
- Auto-renewal: host cron job runs `certbot renew --quiet` twice daily; reloads Nginx on renewal

---

## CI/CD Pipeline (GitHub Actions)

**Trigger:** Push to `main` branch

**Steps:**
1. SSH into EC2 using stored private key
2. `git pull origin main` on the server
3. `docker compose up -d --build app` — rebuilds and restarts only the app container
4. Health check: `curl -f https://<domain>/health` — fails the action if unhealthy

Redis and Nginx containers are not touched on deploy.
Downtime per deploy: ~5–10 seconds (container restart only).

### GitHub Secrets Required
| Secret | Value |
|--------|-------|
| `EC2_HOST` | Elastic IP or domain |
| `EC2_USER` | `ubuntu` |
| `EC2_SSH_KEY` | EC2 private key (PEM) |

---

## Environment Variables

The `.env` file is copied to the server manually once via SSH. It is never committed to the repo. Contains all production values:

- `MONGODB_URL` — Atlas connection string
- `JWT_SECRET_KEY` — strong random secret (not the dev value)
- `REDIS_URL` — `redis://redis:6379` (Docker service name)
- `DO_SPACES_KEY`, `DO_SPACES_SECRET` — DigitalOcean credentials
- `CORS_ORIGINS` — production frontend domain only (not `["*"]`)
- All other existing `.env` variables

---

## Deployment Architecture Diagram

```
GitHub push to main
        ↓
GitHub Actions (SSH)
        ↓
  EC2 t3.small (Ubuntu 22.04)
  ┌─────────────────────────────────────┐
  │  Nginx :443 ──→ app:8000 (FastAPI)  │
  │  Nginx :80  ──→ redirect to HTTPS   │
  │  /ws        ──→ WebSocket proxy     │
  │  redis:6379 (internal only)         │
  └─────────────────────────────────────┘
        ↓                    ↓
  MongoDB Atlas       DO Spaces (files)
```

---

## Files to Create

| File | Purpose |
|------|---------|
| `Dockerfile` | Build image for FastAPI app |
| `docker-compose.yml` | Defines app, redis, nginx services |
| `nginx/nginx.conf` | Nginx reverse proxy + WebSocket config |
| `.github/workflows/deploy.yml` | GitHub Actions CI/CD workflow |
| `.dockerignore` | Exclude venv, __pycache__, .env from build |

---

## Out of Scope

- Load balancing / multiple instances (not needed at MVP scale)
- ElastiCache or RDS (Atlas + local Redis sufficient)
- ECR / Docker Hub (images built directly on server)
- Blue/green deployments (5–10s restart acceptable for MVP)
