# Day 12 — Deploy AI Agent to Production

> **AICB-P1 · VinUniversity 2026**
> **Student:** Lưu Lương Vi Nhân — Submission 2026-04-17

Lab về: `dev → production` gap, Docker, cloud deploy, API security, scaling & reliability.

**Live deployment:** https://day12ha-tang-cloudvadeployment-production.up.railway.app

---

## Deliverables

| File | Nội dung |
|------|---------|
| [MISSION_ANSWERS.md](MISSION_ANSWERS.md) | Trả lời 5 parts + test outputs |
| [DEPLOYMENT.md](DEPLOYMENT.md) | URL + env vars + test commands |
| [06-lab-complete/](06-lab-complete/) | Source code production-ready (Part 6) |
| [screenshots/](screenshots/) | Dashboard + deploy log + test output screenshots |

---

## Cấu trúc repo

```
.
├── 01-localhost-vs-production/   # Dev ≠ Production
├── 02-docker/                    # Containerization
├── 03-cloud-deployment/          # Railway / Render / Cloud Run examples
├── 04-api-gateway/               # Auth / Rate limit / Cost guard
├── 05-scaling-reliability/       # Health check / Stateless / LB
├── 06-lab-complete/              # ⭐ FINAL SUBMISSION: tất cả kết hợp
├── utils/mock_llm.py             # Mock LLM dùng chung
├── MISSION_ANSWERS.md
└── DEPLOYMENT.md
```

---

## Yêu cầu môi trường

```
python 3.11+
docker & docker compose
git
```

Không cần OpenAI API key — lab dùng mock LLM.

---

## Cách chạy

### Option 1 — Chạy local (không Docker)

```bash
cd 06-lab-complete
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# sửa AGENT_API_KEY, JWT_SECRET trong .env

# chạy app
cd ..
PYTHONPATH=. uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload \
  --app-dir 06-lab-complete
```

Rate limit và cost guard sẽ fallback in-memory (không cần Redis).

### Option 2 — Chạy Docker stack (khuyến nghị, demo scale + LB)

```bash
cd 06-lab-complete
cp .env.example .env
# sửa AGENT_API_KEY trong .env

docker compose up --scale agent=3 --build
```

Stack gồm:
- `nginx` (port `:80`) — load balancer round-robin
- `agent` x 3 replicas — FastAPI app (chỉ expose internal)
- `redis` — shared state (rate limit + cost counter)

### Option 3 — Dùng live deployment trên Railway

```bash
URL=https://day12ha-tang-cloudvadeployment-production.up.railway.app
KEY=<AGENT_API_KEY bạn set trên Railway Variables>
```

Xem [DEPLOYMENT.md](DEPLOYMENT.md) để biết cách tự deploy mới.

---

## Test commands

### Health + readiness
```bash
curl $URL/health
curl $URL/ready
```

### Authentication (401 → 200)
```bash
# Không key → 401
curl -X POST $URL/ask \
  -H "Content-Type: application/json" \
  -d '{"user_id":"test","question":"Hello"}'

# Có key → 200
curl -X POST $URL/ask \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"user_id":"test","question":"Hello"}'
```

### Rate limit (10/min per user → 11th request → 429)
```bash
for i in $(seq 1 12); do
  curl -s -o /dev/null -w "req $i → %{http_code}\n" \
    -X POST $URL/ask -H "X-API-Key: $KEY" \
    -H "Content-Type: application/json" \
    -d '{"user_id":"rl-demo","question":"ping"}'
done
```

### Metrics (per-user budget)
```bash
curl "$URL/metrics?user_id=test" -H "X-API-Key: $KEY"
```

### Load balancing test (local Docker stack only)
```bash
# Nginx thêm header X-Served-By cho biết instance nào xử lý
for i in {1..6}; do
  curl -sI http://localhost/health | grep -i x-served-by
done
```

---

## Verify production readiness

```bash
cd 06-lab-complete
python3 check_production_ready.py
```

Kết quả: **20/20 checks passed** ✅

---

## Learning Materials (course-provided)

| Tài liệu | Mô tả |
|---------|-------|
| [CODE_LAB.md](CODE_LAB.md) | Hướng dẫn lab chi tiết từng bước |
| [QUICK_START.md](QUICK_START.md) | Setup nhanh 5 phút |
| [QUICK_REFERENCE.md](QUICK_REFERENCE.md) | Cheat sheet |
| [TROUBLESHOOTING.md](TROUBLESHOOTING.md) | Xử lý lỗi thường gặp |
| [LEARNING_PATH.md](LEARNING_PATH.md) | Lộ trình học |

---

## Issues gặp phải trong quá trình deploy

Xem phần "Troubleshooting history" trong [DEPLOYMENT.md](DEPLOYMENT.md) — 3 lỗi thực tế đã fix:

1. Railway `startCommand` không shell-expand `$PORT` → app crash.
2. Docker `pip --user` path mismatch do user home sai vị trí.
3. Starlette `MutableHeaders` không có `.pop()` method.
