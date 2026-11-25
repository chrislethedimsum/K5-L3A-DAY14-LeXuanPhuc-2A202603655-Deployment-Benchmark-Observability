# Deployment Information

## Public URL
https://k5-l3a-day14-lexuanphuc-2a202603655.onrender.com

## Platform
Render (Web Service Docker với Root Directory `06-lab-complete` + Render Key Value / Redis)

## Test Commands

### 1. Health Check (Liveness — 200)
```bash
curl -sS -o /dev/null -w '%{http_code}\n' "https://k5-l3a-day14-lexuanphuc-2a202603655.onrender.com/health"
# Expected: 200
# Body: {"status":"ok","environment":"production"}
```

### 2. Readiness Check (Redis Connected — 200)
```bash
curl -sS -o /dev/null -w '%{http_code}\n' "https://k5-l3a-day14-lexuanphuc-2a202603655.onrender.com/ready"
# Expected: 200
# Body: {"status":"ready"}
```

### 3. API Test (Without API Key — 401)
```bash
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "https://k5-l3a-day14-lexuanphuc-2a202603655.onrender.com/ask" \
  -H 'Content-Type: application/json' \
  -d '{"question":"Hello"}'
# Expected: 401
# Body: {"detail":"Invalid or missing API key"}
```

### 4. API Test (With API Key — 200)
```bash
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "https://k5-l3a-day14-lexuanphuc-2a202603655.onrender.com/ask" \
  -H 'Content-Type: application/json' \
  -H "X-API-Key: $AGENT_API_KEY" \
  -d '{"question":"Hello"}'
# Expected: 200
# Body: {"question":"Hello","answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận.","cost_usd":1.83e-05}
```

## Environment Variables Set
- `PORT` (do Render tự động cấp cho container)
- `ENVIRONMENT` (`production`)
- `REDIS_URL` (Internal Key Value / Redis URL trên Render)
- `AGENT_API_KEY` (đặt trực tiếp trên Render Dashboard, không commit vào code)
- `RATE_LIMIT_PER_MINUTE` (`10`)
- `DAILY_BUDGET_USD` (`1.0`)

## Screenshots
- [Deployment dashboard](screenshots/dashboard.png)
- [Service running](screenshots/running.png)
- [Test results](screenshots/test.png)
