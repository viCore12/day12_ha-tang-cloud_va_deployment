# Day 12 Lab — Live Test Output

**URL:** `https://day12ha-tang-cloudvadeployment-production.up.railway.app`
**Run at:** 2026-04-17 08:24:07 UTC

---

## 1. Health check
```json
{
  "status": "ok",
  "version": "1.0.0",
  "environment": "production",
  "uptime_seconds": 1403.7,
  "total_requests": 67,
  "timestamp": "2026-04-17T08:24:08.308026+00:00"
}
```

## 2. Readiness probe
```json
{
  "ready": true
}
```

## 3. Ask (authenticated)
```json
{
  "user_id": "ss-demo2",
  "question": "Hello Railway!",
  "answer": "Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé.",
  "model": "gpt-4o-mini",
  "timestamp": "2026-04-17T08:24:09.678689+00:00"
}
```

## 4. Unauthorized (expect 401)
```
HTTP 401
```

## 5. Rate limit (12 requests, 10/min cap → 11th returns 429)
```
  req  1 → 200
  req  2 → 200
  req  3 → 200
  req  4 → 200
  req  5 → 200
  req  6 → 200
  req  7 → 200
  req  8 → 200
  req  9 → 200
  req 10 → 200
  req 11 → 429
  req 12 → 429
```

## 6. Metrics (per-user usage)
```json
{
  "uptime_seconds": 1414.2,
  "total_requests": 83,
  "error_count": 0,
  "inflight": 1,
  "usage": {
    "user_id": "ss-demo2",
    "month": "2026-04",
    "spent_usd": 0.0,
    "budget_usd": 10.0,
    "remaining_usd": 10.0,
    "used_pct": 0.0
  }
}
```
