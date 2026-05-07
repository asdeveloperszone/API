# ASDroid TikTok API 🥰❤️👑

> **Production-ready TikTok Video Downloader API**  
> Built by **M.ASIM** from 🇵🇰 Pakistan  
> Version: `2.0.0` | Deploy Target: Railway

---

## Features

- 🎯 **Watermark-free** video extraction via multi-strategy HTML parsing
- ⚡ **Zero storage** — videos stream directly from TikTok CDN to client
- 🔄 **Short-link support** — `vm.tiktok.com` and `vt.tiktok.com` auto-resolved
- 🛡️ **Rate limiting** — per-IP (SlowAPI) with proper `429 + Retry-After`
- 💾 **In-memory cache** — 5-min TTL reduces duplicate TikTok fetches
- 📦 **Range request support** — allows partial downloads and video seeking
- 🔒 **SSRF-safe** — domain allow-list, input sanitisation, no `eval()`

---

## Project Structure

```
tiktok-api/
├── app/
│   ├── __init__.py
│   ├── main.py            ← FastAPI app, middleware, exception handlers
│   ├── config.py          ← Pydantic Settings (env vars)
│   ├── models.py          ← Request/response Pydantic models
│   ├── routers/
│   │   └── download.py    ← All API endpoints
│   ├── services/
│   │   ├── resolver.py    ← TikTok HTML extraction (3 strategies)
│   │   ├── streamer.py    ← CDN proxy / streaming
│   │   └── signer.py      ← X-Bogus placeholder (future)
│   └── utils/
│       ├── cache.py       ← In-memory TTL cache
│       ├── exceptions.py  ← Custom exception hierarchy
│       ├── logger.py      ← Structured logging + request ID
│       └── validators.py  ← URL validation & sanitisation
├── .env.example
├── .gitignore
├── Procfile
├── railway.json
├── requirements.txt
└── runtime.txt
```

---

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/health` | Health check + uptime |
| `GET` | `/api/v1/info` | API metadata + rate-limit config |
| `POST` | `/api/v1/resolve` | Resolve TikTok URL → video info |
| `GET` | `/api/v1/download` | Stream video to client |

---

## Local Development

### 1. Clone & set up environment

```bash
git clone https://github.com/asdeveloperszone/asdroid-tiktok-api.git
cd asdroid-tiktok-api

python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env if needed — defaults work out of the box
```

### 3. Run locally

```bash
uvicorn app.main:app --reload --port 8000
```

### 4. Open Swagger docs

```
http://localhost:8000/docs
```

---

## Testing the API

### Health check

```bash
curl http://localhost:8000/api/v1/health
```

Expected:
```json
{
  "success": true,
  "data": {
    "status": "ok",
    "version": "2.0.0",
    "uptime_seconds": 3.14,
    "cache_size": 0
  }
}
```

---

### Resolve a TikTok video

```bash
curl -X POST http://localhost:8000/api/v1/resolve \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.tiktok.com/@tiktok/video/7106594312292453675"}'
```

Expected:
```json
{
  "success": true,
  "data": {
    "video_id": "7106594312292453675",
    "author": "tiktok",
    "description": "Video caption here",
    "duration": 15,
    "download_url": "https://v19-webapp.tiktok.com/...",
    "thumbnail_url": "https://p16-sign.tiktokcdn-us.com/...",
    "like_count": 1234567
  }
}
```

---

### Stream / download a video

```bash
# In browser or curl:
curl -L "http://localhost:8000/api/v1/download?url=https%3A%2F%2Fwww.tiktok.com%2F%40tiktok%2Fvideo%2F7106594312292453675" \
  --output video.mp4
```

---

## Deploy to Railway

### Step 1 — Push to GitHub

```bash
git init
git add .
git commit -m "Initial commit — ASDroid TikTok API v2.0.0"
git remote add origin https://github.com/YOUR_USERNAME/asdroid-tiktok-api.git
git push -u origin main
```

### Step 2 — Create Railway project

1. Go to [railway.app](https://railway.app) and sign in
2. Click **New Project → Deploy from GitHub repo**
3. Select your repository
4. Railway auto-detects Python via Nixpacks

### Step 3 — Set environment variables

In Railway dashboard → your service → **Variables**, add:

```
API_VERSION=2.0.0
DEBUG_MODE=false
LOG_LEVEL=INFO
RATE_LIMIT_PER_MINUTE=30
RATE_LIMIT_PER_HOUR=1000
CACHE_TTL_SECONDS=300
MAX_VIDEO_SIZE_MB=500
```

### Step 4 — Get public URL

Railway dashboard → your service → **Settings → Domains → Generate Domain**

You'll get something like: `https://asdroid-tiktok-api-production.up.railway.app`

### Step 5 — Test deployed API

```bash
# Health check
curl https://YOUR-APP.up.railway.app/api/v1/health

# In browser
https://YOUR-APP.up.railway.app/docs
```

### Automatic deployments (GitHub Actions)

1. Get your Railway token: Railway dashboard → Account → Tokens → Create
2. Add to GitHub: Settings → Secrets → `RAILWAY_TOKEN`
3. Every push to `main` auto-deploys via `.github/workflows/deploy.yml`

---

## Error Codes

| Code | HTTP | Description |
|------|------|-------------|
| `INVALID_URL` | 400 | URL is not a valid TikTok URL |
| `VIDEO_NOT_FOUND` | 404 | Video deleted, private, or ID invalid |
| `TIKTOK_BLOCKED` | 503 | TikTok returned 403/429 |
| `EXTRACTION_FAILED` | 502 | All parsing strategies failed |
| `RATE_LIMITED` | 429 | Client hit our API rate limit |
| `STREAM_ERROR` | 502 | CDN streaming failed |
| `INTERNAL_ERROR` | 500 | Unexpected server error |

---

## Android App Integration

```kotlin
// Retrofit interface
interface TikTokApiService {
    @POST("api/v1/resolve")
    suspend fun resolveVideo(@Body request: ResolveRequest): ApiResponse<VideoInfo>

    @Streaming
    @GET("api/v1/download")
    suspend fun downloadVideo(@Query("url") url: String): Response<ResponseBody>
}

data class ResolveRequest(val url: String, val quality: String = "hd")
```

---

## License

MIT — Free to use, modify, and deploy.

---

> Made with 🥰❤️👑 by **M.ASIM** — Pakistan  
> GitHub: [@asdeveloperszone](https://github.com/asdeveloperszone)
