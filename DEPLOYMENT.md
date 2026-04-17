# Deployment Information

## Public URL

**https://day12ha-tang-cloudvadeployment-production.up.railway.app**

## Platform

Railway — builder = Dockerfile, root directory = `06-lab-complete`, 1 agent replica + Redis plugin.

## Environment Variables (Railway)

| Variable | Value |
|----------|-------|
| `PORT` | `8000` (khớp Target Port trong Public Networking) |
| `ENVIRONMENT` | `production` |
| `AGENT_API_KEY` | `<random 32 hex>` — sinh bằng `openssl rand -hex 16` |
| `JWT_SECRET` | `<random 64 hex>` — sinh bằng `openssl rand -hex 32` |
| `RATE_LIMIT_PER_MINUTE` | `10` |
| `MONTHLY_BUDGET_USD` | `10.0` |
| `ALLOWED_ORIGINS` | `*` |
| `REDIS_URL` | `${{Redis.REDIS_URL}}` (reference tới Redis plugin) |

## Test Commands

### 1. Health check
```bash
curl https://day12ha-tang-cloudvadeployment-production.up.railway.app/health
```
**Output:**
```json
{"status":"ok","version":"1.0.0","environment":"production","uptime_seconds":192.2,"total_requests":2,"timestamp":"2026-04-17T08:03:56.860462+00:00"}
```

### 2. Readiness
```bash
curl https://day12ha-tang-cloudvadeployment-production.up.railway.app/ready
```
**Output:** `{"ready":true}`

### 3. Root info
```bash
curl https://day12ha-tang-cloudvadeployment-production.up.railway.app/
```
**Output:**
```json
{"app":"Production AI Agent","version":"1.0.0","environment":"production","endpoints":{"ask":"POST /ask  (X-API-Key required, body: {user_id, question})","health":"GET /health","ready":"GET /ready","metrics":"GET /metrics (X-API-Key required)"}}
```

### 4. Ask endpoint (authenticated)
```bash
URL=https://day12ha-tang-cloudvadeployment-production.up.railway.app
KEY=<your AGENT_API_KEY>

curl -X POST $URL/ask \
  -H "X-API-Key: $KEY" \
  -H "Content-Type: application/json" \
  -d '{"user_id":"test","question":"Hello"}'
```
**Output:**
```json
{"user_id":"test","question":"Hello","answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic.","model":"gpt-4o-mini","timestamp":"2026-04-17T08:05:51.686268+00:00"}
```

### 5. Unauthorized (expect 401)
```bash
curl -s -o /dev/null -w "status=%{http_code}\n" \
  -X POST https://day12ha-tang-cloudvadeployment-production.up.railway.app/ask \
  -H "Content-Type: application/json" \
  -d '{"user_id":"x","question":"hi"}'
```
**Output:** `status=401`

### 6. Rate limit (10 req/min → 11th returns 429)
```bash
URL=https://day12ha-tang-cloudvadeployment-production.up.railway.app
KEY=<your AGENT_API_KEY>

for i in $(seq 1 12); do
  code=$(curl -s -o /dev/null -w "%{http_code}" -X POST $URL/ask \
    -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
    -d '{"user_id":"rl-demo","question":"ping"}')
  echo "req $i → $code"
done
```
**Output:**
```
req 1 → 200
req 2 → 200
req 3 → 200
req 4 → 200
req 5 → 200
req 6 → 200
req 7 → 200
req 8 → 200
req 9 → 200
req 10 → 200
req 11 → 429
req 12 → 429
```

### 7. Metrics (authenticated)
```bash
curl "$URL/metrics?user_id=test" -H "X-API-Key: $KEY"
```
**Output:**
```json
{"uptime_seconds":316.2,"total_requests":31,"error_count":0,"inflight":1,"usage":{"user_id":"test","month":"2026-04","spent_usd":0.0,"budget_usd":10.0,"remaining_usd":10.0,"used_pct":0.0}}
```

## Screenshots

Xem thư mục [screenshots/](screenshots/):
- `dashboard.png` — Railway project view với agent + redis service
- `deploy-success.png` — deployment log "Healthcheck succeeded"
- `test-curl.png` — output các test command ở trên

## Troubleshooting history

- **Healthcheck fail lần 1:** `startCommand` trong `railway.toml` không qua shell → `$PORT` bị truyền nguyên string → uvicorn reject `Invalid value for '--port'`. **Fix:** xoá `startCommand`, để Dockerfile shell-form CMD expand `${PORT:-8000}`.
- **Uvicorn ModuleNotFoundError (local docker-compose):** `pip install --user` trong builder stage tạo path `/root/.local`, copy sang `/home/agent/.local` nhưng user `agent` có home `/app` (do `-d /app` trong useradd) → Python tìm site-packages sai chỗ. **Fix:** `useradd -m -d /home/agent` + `PYTHONPATH=/home/agent/.local/lib/python3.11/site-packages`.
- **Starlette MutableHeaders.pop AttributeError:** không có method `.pop()`. **Fix:** `if "server" in response.headers: del response.headers["server"]`.
