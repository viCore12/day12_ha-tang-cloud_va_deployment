# Day 12 Lab — Mission Answers

> **Student:** Lưu Lương Vi Nhân
> **Date:** 2026-04-17
> **Deployed URL:** https://day12ha-tang-cloudvadeployment-production.up.railway.app

---

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns in [01-localhost-vs-production/develop/app.py](01-localhost-vs-production/develop/app.py)

1. **Hardcoded secrets** — `OPENAI_API_KEY`, `DATABASE_URL` nằm thẳng trong code, push GitHub = lộ key.
2. **Debug flag bật cứng** (`DEBUG = True`, `reload=True`) → leak stack trace ra client, restart liên tục trong prod.
3. **Logging bằng `print()`** — không có level, không JSON, không redact secret (`print(... OPENAI_API_KEY)` in secret ra stdout).
4. **Không có `/health` hay `/ready` endpoint** → orchestrator không biết restart container chết.
5. **Host cứng `localhost`** → container bind `127.0.0.1` không ai access được từ ngoài.
6. **Port cứng `8000`** → không đọc `$PORT` từ env, platform Railway/Render gán port khác là fail.
7. **Không graceful shutdown** — nhận SIGTERM là kill luôn, request đang chạy bị cụt.

### Exercise 1.3: Develop vs Production

| Feature | Develop | Production | Why important |
|---------|---------|------------|----------------|
| Config | Hardcode trong source | Env vars + validate khi start | Đổi giá trị không cần rebuild; tránh leak secret khi commit |
| Health check | Không có | `GET /health` + `GET /ready` | Platform biết liveness để restart; LB biết readiness để route |
| Logging | `print()` | JSON structured (`{"ts", "lvl", "event", ...}`) | Parse được bằng Loki/Datadog; redact secrets |
| Shutdown | SIGTERM → kill ngay | Drain inflight 25s rồi mới exit | Request không bị cụt giữa chừng khi deploy/scale |
| Secret handling | Source code | Env + gitignore `.env` | Rotate key không cần PR; không lộ qua git history |
| Port binding | `localhost:8000` | `0.0.0.0:$PORT` | Bind mọi interface; đọc PORT do platform gán |

---

## Part 2: Docker

### Exercise 2.1: Dockerfile cơ bản ([02-docker/develop/Dockerfile](02-docker/develop/Dockerfile))

1. **Base image:** `python:3.11` (full ~1 GB).
2. **Working directory:** `/app`.
3. **COPY requirements trước?** Tận dụng layer cache — chỉ re-install dependencies khi `requirements.txt` đổi, không phải mỗi khi code thay đổi.
4. **CMD vs ENTRYPOINT:** `CMD` là default args có thể override bằng `docker run <image> <cmd>`; `ENTRYPOINT` là executable cố định, args từ CMD/CLI được append vào. Dùng `CMD` khi muốn cho phép override, `ENTRYPOINT` khi image = 1 binary cụ thể.

### Exercise 2.3: Image size so sánh

- **Develop:** ~1020 MB (single-stage, base `python:3.11`)
- **Production:** ~230 MB (multi-stage, base `python:3.11-slim`)
- **Difference:** ~77% giảm

Lý do: multi-stage chỉ copy `/root/.local` site-packages sang runtime, bỏ hẳn gcc/apt cache/dev headers.

---

## Part 3: Cloud Deployment

### Exercise 3.1: Railway deployment

- **URL:** https://day12ha-tang-cloudvadeployment-production.up.railway.app
- **Platform:** Railway (builder = Dockerfile)
- **Services:** 1 × agent (FastAPI + uvicorn) + 1 × Redis plugin
- **Root directory:** `06-lab-complete`
- **Target port:** 8000 (khớp với `PORT` env var)
- **Screenshots:**
  - [screenshots/dashboard.png](screenshots/dashboard.png) — Railway project canvas (agent + Redis)
  - [screenshots/deploy-success.png](screenshots/deploy-success.png) — Deploy Logs with "Uvicorn running" + healthcheck success
  - [screenshots/test-curl.png](screenshots/test-curl.png) — Terminal output of test commands (see [screenshots/test-output.md](screenshots/test-output.md))

Xem chi tiết env vars + test output trong [DEPLOYMENT.md](DEPLOYMENT.md).

### Key lesson

Railway `startCommand` trong `railway.toml` **không chạy qua shell** → `$PORT` không expand → uvicorn nhận string literal `$PORT` và crash `Invalid value for '--port'`. Fix: xoá `startCommand`, để Dockerfile CMD (shell form) shell-expand `${PORT:-8000}`.

---

## Part 4: API Security

### Exercise 4.1: API Key authentication

- Key được check trong [app/auth.py](06-lab-complete/app/auth.py) bằng FastAPI dependency `verify_api_key` đọc header `X-API-Key`.
- Sai/thiếu key → raise `HTTPException(401)` trước khi vào business logic.
- **Rotate:** đổi `AGENT_API_KEY` trong Railway Variables → auto redeploy, key cũ vô hiệu ngay.

**Test output (live Railway URL):**
```bash
# Không có key → 401
$ curl -s -o /dev/null -w "HTTP %{http_code}\n" -X POST $URL/ask \
    -H "Content-Type: application/json" -d '{"user_id":"x","question":"hi"}'
HTTP 401

# Có key hợp lệ → 200
$ curl -s -X POST $URL/ask -H "X-API-Key: $KEY" \
    -H "Content-Type: application/json" \
    -d '{"user_id":"demo","question":"Hello Railway!"}'
{
  "user_id": "demo",
  "question": "Hello Railway!",
  "answer": "Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé.",
  "model": "gpt-4o-mini",
  "timestamp": "2026-04-17T08:24:09.678689+00:00"
}
```

### Exercise 4.2: JWT

Lab 06 dùng API Key thuần thay vì JWT vì use case chỉ có server-to-server — key cố định dễ manage, không cần expiry/refresh. JWT phù hợp hơn khi có frontend với session người dùng.

### Exercise 4.3: Rate limiting

- **Algorithm:** Sliding window (Redis sorted set `ratelimit:<user_id>`, score = timestamp).
- **Giới hạn:** 10 req/min per `user_id` (cấu hình `RATE_LIMIT_PER_MINUTE`).
- **Code:** [app/rate_limiter.py](06-lab-complete/app/rate_limiter.py).

**Test output (live Railway URL):**
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

Bypass admin: không implement trong lab — production sẽ làm bằng cách cho admin API key có tier riêng với limit cao hơn (dùng `DEMO_USERS["admin"]["daily_limit"]` pattern từ [04-api-gateway/production/auth.py](04-api-gateway/production/auth.py)).

### Exercise 4.4: Cost guard

**Approach** ([app/cost_guard.py](06-lab-complete/app/cost_guard.py)):

1. Key Redis `budget:<user_id>:YYYY-MM` chứa USD đã chi trong tháng.
2. Trước mỗi LLM call: `check_budget(user_id)` — nếu `spent >= MONTHLY_BUDGET_USD` raise `402 Payment Required`.
3. Sau LLM call: `record_usage(user_id, input_tokens, output_tokens)` — `INCRBYFLOAT` atomic + `EXPIRE 32d`.
4. TTL 32 ngày → tự rollover đầu tháng sau.

Giá token tính theo GPT-4o-mini pricing (`$0.15/1M input`, `$0.60/1M output`). Fallback in-memory khi Redis không có (local dev).

---

## Part 5: Scaling & Reliability

### Exercise 5.1: Health checks

- **`/health`** (liveness): trả `status: ok` + uptime + total_requests. Platform gọi → nếu fail thì restart container.
- **`/ready`** (readiness): check flag `_is_ready` (set trong lifespan), đồng thời trả 503 khi đang `_is_shutting_down`. LB không route request mới nếu fail → giúp rolling deploy không bị 502.

### Exercise 5.2: Graceful shutdown

Handler trong [app/main.py:202-205](06-lab-complete/app/main.py):
1. Signal SIGTERM/SIGINT set `_is_shutting_down = True`.
2. `/ready` ngay lập tức trả 503 → LB ngừng route.
3. Lifespan shutdown wait inflight requests xong (timeout 25s) rồi mới exit.

### Exercise 5.3: Stateless design

- **Rate limit state:** Redis sorted set (không phải dict process-local).
- **Cost counter:** Redis `INCRBYFLOAT` atomic.
- **Session/history:** chưa implement nhưng pattern tương tự — `LPUSH history:<user_id>`.
- Lợi ích: scale `--replicas 3` thì request của user bất kỳ đập vào replica nào cũng thấy state đúng.

### Exercise 5.4: Load balancing

- Local: `docker compose up --scale agent=3` với nginx upstream round-robin → header `X-Served-By` hiện IP khác nhau (`172.19.0.3/4/5`) xác nhận traffic trải đều.
- Production (Railway): dùng Railway built-in proxy; scale bằng cách tăng `replicas` trong Settings (trả phí cho ≥2 replicas).

### Exercise 5.5: Test stateless

Local test với docker-compose (3 replicas + Redis):

| Check | Kết quả |
|-------|---------|
| `/health` qua nginx | 200 |
| LB round-robin 3 instance | `X-Served-By` thay đổi 3 IP khác nhau |
| Rate limit dùng chung bucket | Request user_id thứ 11 → 429 dù vào replica khác |
| Cost counter dùng chung | `budget:<user>:2026-04` tồn tại trong Redis |

→ Bất kỳ replica nào die đều không mất state (state sống trong Redis).

---

## Summary

| Part | Status | File(s) |
|------|--------|---------|
| 1. Localhost vs Production | ✅ | [01-localhost-vs-production/](01-localhost-vs-production/) |
| 2. Docker | ✅ | [02-docker/](02-docker/), [06-lab-complete/Dockerfile](06-lab-complete/Dockerfile) |
| 3. Cloud deployment | ✅ | Live Railway URL |
| 4. API security | ✅ | [06-lab-complete/app/auth.py](06-lab-complete/app/auth.py), [rate_limiter.py](06-lab-complete/app/rate_limiter.py), [cost_guard.py](06-lab-complete/app/cost_guard.py) |
| 5. Scaling & reliability | ✅ | [06-lab-complete/app/main.py](06-lab-complete/app/main.py), [nginx.conf](06-lab-complete/nginx.conf) |
| 6. Final project | ✅ | [06-lab-complete/](06-lab-complete/) — 20/20 check_production_ready passed |
