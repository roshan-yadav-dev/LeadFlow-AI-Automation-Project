# Phase 7: Deployment & Production Operations Guide

## 1. Overview

LeadFlow AI Phase 7 features a decoupled architecture:
1. **Backend:** FastAPI application running with Uvicorn, SQLite WAL stores, and single-worker automation background loop.
2. **Frontend:** React 18 / Vite 5 Single Page Application compiled to optimized static assets.

---

## 2. Production Build

Build the frontend static bundle:

```bash
cd ~/LeadFlow-AI/frontend
npm ci
npm run build
```

The compiled assets are generated in `frontend/dist/`:
- `dist/index.html`
- `dist/assets/index-[hash].js`
- `dist/assets/index-[hash].css`

---

## 3. Serving Architectures

### Option A: Reverse Proxy (Recommended for Production)
Use Nginx or Caddy in front of FastAPI and Vite static files.

**Nginx Configuration Example (`/etc/nginx/sites-available/leadflow`):**
```nginx
server {
    listen 80;
    server_name crm.yourcompany.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name crm.yourcompany.com;

    ssl_certificate /etc/letsencrypt/live/crm.yourcompany.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/crm.yourcompany.com/privkey.pem;

    # Serve React SPA static files
    root /home/roshan/LeadFlow-AI/frontend/dist;
    index index.html;

    # SPA routing fallback
    location / {
        try_files $uri $uri/ /index.html;
    }

    # Proxy API and Webhook requests to FastAPI backend
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # OpenAPI Docs
    location ~ ^/(docs|redoc|openapi.json) {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
    }
}
```

### Option B: FastAPI Static Mount
FastAPI can serve the frontend directly using `StaticFiles`:

```python
# In app/main.py
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os

frontend_dist = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.exists(frontend_dist):
    app.mount("/assets", StaticFiles(directory=os.path.join(frontend_dist, "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        file_path = os.path.join(frontend_dist, full_path)
        if os.path.exists(file_path) and os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(frontend_dist, "index.html"))
```

---

## 4. Production Environment Variables

Configure `.env` on your production server:

```env
# Application & Security
ENVIRONMENT=production
DASHBOARD_USERNAME=admin
DASHBOARD_PASSWORD=ChangeMeToAStrongRandomPassword123!
SESSION_SECRET_KEY=generate_with_openssl_rand_hex_32
SESSION_COOKIE_SECURE=true
CORS_ORIGINS=["https://crm.yourcompany.com"]

# Webhook Secret (Server-side only)
WEBHOOK_SECRET=your_high_entropy_webhook_secret

# AI & External Services
GROQ_API_KEY=your_groq_api_key
GMAIL_SENDER_EMAIL=leads@yourcompany.com

# Automation Engine
AUTOMATION_DB_FILE=credentials/automation.sqlite3
AUTOMATION_WORKER_ENABLED=true
AUTOMATION_WORKER_POLL_INTERVAL_SECONDS=10
AUTOMATION_DEFAULT_TIMEZONE=Asia/Kolkata
```

---

## 5. Security & TLS Checklist

1. **HTTPS / TLS:** Always run under HTTPS in production. Ensure `SESSION_COOKIE_SECURE=true` so session cookies are only transmitted over TLS.
2. **CSRF Validation:** Verify that state-changing requests transmit the `X-CSRF-Token` header.
3. **Owner-Only SQLite File Permissions:** Ensure SQLite databases have restricted permissions (`chmod 600 credentials/*.sqlite3`).
4. **Single-Worker Enforcement:** Run FastAPI with a single worker process (`--workers 1`) or use Celery/Redis if scaling to multi-process architectures, preserving SQLite single-writer safety.
