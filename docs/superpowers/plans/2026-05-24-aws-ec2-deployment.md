# AWS EC2 Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy the Flame FastAPI backend to a single AWS EC2 t3.small instance with Docker Compose, Nginx SSL, and GitHub Actions auto-deploy on push to main.

**Architecture:** FastAPI app + Redis run as Docker Compose services behind an Nginx reverse proxy. Let's Encrypt handles SSL for `api.flame.banatalk.com`. GitHub Actions SSHs into the server on push to main and rebuilds only the app container.

**Tech Stack:** Docker, Docker Compose, Nginx, Certbot/Let's Encrypt, GitHub Actions (appleboy/ssh-action), Python 3.12-slim, Ubuntu 22.04

---

## Files to Create

| File | Purpose |
|------|---------|
| `Dockerfile` | Build the FastAPI app image |
| `.dockerignore` | Exclude venv, .env, __pycache__ from image |
| `docker-compose.yml` | Define app, redis, nginx services |
| `nginx/nginx.conf` | Reverse proxy + WebSocket + SSL config |
| `.github/workflows/deploy.yml` | GitHub Actions CI/CD pipeline |

---

## Task 1: Dockerfile + .dockerignore

**Files:**
- Create: `Dockerfile`
- Create: `.dockerignore`

- [ ] **Step 1: Create `.dockerignore`**

```
venv/
__pycache__/
*.pyc
*.pyo
.env
.git/
.github/
docs/
*.md
```

- [ ] **Step 2: Create `Dockerfile`**

`python-magic` requires `libmagic1` to be installed as a system package.

```dockerfile
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
```

- [ ] **Step 3: Verify the image builds locally**

```bash
docker build -t flame-backend .
```

Expected: build completes with no errors, final layer shows `CMD`.

- [ ] **Step 4: Commit**

```bash
git add Dockerfile .dockerignore
git commit -m "feat: add Dockerfile and .dockerignore for EC2 deployment"
```

---

## Task 2: docker-compose.yml

**Files:**
- Create: `docker-compose.yml`

- [ ] **Step 1: Create `docker-compose.yml`**

```yaml
services:
  redis:
    image: redis:7-alpine
    restart: unless-stopped
    volumes:
      - redis_data:/data
    networks:
      - internal

  app:
    build: .
    restart: unless-stopped
    env_file: .env
    depends_on:
      - redis
    expose:
      - "8000"
    networks:
      - internal

  nginx:
    image: nginx:alpine
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/conf.d/default.conf:ro
      - /etc/letsencrypt:/etc/letsencrypt:ro
    depends_on:
      - app
    networks:
      - internal

networks:
  internal:

volumes:
  redis_data:
```

- [ ] **Step 2: Validate the compose file syntax**

```bash
docker compose config
```

Expected: prints the fully resolved config with no errors.

- [ ] **Step 3: Commit**

```bash
git add docker-compose.yml
git commit -m "feat: add docker-compose.yml with app, redis, nginx services"
```

---

## Task 3: Nginx Config

**Files:**
- Create: `nginx/nginx.conf`

- [ ] **Step 1: Create `nginx/` directory and config**

```bash
mkdir -p nginx
```

Create `nginx/nginx.conf`:

```nginx
server {
    listen 80;
    server_name api.flame.banatalk.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name api.flame.banatalk.com;

    ssl_certificate /etc/letsencrypt/live/api.flame.banatalk.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.flame.banatalk.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    location / {
        proxy_pass http://app:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
    }

    location /ws {
        proxy_pass http://app:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 86400s;
    }
}
```

- [ ] **Step 2: Validate nginx config syntax**

```bash
docker run --rm \
  -v $(pwd)/nginx/nginx.conf:/etc/nginx/conf.d/default.conf:ro \
  nginx:alpine nginx -t
```

Expected output:
```
nginx: the configuration file /etc/nginx/nginx.conf syntax is ok
nginx: configuration file /etc/nginx/nginx.conf test is successful
```

- [ ] **Step 3: Commit**

```bash
git add nginx/nginx.conf
git commit -m "feat: add nginx reverse proxy config with SSL and WebSocket support"
```

---

## Task 4: GitHub Actions Workflow

**Files:**
- Create: `.github/workflows/deploy.yml`

- [ ] **Step 1: Create `.github/workflows/deploy.yml`**

```bash
mkdir -p .github/workflows
```

```yaml
name: Deploy to EC2

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest

    steps:
      - name: Deploy to EC2
        uses: appleboy/ssh-action@v1.0.3
        with:
          host: ${{ secrets.EC2_HOST }}
          username: ${{ secrets.EC2_USER }}
          key: ${{ secrets.EC2_SSH_KEY }}
          script: |
            cd /home/ubuntu/flame_backend
            git pull origin main
            docker compose up -d --build app
            sleep 8
            curl -sf https://api.flame.banatalk.com/health || exit 1
```

- [ ] **Step 2: Commit and push**

```bash
git add .github/workflows/deploy.yml
git commit -m "feat: add GitHub Actions deploy workflow for EC2"
git push origin main
```

Expected: workflow appears in GitHub → Actions tab (it will fail until EC2 secrets are set — that's fine for now).

---

## Task 5: Launch EC2 Instance (AWS Console)

These are manual AWS console steps.

- [ ] **Step 1: Launch EC2 instance**

  Go to EC2 → Launch Instance:
  - Name: `flame-backend`
  - AMI: `Ubuntu Server 22.04 LTS (HVM)` (64-bit x86)
  - Instance type: `t3.small`
  - Key pair: create new → name it `flame-ec2` → download the `.pem` file → **keep it safe**
  - Security group: create new named `flame-backend-sg` with these inbound rules:
    - SSH (22) — My IP
    - HTTP (80) — Anywhere (0.0.0.0/0)
    - HTTPS (443) — Anywhere (0.0.0.0/0)
  - Storage: 20 GB gp3 (default is fine)
  - Click **Launch Instance**

- [ ] **Step 2: Allocate and attach Elastic IP**

  Go to EC2 → Elastic IPs → Allocate Elastic IP address → Allocate.
  Select the new IP → Actions → Associate Elastic IP → select `flame-backend` instance → Associate.

  Note the Elastic IP — you'll need it for DNS and GitHub secrets.

- [ ] **Step 3: Add DNS A record**

  In your domain registrar (wherever `banatalk.com` DNS is managed):
  - Type: `A`
  - Name: `api.flame`
  - Value: `<your-elastic-ip>`
  - TTL: 300

  Verify propagation (may take a few minutes):
  ```bash
  dig api.flame.banatalk.com A +short
  ```
  Expected: your Elastic IP

---

## Task 6: Bootstrap the Server

SSH into the instance and install dependencies. Run these commands one block at a time.

- [ ] **Step 1: SSH into the instance**

```bash
chmod 400 flame-ec2.pem
ssh -i flame-ec2.pem ubuntu@<your-elastic-ip>
```

- [ ] **Step 2: Install Docker**

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
sudo usermod -aG docker ubuntu
```

Log out and back in so the docker group takes effect:
```bash
exit
ssh -i flame-ec2.pem ubuntu@<your-elastic-ip>
```

Verify:
```bash
docker --version
docker compose version
```

Expected: both commands print version numbers.

- [ ] **Step 3: Install Certbot**

```bash
sudo apt-get install -y certbot
```

- [ ] **Step 4: Clone the repo**

```bash
cd /home/ubuntu
git clone https://github.com/firdavs9777/flame_backend.git
cd flame_backend
```

- [ ] **Step 5: Copy the production `.env` to the server**

From your **local machine** (new terminal, not the SSH session):

```bash
scp -i flame-ec2.pem .env ubuntu@<your-elastic-ip>:/home/ubuntu/flame_backend/.env
```

Then back in the SSH session, update two values in `.env`:

```bash
nano /home/ubuntu/flame_backend/.env
```

Change these lines:
```
REDIS_URL=redis://redis:6379
DEBUG=False
CORS_ORIGINS=["https://flame.banatalk.com"]
```

`redis://redis:6379` uses the Docker Compose service name. Replace `https://flame.banatalk.com` with your actual frontend domain.

---

## Task 7: SSL Certificate

Certbot needs port 80 free to complete the HTTP challenge. Run it before starting containers.

- [ ] **Step 1: Obtain SSL certificate**

On the server (SSH session):

```bash
sudo certbot certonly --standalone \
  -d api.flame.banatalk.com \
  --non-interactive \
  --agree-tos \
  -m your-email@example.com
```

Expected output ends with:
```
Successfully received certificate.
Certificate is saved at: /etc/letsencrypt/live/api.flame.banatalk.com/fullchain.pem
Key is saved at: /etc/letsencrypt/live/api.flame.banatalk.com/privkey.pem
```

- [ ] **Step 2: Set up auto-renewal cron**

```bash
(crontab -l 2>/dev/null; echo "0 3 * * * sudo certbot renew --quiet && docker compose -f /home/ubuntu/flame_backend/docker-compose.yml exec nginx nginx -s reload") | crontab -
```

Verify it was saved:
```bash
crontab -l
```

Expected: shows the certbot renewal line.

---

## Task 8: First Deploy

- [ ] **Step 1: Start all containers**

On the server:

```bash
cd /home/ubuntu/flame_backend
docker compose up -d
```

- [ ] **Step 2: Check all containers are running**

```bash
docker compose ps
```

Expected:
```
NAME                    STATUS
flame_backend-app-1     Up
flame_backend-redis-1   Up
flame_backend-nginx-1   Up
```

- [ ] **Step 3: Check app logs for errors**

```bash
docker compose logs app --tail=50
```

Expected: see `Uvicorn running on http://0.0.0.0:8000` and `MongoDB connected`. No ERROR lines.

- [ ] **Step 4: Verify health endpoint**

```bash
curl -s https://api.flame.banatalk.com/health
```

Expected:
```json
{"status":"healthy","version":"1.0.0"}
```

- [ ] **Step 5: Verify API docs are reachable**

Open in browser: `https://api.flame.banatalk.com/docs`

Expected: Swagger UI loads with all endpoints listed.

---

## Task 9: Wire Up GitHub Actions Auto-Deploy

- [ ] **Step 1: Add GitHub secrets**

Go to your GitHub repo → Settings → Secrets and variables → Actions → New repository secret. Add three secrets:

| Name | Value |
|------|-------|
| `EC2_HOST` | `api.flame.banatalk.com` |
| `EC2_USER` | `ubuntu` |
| `EC2_SSH_KEY` | Full contents of `flame-ec2.pem` (including `-----BEGIN RSA PRIVATE KEY-----` header/footer) |

- [ ] **Step 2: Allow GitHub Actions to pull from the server**

On the server, configure git to not need a password for pull (the repo is public — this just avoids prompt issues):

```bash
cd /home/ubuntu/flame_backend
git config pull.rebase false
```

- [ ] **Step 3: Trigger a test deploy**

On your local machine, make a small change and push:

```bash
# In flame_backend repo locally
git commit --allow-empty -m "test: trigger auto-deploy"
git push origin main
```

- [ ] **Step 4: Watch the GitHub Actions run**

Go to GitHub → Actions → the latest workflow run.

Expected: all steps green, final step shows:
```
{"status":"healthy","version":"1.0.0"}
```

- [ ] **Step 5: Clean up test commit**

```bash
git revert HEAD --no-edit
git push origin main
```

---

## Task 10: Smoke Test

- [ ] **Step 1: Test register endpoint**

```bash
curl -s -X POST https://api.flame.banatalk.com/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"Test1234","name":"Test","age":25,"gender":"male","looking_for":"female","interests":["music"],"photos":["https://example.com/photo.jpg"],"latitude":37.7749,"longitude":-122.4194}' | python3 -m json.tool
```

Expected: `{"success": true, "data": {"user": {...}, "tokens": {...}}}` or a validation error with a clear message (not a 500).

- [ ] **Step 2: Test WebSocket connection**

```bash
# Install wscat if needed: npm install -g wscat
wscat -c "wss://api.flame.banatalk.com/ws?token=<access_token_from_step_1>"
```

Expected: connection opens, server sends a pong when you send `{"type":"ping"}`.

- [ ] **Step 3: Verify Redis is working**

```bash
ssh -i flame-ec2.pem ubuntu@<your-elastic-ip> \
  "docker compose -f /home/ubuntu/flame_backend/docker-compose.yml exec redis redis-cli ping"
```

Expected: `PONG`
