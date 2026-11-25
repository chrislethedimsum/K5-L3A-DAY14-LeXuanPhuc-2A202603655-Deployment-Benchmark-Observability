# Day 14 Lab - Mission Answers

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns found

Các anti-pattern tìm thấy trong `01-localhost-vs-production/develop/app.py` (đối chiếu với bản `01-localhost-vs-production/production/`):

1. **Hardcode secrets trong mã nguồn** (`develop/app.py`, dòng 17–18: `OPENAI_API_KEY = "sk-hardcoded-fake-key-never-do-this"`, `DATABASE_URL = "postgresql://admin:password123@localhost:5432/mydb"`) — Khi push lên Git sẽ lộ trực tiếp API key và mật khẩu database; không thể thay đổi hay rotate key theo từng môi trường mà không sửa code. Bản `production/config.py` (dòng 27, 32) chuyển sang đọc qua `os.getenv(...)`.
2. **Thiếu quản lý cấu hình tập trung và bật cứng chế độ debug** (`develop/app.py`, dòng 21–22: `DEBUG = True`, `MAX_TOKENS = 500`) — Cấu hình nằm rải rác trong code, muốn đổi thông số giữa dev/staging/prod phải sửa trực tiếp source code và dễ lộ thông tin debug ở production. Bản `production/config.py` (dòng 14–50) gom cấu hình vào dataclass `Settings` kèm `validate()` kiểm tra fail-fast.
3. **Dùng `print()` thay cho structured logging và log thẳng secret** (`develop/app.py`, dòng 33–34, 38: `print(f"[DEBUG] Using key: {OPENAI_API_KEY}")`) — Log dạng text tự do không có timestamp/level chuẩn JSON để công cụ thu thập log (Loki, Datadog...) phân tích, đồng thời in cả API key ra stdout gây rò rỉ thông tin nhạy cảm. Bản `production/app.py` (dòng 28–32, 111–122) dùng `logging` định dạng JSON và không log secrets.
4. **Không có health check và readiness endpoint** (`develop/app.py` chỉ có `/` và `/ask`) — Nền tảng cloud hoặc load balancer không kiểm tra được app còn sống hay đã sẵn sàng nhận request để tự động restart hoặc ngắt traffic khi gặp sự cố. Bản `production/app.py` (dòng 135–161) bổ sung `GET /health` và `GET /ready`.
5. **Cố định `host="localhost"`, `port=8000` và bật `reload=True`** (`develop/app.py`, dòng 51–53) — Bind `localhost` khiến bên ngoài container không kết nối được; hardcode `port=8000` không tương thích biến `PORT` do cloud platform (Railway/Render) cấp; `reload=True` gây tốn tài nguyên và không ổn định khi chạy production. Bản `production/app.py` (dòng 194–199) đọc `settings.host` (`0.0.0.0`), `settings.port` (từ `PORT`) và `settings.debug`.
6. **Không xử lý graceful shutdown (`SIGTERM` / `lifespan`)** (`develop/app.py`) — Khi container bị dừng hoặc redeploy, các request đang xử lý bị ngắt đột ngột và kết nối tài nguyên không được dọn dẹp an toàn. Bản `production/app.py` (dòng 39–68, 180–189) dùng `lifespan` và đăng ký `signal.signal(signal.SIGTERM, handle_sigterm)`.
7. **Nhận dữ liệu qua query parameter, thiếu validation và cấu hình CORS** (`develop/app.py`, dòng 30–31: `def ask_agent(question: str):`) — Dữ liệu câu hỏi nằm trên URL dễ bị lưu lại trong access log của proxy/browser và thiếu kiểm tra đầu vào/CORS rõ ràng. Bản `production/app.py` (dòng 77–82, 102–108) đọc JSON body, kiểm tra trường bắt buộc (trả `422` nếu rỗng) và cấu hình `CORSMiddleware`.

### Exercise 1.2: Chạy bản develop

- **Lệnh chạy server** (trong `01-localhost-vs-production/develop/`):
  ```bash
  ./path/to/venv/bin/python app.py
  ```
- **Lệnh kiểm thử & kết quả thực tế:**
  - `curl -i http://localhost:8000/` → `HTTP/1.1 200 OK`:
    ```json
    {"message":"Hello! Agent is running on my machine :)"}
    ```
  - `curl -i -X POST "http://localhost:8000/ask?question=Hello"` *(bản `develop` nhận `question` qua query param, không nhận JSON body)* → `HTTP/1.1 200 OK`:
    ```json
    {"answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé."}
    ```
  - `curl -i http://localhost:8000/health` → `HTTP/1.1 404 Not Found`:
    ```json
    {"detail":"Not Found"}
    ```
- **Quan sát từ terminal server & nhận xét:**
  - Server chạy được trên localhost (`Uvicorn running on http://localhost:8000`), nhưng **chưa production-ready**:
    1. Log bằng `print()` in thẳng secret ra terminal: `[DEBUG] Using key: sk-hardcoded-fake-key-never-do-this`.
    2. Không có `/health` (`404 Not Found`) để nền tảng theo dõi trạng thái sống/chết.
    3. Bind cố định `localhost:8000` kèm `reload=True` (bật reloader process `WatchFiles`).
    4. Nhận `question` qua query string thay vì JSON body.

### Exercise 1.3: Comparison table

| Feature                      | Develop (`01-localhost-vs-production/develop`)                                                                       | Production (`01-localhost-vs-production/production`)                                                                                                                                                                                                                                                                                          | Why Important?                                                                                                                                                                   |
| ---------------------------- | -------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Config & Secrets**         | Hardcode trực tiếp `OPENAI_API_KEY`, `DATABASE_URL`, `DEBUG = True`, `MAX_TOKENS = 500` trong `app.py` (dòng 17–22). | Đọc từ biến môi trường qua `os.getenv(...)` trong `config.py` (`Settings`), dùng `.env.example` làm mẫu (`.env` được `.gitignore`), kèm `validate()` fail-fast khi thiếu `AGENT_API_KEY` ở `production`.                                                                                                                                      | Tránh lộ secret khi push lên Git, dễ đổi cấu hình giữa dev/staging/prod mà không sửa code, và phát hiện thiếu cấu hình ngay lúc khởi động.                                       |
| **Health check & Readiness** | Không có `/health` hay `/ready` (`GET /health` trả `404 Not Found`).                                                 | Có `GET /health` (liveness probe trả `uptime_seconds`, `version`, `environment`, `timestamp`), `GET /ready` (readiness probe trả `503` khi `is_ready` là `False`) và `GET /metrics`.                                                                                                                                                          | Platform/orchestrator dùng `/health` để biết container còn sống mà restart, còn load balancer dùng `/ready` để tránh đẩy traffic vào instance chưa khởi động xong hoặc đang tắt. |
| **Logging**                  | Dùng `print()` dạng text tự do và in thẳng `OPENAI_API_KEY` ra stdout (`app.py` dòng 33–38).                         | Dùng `logging` với format JSON (`app.py` dòng 28–32, 111–122) ghi `event`, `question_length`, `client_ip`, `response_length` và tuyệt đối không log secret. _(Lưu ý quan sát khi chạy: do `config.py` gọi `logging.warning()` trước khi `app.py` gọi `logging.basicConfig()`, log `INFO` mặc định không in ra nếu chưa truyền `force=True`)._ | Log cấu trúc JSON dễ parse/lọc/cảnh báo trên Datadog, Loki, ELK; không log secret giúp tránh rò rỉ khóa bảo mật qua hệ thống log.                                                |
| **Shutdown**                 | Tắt đột ngột, không có `lifespan` hay xử lý tín hiệu dừng.                                                           | Có `@asynccontextmanager` `lifespan` (đặt `is_ready = False`, chờ request đang chạy) và đăng ký `signal.SIGTERM` (`app.py` dòng 39–68, 180–189).                                                                                                                                                                                              | Khi redeploy hoặc scale down, server hoàn thành các request in-flight trước khi thoát, tránh lỗi `502`/mất dữ liệu phía người dùng.                                              |
| **Host / Port / Reload**     | Cố định `host="localhost"`, `port=8000`, `reload=True` (`app.py` dòng 51–53).                                        | Đọc từ env (`HOST` mặc định `0.0.0.0`, `PORT` mặc định `8000`, `DEBUG` mặc định `false`).                                                                                                                                                                                                                                                     | `0.0.0.0` cho phép nhận traffic từ ngoài container; đọc `PORT` bắt buộc với PaaS (Railway/Render); tắt `reload` ở production để ổn định và tiết kiệm tài nguyên.                 |
| **Request Input & CORS**     | Nhận `question: str` qua query parameter (`POST /ask?question=...`), không kiểm tra rỗng, không cấu hình CORS.       | Nhận JSON body `{"question": "..."}`, validate rỗng trả `422`, cấu hình `CORSMiddleware` với `ALLOWED_ORIGINS`.                                                                                                                                                                                                                               | Tránh lộ dữ liệu câu hỏi trên URL/access log, chuẩn hóa API JSON, từ chối input sai sớm và kiểm soát domain frontend được phép gọi API.                                          |

- **Kết quả chạy & kiểm thử thực tế bản `production`** (đã copy `.env.example` → `.env`, chạy với `PORT=8001` để kiểm chứng đọc biến môi trường `PORT` khi cổng `8000` đang chạy bản `develop`):
  - Server khởi động tại `http://0.0.0.0:8001` (`WARNING:root:OPENAI_API_KEY not set — using mock LLM`).
  - `curl -i http://localhost:8001/health` → `HTTP/1.1 200 OK`:
    ```json
    {
      "status": "ok",
      "uptime_seconds": 0.4,
      "version": "1.0.0",
      "environment": "development",
      "timestamp": "2026-11-25T08:14:08.735499+00:00"
    }
    ```
  - `curl -i http://localhost:8001/ready` → `HTTP/1.1 200 OK`:
    ```json
    { "ready": true }
    ```
  - `curl -i http://localhost:8001/metrics` → `HTTP/1.1 200 OK`:
    ```json
    { "uptime_seconds": 0.4, "environment": "development", "version": "1.0.0" }
    ```
  - `curl -i -X POST http://localhost:8001/ask -H "Content-Type: application/json" -d '{"question": "Hello"}'` → `HTTP/1.1 200 OK`:
    ```json
    { "question": "Hello", "answer": "Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận.", "model": "gpt-4o-mini" }
    ```
  - Gửi `kill -TERM <PID>`: server thực hiện graceful shutdown qua uvicorn (`Shutting down` → `Waiting for application shutdown.` → `Application shutdown complete.`) và tự thoát hoàn toàn.

## Part 2: Docker

### Exercise 2.1: Dockerfile questions

1. **Base image:** `python:3.11` (`02-docker/develop/Dockerfile`, dòng 8) — là image Python 3.11 đầy đủ (full Debian-based, dung lượng lớn khoảng ~1 GB vì đi kèm sẵn nhiều gói/công cụ hệ thống không cần thiết lúc chạy app).
2. **Working directory:** `/app` (`WORKDIR /app`, dòng 11) — thư mục làm việc mặc định bên trong container; các lệnh `COPY`, `RUN`, `CMD` phía sau đều chạy tương đối tại `/app`.
3. **Tại sao `COPY requirements.txt` trước:** (`COPY 02-docker/develop/requirements.txt .` + `RUN pip install --no-cache-dir -r requirements.txt` ở dòng 14–17 đặt trước `COPY 02-docker/develop/app.py .` ở dòng 20) — để tận dụng **Docker layer cache**. Docker cache từng layer theo thứ tự; khi một layer thay đổi thì toàn bộ các layer phía sau bị invalidate và phải build lại. Vì `app.py` thay đổi thường xuyên hơn `requirements.txt`, việc cài dependencies trước giúp các lần rebuild khi sửa code tái sử dụng được cache của bước `pip install`, rút ngắn thời gian build (lưu ý `--no-cache-dir` chỉ tắt cache tải package của `pip` để giảm dung lượng image, không tắt Docker layer cache).
4. **Khác nhau giữa `CMD` và `ENTRYPOINT`:**
   - `CMD` (dòng 30: `CMD ["python", "app.py"]`) quy định lệnh chạy mặc định khi container khởi động và **có thể bị ghi đè dễ dàng** bằng đối số truyền sau tên image trong `docker run` (ví dụ `docker run <image> sh`).
   - `ENTRYPOINT` cố định tiến trình chính của container như một executable; các đối số truyền thêm trong `docker run` sẽ được **nối vào làm tham số** cho `ENTRYPOINT` (chỉ đổi được khi dùng cờ `--entrypoint`). Khi kết hợp cả hai, `ENTRYPOINT` giữ lệnh chính còn `CMD` cung cấp tham số mặc định.

### Exercise 2.2: Build và run container cơ bản

- **Lệnh build (từ gốc repo) và run container:**
  ```bash
  docker build -f 02-docker/develop/Dockerfile -t my-agent:develop .
  docker run -d -p 8000:8000 my-agent:develop
  ```
- **Kết quả kiểm thử thực tế với container `my-agent:develop`:**
  - `curl -i http://localhost:8000/health` → `HTTP/1.1 200 OK`:
    ```json
    {"status":"ok","uptime_seconds":1093.1,"container":true}
    ```
  - `curl -i -X POST "http://localhost:8000/ask?question=What%20is%20Docker%3F"` *(bản `02-docker/develop/app.py` nhận `question` qua query param)* → `HTTP/1.1 200 OK`:
    ```json
    {"answer":"Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!"}
    ```
- **Kích thước image đo được (`docker images my-agent:develop`):**
  - `my-agent:develop`: **`1.67GB`** (`1,672,153,402` bytes; content size `415MB`).
  - **Nhận xét:** Image chạy ổn định và nhất quán giữa các máy, nhưng dung lượng rất lớn (`1.67GB`) vì dùng base image `python:3.11` đầy đủ và build single-stage.

### Exercise 2.3: Image size comparison

- **Phân tích Multi-stage build (`02-docker/production/Dockerfile`):**
  1. **Stage 1 (`builder` — `FROM python:3.11-slim AS builder`, dòng 16–29):** cài các gói công cụ biên dịch (`gcc`, `libpq-dev`), xóa cache apt (`/var/lib/apt/lists/*`), copy `02-docker/production/requirements.txt` và cài Python dependencies bằng `pip install --no-cache-dir --user` vào `/root/.local`. Image trung gian này không dùng để deploy.
  2. **Stage 2 (`runtime` — `FROM python:3.11-slim AS runtime`, dòng 36–72):** tạo non-root user `appuser`, dùng `COPY --from=builder /root/.local /home/appuser/.local` để chỉ lấy các package đã cài, copy `main.py` và `utils/mock_llm.py`, đặt `chown`, chuyển sang `USER appuser`, cấu hình `ENV PATH`/`PYTHONPATH`, thêm `HEALTHCHECK` và `CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]`.
  3. **Tại sao image nhỏ hơn nhiều:**
     - Chuyển từ full base image `python:3.11` sang `python:3.11-slim`.
     - Loại bỏ toàn bộ trình biên dịch (`gcc`, `libpq-dev`, headers, build cache) ở Stage 1 ra khỏi final image — Stage 2 chỉ chứa Python runtime và thư viện cần để chạy app.

- **Số đo kích thước thực tế trên máy (`docker build` + `docker images`):**
  - Develop (`my-agent:develop`): `1672.15 MB` (`1.67GB` — `1,672,153,402` bytes)
  - Production (`my-agent:advanced`): `265.49 MB` (`265MB` — `265,493,227` bytes)
  - Difference: giảm `84.12%` (nhỏ hơn khoảng `6.3` lần)

  ```text
  $ docker images | grep my-agent
  my-agent:advanced                32628df1f13b        265MB         57.5MB
  my-agent:develop                 c0508d76dae7       1.67GB          415MB   U
  ```

### Exercise 2.4: Docker Compose stack

- **Sơ đồ kiến trúc (`02-docker/production/docker-compose.yml`):**

  ```text
  ┌──────────┐   HTTP :80 / :443   ┌──────────────────────────┐
  │  Client  │ ──────────────────► │  nginx (nginx:alpine)    │
  └──────────┘                     │  Reverse Proxy & Rate LB │
                                   └────────────┬─────────────┘
                                                │ proxy_pass http://agent:8000
                                                ▼
                                   ┌──────────────────────────┐
                                   │  agent (FastAPI, :8000)  │
                                   │  (không expose ra host)  │
                                   └──────┬───────────┬───────┘
                                          │           │
                 REDIS_URL=redis://redis:6379/0       │ QDRANT_URL=http://qdrant:6333
                                          ▼           ▼
                            ┌──────────────────┐ ┌──────────────────┐
                            │ redis:7-alpine   │ │ qdrant:v1.9.0    │
                            │ :6379            │ │ :6333 / :6334    │
                            │ vol: redis_data  │ │ vol: qdrant_data │
                            └──────────────────┘ └──────────────────┘
                 (Tất cả chạy trong Docker bridge network: internal)
  ```

- **Các service được start & cách giao tiếp:**
  1. `nginx` (`nginx:alpine`): mở cổng `80` và `443` ra host, kiểm tra security headers (`X-Frame-Options`, `X-Content-Type-Options`, `X-XSS-Protection`), áp rate limit `10r/s` (`burst=20`) và proxy request tới `agent:8000` (trừ `/health` không rate limit và tắt access log).
  2. `agent` (build từ `02-docker/production/Dockerfile`, `target: runtime`): không mở port trực tiếp ra host để tăng bảo mật, chỉ nhận traffic nội bộ từ `nginx`; chỉ khởi động sau khi `redis` và `qdrant` đều đạt trạng thái `service_healthy` (`depends_on`).
  3. `redis` (`redis:7-alpine`): cache session & rate limiting (`--maxmemory 256mb --maxmemory-policy allkeys-lru`), lưu dữ liệu bền vững qua volume `redis_data`.
  4. `qdrant` (`qdrant/qdrant:v1.9.0`): vector database phục vụ RAG trên cổng nội bộ `6333`, lưu dữ liệu bền vững qua volume `qdrant_data`.
  - **Cơ chế giao tiếp:** Toàn bộ 4 service nằm chung bridge network `internal`, gọi nhau bằng **service name qua Docker internal DNS** (`agent:8000`, `redis:6379`, `qdrant:6333`).

- **Kết quả chạy & test thực tế qua Nginx:**
  - Khởi động (từ gốc repo, sau khi `touch 02-docker/production/.env.local`):
    ```bash
    docker compose -p k5-day14-docker -f 02-docker/production/docker-compose.yml up -d --build
    docker compose -p k5-day14-docker -f 02-docker/production/docker-compose.yml ps
    ```
    Output `ps` ghi nhận đủ 4 container: `k5-day14-docker-nginx-1`, `k5-day14-docker-agent-1`, `k5-day14-docker-redis-1` (healthy), `k5-day14-docker-qdrant-1` (healthy).
  - `curl -i http://localhost/health` → `HTTP/1.1 200 OK` (qua `Server: nginx`, kèm các security header):
    ```json
    {"status":"ok","uptime_seconds":0.8,"version":"2.0.0","timestamp":"2026-11-25T08:51:47.600350"}
    ```
  - `curl -i -X POST http://localhost/ask -H "Content-Type: application/json" -d '{"question": "Explain microservices"}'` → `HTTP/1.1 200 OK` (`Server: nginx`):
    ```json
    {"answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận."}
    ```
  - Dọn dẹp sau khi test: `docker compose -p k5-day14-docker -f 02-docker/production/docker-compose.yml down`.

## Part 3: Cloud Deployment

### Exercise 3.2: Render deployment (Agent Part 6)

- **Nền tảng:** Render (Web Service Docker với `Root Directory: 06-lab-complete` + Render Key Value / Redis)
- **Public URL:** https://k5-l3a-day14-lexuanphuc-2a202603655.onrender.com
- **Biến môi trường đặt trên Render Dashboard** *(không ghi secret trong code)*: `ENVIRONMENT=production`, `REDIS_URL` (Internal Key Value URL), `AGENT_API_KEY` (đặt trực tiếp trên Dashboard), `RATE_LIMIT_PER_MINUTE=10`, `DAILY_BUDGET_USD=1.0` (`PORT` do Render tự động cấp).
- **Kết quả kiểm tra 4 lệnh CP6 (che key bằng `$AGENT_API_KEY`):**
  ```bash
  BASE="https://k5-l3a-day14-lexuanphuc-2a202603655.onrender.com"
  curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/health"                                                                                              # 200
  curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/ready"                                                                                               # 200
  curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" -H 'Content-Type: application/json' -d '{"question":"Hello"}'                           # 401
  curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" -H 'Content-Type: application/json' -H "X-API-Key: $AGENT_API_KEY" -d '{"question":"Hello"}'  # 200
  ```
  - `/health` → `200` (`{"status":"ok","environment":"production"}`)
  - `/ready` → `200` (`{"status":"ready"}`)
  - `POST /ask` (không có key) → `401` (`{"detail":"Invalid or missing API key"}`)
  - `POST /ask` (có `X-API-Key`) → `200` (`{"question":"Hello","answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận.","cost_usd":1.83e-05}`)
- **Screenshots:**
  - [Deployment dashboard](screenshots/dashboard.png)
  - [Service running](screenshots/running.png)
  - [Test results](screenshots/test.png)

### So sánh `railway.toml` và `render.yaml`

| Tiêu chí | `railway.toml` (`06-lab-complete/railway.toml`) | `render.yaml` (`06-lab-complete/render.yaml` / `03-cloud-deployment/render/render.yaml`) |
| --- | --- | --- |
| **Định dạng & vai trò** | TOML — cấu hình build/deploy cho **1 service đơn lẻ**. | YAML (Blueprint / IaC) — khai báo được **cả stack nhiều service** (Web Service + Redis/Key Value) trong cùng 1 file. |
| **Builder / Runtime** | Khai báo `[build] builder = "DOCKERFILE"` (hoặc `"NIXPACKS"`). | Khai báo `type: web`, `runtime: docker` (hoặc `runtime: python`), `dockerfilePath`, `rootDir`, `region`, `plan`. |
| **Health check** | `healthcheckPath = "/health"` dưới `[deploy]`, kèm `healthcheckTimeout`, `restartPolicyType`. | `healthCheckPath: /health` trong spec của web service. |
| **Biến môi trường & Secrets** | Không khai báo trực tiếp secret trong file; đặt qua Railway Dashboard hoặc `railway variables set` và nối Redis bằng reference `${{Redis.REDIS_URL}}`. | Hỗ trợ khai báo `envVars` ngay trong YAML nhưng với secret phải dùng `sync: false` (nhập tay trên Dashboard) hoặc `generateValue: true` (tự sinh random), và nối Redis bằng `fromService` (`type: keyvalue`, `property: connectionString`). |

- **Vì sao khác nhau:** Railway thiên về cấu hình gọn cho từng service riêng lẻ (phần database/env quản lý qua Dashboard/CLI), còn Render Blueprint dùng `render.yaml` theo hướng Infrastructure-as-Code để đồng bộ cả ứng dụng lẫn hạ tầng phụ thuộc (Redis, region, plan) từ một file Git duy nhất.

### Exercise 3.3: GCP Cloud Run CI/CD (`03-cloud-deployment/production-cloud-run/`)

- Pipeline CI/CD trong `cloudbuild.yaml` tự động kích hoạt khi push lên nhánh `main` và đi qua 4 bước tuần tự (`waitFor`):
  1. **Test (`python:3.11-slim`):** cài `requirements.txt` + `pytest` và chạy `pytest tests/ -v` để chặn build nếu test fail.
  2. **Build (`gcr.io/cloud-builders/docker`):** build Docker image gắn 2 tag (`$COMMIT_SHA` và `latest`) kèm `--cache-from` để tận dụng layer cache.
  3. **Push:** đẩy các tag image vừa build lên Google Container Registry (`gcr.io/$PROJECT_ID/ai-agent`).
  4. **Deploy (`gcloud run deploy`):** triển khai revision mới lên Cloud Run (`asia-southeast1`), cấu hình public (`--allow-unauthenticated`), autoscale (`min-instances=1`, `max-instances=10`), tài nguyên (`512Mi`, `1 CPU`) và nạp secret từ Secret Manager (`--set-secrets`). File `service.yaml` bổ sung đặc tả Knative/Cloud Run chi tiết cho `containerConcurrency: 80`, `livenessProbe` (`/health`) và `startupProbe` (`/ready`).

## Part 4: API Security

### Exercise 4.1: API Key authentication

- **Phân tích code (`04-api-gateway/develop/app.py`):**
  1. **API key được check ở đâu?**
     - Key kỳ vọng được đọc từ biến môi trường `AGENT_API_KEY` (dòng 35: `API_KEY = os.getenv("AGENT_API_KEY", "demo-key-change-in-production")`).
     - Header được khai báo bằng `APIKeyHeader(name="X-API-Key", auto_error=False)` (dòng 36) để tự kiểm soát mã lỗi trả về.
     - Logic kiểm tra nằm trong hàm dependency `verify_api_key` (dòng 39–54) và được gắn vào endpoint `POST /ask` qua `_key: str = Depends(verify_api_key)` (dòng 70); các endpoint public như `/` và `/health` không gắn dependency này.
  2. **Điều gì xảy ra nếu thiếu hoặc sai key?**
     - **Thiếu header `X-API-Key`** (`if not api_key:`, dòng 44–48): trả về **`HTTP 401 Unauthorized`** với detail `"Missing API key. Include header: X-API-Key: <your-key>"`.
     - **Có header nhưng sai key** (`if api_key != API_KEY:`, dòng 49–53): trả về **`HTTP 403 Forbidden`** với detail `"Invalid API key."`.
  3. **Làm sao rotate key?**
     - Với bản hiện tại (chỉ lưu 1 key đơn trong biến môi trường): đổi giá trị `AGENT_API_KEY` trên nền tảng deploy rồi restart service (có nhược điểm gây gián đoạn cho client chưa kịp đổi key).
     - Cách chuẩn không downtime (*zero-downtime rotation*): cho phép cấu hình danh sách nhiều key hợp lệ cùng lúc (ví dụ `AGENT_API_KEYS=old_key,new_key` hoặc lưu trong Secret Manager / DB và so sánh bằng `secrets.compare_digest`), phát hành key mới để client chuyển dần trong giai đoạn chuyển tiếp (*grace period*), kiểm tra log/metrics khi không còn request dùng key cũ rồi mới thu hồi (`revoke`) key cũ.

- **Kết quả chạy & test thực tế** (`AGENT_API_KEY=secret-key-123 python app.py`):
  1. **Không có key (`401 Unauthorized`):**
     ```http
     $ curl -i http://localhost:8000/ask -X POST -H "Content-Type: application/json" -d '{"question": "Hello"}'
     HTTP/1.1 401 Unauthorized
     date: Wed, 25 Nov 2026 09:00:56 GMT
     server: uvicorn
     content-length: 67
     content-type: application/json

     {"detail":"Missing API key. Include header: X-API-Key: <your-key>"}
     ```
  2. **Sai key (`403 Forbidden`):**
     ```http
     $ curl -i http://localhost:8000/ask -X POST -H "X-API-Key: wrong-key" -H "Content-Type: application/json" -d '{"question": "Hello"}'
     HTTP/1.1 403 Forbidden
     date: Wed, 25 Nov 2026 09:00:56 GMT
     server: uvicorn
     content-length: 29
     content-type: application/json

     {"detail":"Invalid API key."}
     ```
  3. **Có key hợp lệ (`200 OK`):**
     ```http
     $ curl -i http://localhost:8000/ask -X POST -H "X-API-Key: secret-key-123" -H "Content-Type: application/json" -d '{"question": "Hello"}'
     HTTP/1.1 200 OK
     date: Wed, 25 Nov 2026 09:00:56 GMT
     server: uvicorn
     content-length: 114
     content-type: application/json

     {"question":"Hello","answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé."}
     ```

### Exercise 4.2: JWT authentication

- **Phân tích JWT flow (`04-api-gateway/production/auth.py` & `app.py`):**
  1. **Đăng nhập & cấp token (`POST /auth/token`, `app.py` dòng 105–118):** gọi `authenticate_user(username, password)` kiểm tra thông tin trong `DEMO_USERS` (sai trả `401 Invalid credentials`), sau đó `create_token(username, role)` (`auth.py` dòng 35–43) ký JWT bằng thuật toán `HS256` với `SECRET_KEY` (`JWT_SECRET`), payload gồm `sub` (username), `role`, `iat` và `exp` (hết hạn sau 60 phút).
  2. **Xác thực stateless (`verify_token`, `auth.py` dòng 46–67):** dùng `HTTPBearer(auto_error=False)` đọc header `Authorization: Bearer <token>` và gọi `jwt.decode(...)` kiểm tra chữ ký & thời hạn mà không cần truy vấn database ở mỗi request:
     - Thiếu header `Authorization` → **`401 Unauthorized`** (kèm `WWW-Authenticate: Bearer`).
     - Token hết hạn (`jwt.ExpiredSignatureError`) → **`401 Unauthorized`**.
     - Token sai chữ ký / sai định dạng (`jwt.InvalidTokenError`) → **`403 Forbidden`**.
  3. **Phân quyền theo role (RBAC):** `app.py` lấy `user["role"]` từ payload JWT để chọn limiter (`rate_limiter_admin` vs `rate_limiter_user`, dòng 141) và chặn user thường truy cập `GET /admin/stats` (`403 Admin only`, dòng 171–175).

- **Kết quả kiểm thử thực tế (`curl -i`, token đã được che):**
  1. **Lấy token bằng `student` / `demo123` (`POST /auth/token` → `200 OK`):**
     ```http
     $ curl -i -X POST http://localhost:8000/auth/token \
       -H "Content-Type: application/json" \
       -d '{"username": "student", "password": "demo123"}'
     HTTP/1.1 200 OK
     date: Wed, 25 Nov 2026 09:07:11 GMT
     server: uvicorn
     content-length: 307
     content-type: application/json
     x-content-type-options: nosniff
     x-frame-options: DENY
     x-xss-protection: 1; mode=block
     referrer-policy: strict-origin-when-cross-origin

     {"access_token":"<JWT_TOKEN_MASKED>","token_type":"bearer","expires_in_minutes":60,"hint":"Include in header: Authorization: Bearer <JWT_PREFIX>..."}
     ```
  2. **Gọi `/ask` không có token (`401 Unauthorized`):**
     ```http
     $ curl -i -X POST http://localhost:8000/ask -H "Content-Type: application/json" -d '{"question": "Explain JWT"}'
     HTTP/1.1 401 Unauthorized
     date: Wed, 25 Nov 2026 09:07:11 GMT
     server: uvicorn
     www-authenticate: Bearer
     content-length: 76
     content-type: application/json
     x-content-type-options: nosniff
     x-frame-options: DENY
     x-xss-protection: 1; mode=block
     referrer-policy: strict-origin-when-cross-origin

     {"detail":"Authentication required. Include: Authorization: Bearer <token>"}
     ```
  3. **Gọi `/ask` với token sai (`403 Forbidden`):**
     ```http
     $ curl -i -X POST http://localhost:8000/ask -H "Authorization: Bearer invalid.token" -H "Content-Type: application/json" -d '{"question": "Explain JWT"}'
     HTTP/1.1 403 Forbidden
     date: Wed, 25 Nov 2026 09:07:11 GMT
     server: uvicorn
     content-length: 27
     content-type: application/json
     x-content-type-options: nosniff
     x-frame-options: DENY
     x-xss-protection: 1; mode=block
     referrer-policy: strict-origin-when-cross-origin

     {"detail":"Invalid token."}
     ```
  4. **Gọi `/ask` với JWT hợp lệ (`200 OK`):**
     ```http
     $ curl -i -X POST http://localhost:8000/ask \
       -H "Authorization: Bearer <JWT_TOKEN_MASKED>" \
       -H "Content-Type: application/json" \
       -d '{"question": "Explain JWT"}'
     HTTP/1.1 200 OK
     date: Wed, 25 Nov 2026 09:07:11 GMT
     server: uvicorn
     content-length: 184
     content-type: application/json
     x-content-type-options: nosniff
     x-frame-options: DENY
     x-xss-protection: 1; mode=block
     referrer-policy: strict-origin-when-cross-origin

     {"question":"Explain JWT","answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé.","usage":{"requests_remaining":9,"budget_remaining_usd":1.6e-05}}
     ```
  5. **Kiểm tra phân quyền `GET /admin/stats` với token `student` (`403 Forbidden`):**
     ```http
     $ curl -i http://localhost:8000/admin/stats -H "Authorization: Bearer <JWT_TOKEN_MASKED>"
     HTTP/1.1 403 Forbidden
     date: Wed, 25 Nov 2026 09:07:11 GMT
     server: uvicorn
     content-length: 23
     content-type: application/json
     x-content-type-options: nosniff
     x-frame-options: DENY
     x-xss-protection: 1; mode=block
     referrer-policy: strict-origin-when-cross-origin

     {"detail":"Admin only"}
     ```

### Exercise 4.3: Rate limiting

- **Phân tích code (`04-api-gateway/production/rate_limiter.py` & `app.py`):**
  1. **Algorithm nào được dùng?**
     - **Sliding Window** (docstring ghi *Sliding Window Counter*, cài đặt thực tế theo dạng *Sliding Window Log* dùng `deque` lưu timestamp từng request tại `self._windows[user_id]`, dòng 27).
     - Mỗi khi có request mới (`check()`, dòng 29–71), code xóa các timestamp cũ hơn `now - self.window_seconds` (`window.popleft()`, dòng 39–40) rồi kiểm tra `len(window) >= self.max_requests` (dòng 45).
  2. **Limit là bao nhiêu requests/minute?**
     - **User thường** (`student`, `rate_limiter_user`, dòng 86): **10 requests / 60 giây**.
     - **Admin** (`teacher`, `rate_limiter_admin`, dòng 87): **100 requests / 60 giây**.
  3. **Làm sao bypass / nâng limit cho admin?**
     - Hiện tại `app.py` (dòng 141) kiểm tra `role` lấy từ payload JWT để chọn limiter riêng: `limiter = rate_limiter_admin if role == "admin" else rate_limiter_user` (tức nâng limit cho admin lên 100 req/phút).
     - Nếu muốn **bypass hoàn toàn** rate limit cho admin, chỉ cần bỏ qua bước gọi `check()` khi `role == "admin"` (ví dụ: `if role != "admin": rate_info = rate_limiter_user.check(username)`).
  - **Lưu ý production:** `rate_limiter.py` hiện lưu `_windows` trong RAM (`defaultdict(deque)`), nên khi restart server hoặc chạy nhiều worker/instance state sẽ bị mất hoặc lệch giữa các instance — ở production (Part 6) cần lưu sliding window bằng **Redis** (`ZSET`).

- **Kết quả kiểm thử thực tế vòng lặp 20 requests** (dùng token của `student` / `demo123`, `10 req/min`):
  ```text
  Request  1: HTTP 200 | remaining=9
  Request  2: HTTP 200 | remaining=8
  Request  3: HTTP 200 | remaining=7
  Request  4: HTTP 200 | remaining=6
  Request  5: HTTP 200 | remaining=5
  Request  6: HTTP 200 | remaining=4
  Request  7: HTTP 200 | remaining=3
  Request  8: HTTP 200 | remaining=2
  Request  9: HTTP 200 | remaining=1
  Request 10: HTTP 200 | remaining=0
  Request 11: HTTP 429 | {'error': 'Rate limit exceeded', 'limit': 10, 'window_seconds': 60, 'retry_after_seconds': 59}
  Request 12: HTTP 429 | {'error': 'Rate limit exceeded', 'limit': 10, 'window_seconds': 60, 'retry_after_seconds': 59}
  Request 13: HTTP 429 | {'error': 'Rate limit exceeded', 'limit': 10, 'window_seconds': 60, 'retry_after_seconds': 59}
  Request 14: HTTP 429 | {'error': 'Rate limit exceeded', 'limit': 10, 'window_seconds': 60, 'retry_after_seconds': 59}
  Request 15: HTTP 429 | {'error': 'Rate limit exceeded', 'limit': 10, 'window_seconds': 60, 'retry_after_seconds': 59}
  Request 16: HTTP 429 | {'error': 'Rate limit exceeded', 'limit': 10, 'window_seconds': 60, 'retry_after_seconds': 59}
  Request 17: HTTP 429 | {'error': 'Rate limit exceeded', 'limit': 10, 'window_seconds': 60, 'retry_after_seconds': 59}
  Request 18: HTTP 429 | {'error': 'Rate limit exceeded', 'limit': 10, 'window_seconds': 60, 'retry_after_seconds': 59}
  Request 19: HTTP 429 | {'error': 'Rate limit exceeded', 'limit': 10, 'window_seconds': 60, 'retry_after_seconds': 59}
  Request 20: HTTP 429 | {'error': 'Rate limit exceeded', 'limit': 10, 'window_seconds': 60, 'retry_after_seconds': 58}
  ```

- **Chi tiết `curl -i` khi chạm ngưỡng limit (Request 11 → `429 Too Many Requests`, token đã che):**
  ```http
  $ curl -i -X POST http://localhost:8000/ask \
    -H "Authorization: Bearer <JWT_TOKEN_MASKED>" \
    -H "Content-Type: application/json" \
    -d '{"question": "Test 11"}'
  HTTP/1.1 429 Too Many Requests
  date: Wed, 25 Nov 2026 09:15:53 GMT
  server: uvicorn
  x-ratelimit-limit: 10
  x-ratelimit-remaining: 0
  x-ratelimit-reset: 1795598213
  retry-after: 59
  content-length: 98
  content-type: application/json
  x-content-type-options: nosniff
  x-frame-options: DENY
  x-xss-protection: 1; mode=block
  referrer-policy: strict-origin-when-cross-origin

  {"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":59}}
  ```

### Exercise 4.4: Cost guard implementation

- **Phân tích bản mẫu (`04-api-gateway/production/cost_guard.py`):**
  1. **Cách tính chi phí:** quy đổi số lượng token sang USD theo đơn giá (`PRICE_PER_1K_INPUT_TOKENS = 0.00015`, `PRICE_PER_1K_OUTPUT_TOKENS = 0.0006`, dòng 20–21; `UsageRecord.total_cost_usd` ở dòng 33–36).
  2. **Kiểm tra 2 tầng trước khi gọi LLM (`check_budget`, dòng 60–91):**
     - Vượt ngân sách toàn hệ thống (`global_daily_budget_usd = 10.0` USD/ngày) → trả **`HTTP 503 Service Unavailable`**.
     - Vượt ngân sách mỗi user (`daily_budget_usd = 1.0` USD/ngày) → trả **`HTTP 402 Payment Required`**.
     - Đạt `≥ 80%` ngân sách (`warn_at_pct = 0.8`) → ghi `logger.warning` cảnh báo sớm.
  3. **Ghi nhận usage (`record_usage`, dòng 93–110):** cộng dồn `input_tokens`, `output_tokens` sau khi LLM trả lời và tự tạo record mới khi sang ngày mới (`time.strftime("%Y-%m-%d")`).
  4. **Hạn chế của bản demo:** lưu `self._records` trong RAM nên dữ liệu bị mất khi restart và không đồng bộ khi scale nhiều worker/instance.

- **Thiết kế `check_budget(user_id, estimated_cost)` chuẩn production bằng Redis (ngân sách 10 USD/tháng/user):**
  - **Key theo tháng:** `budget:{user_id}:{YYYY-MM}` → sang tháng mới key tự đổi tên nên **tự động reset** ngân sách đầu tháng; đặt TTL `32 * 24 * 3600` giây để tự dọn key tháng cũ.
  - **Cơ chế cập nhật:** đọc chi phí hiện tại (`r.get(key)`), kiểm tra `current + estimated_cost > 10.0` → trả `False` (API trả `HTTP 402 Payment Required`), ngược lại cộng dồn bằng `r.incrbyfloat(key, estimated_cost)` và đặt `r.expire(key, ...)`. *(Trong hệ thống có nhiều request song song, có thể nâng cấp bằng Lua script hoặc `INCRBYFLOAT` trước rồi hoàn tác nếu vượt ngưỡng để tránh race condition).*
  ```python
  from datetime import datetime, timezone
  import redis

  r = redis.Redis(host="localhost", port=6379, db=0, decode_responses=True)
  MONTHLY_BUDGET_USD = 10.0

  def check_budget(user_id: str, estimated_cost: float) -> bool:
      month_key = datetime.now(timezone.utc).strftime("%Y-%m")
      key = f"budget:{user_id}:{month_key}"

      current = float(r.get(key) or 0.0)
      if current + estimated_cost > MONTHLY_BUDGET_USD:
          return False

      r.incrbyfloat(key, estimated_cost)
      r.expire(key, 32 * 24 * 3600)  # tự xóa sau 32 ngày
      return True
  ```

- **Vì sao cần cả Rate Limit lẫn Cost Guard?**
  - **Rate Limit (`429`) bảo vệ tốc độ / lưu lượng:** giới hạn số request trên phút để chống spam, brute-force và quá tải server, nhưng không chặn được việc user gửi các prompt cực dài (rất tốn token) hoặc gọi đều đặn dưới ngưỡng rate limit suốt cả tháng.
  - **Cost Guard (`402`) bảo vệ chi phí LLM:** giới hạn tổng tiền USD tiêu thụ theo ngày/tháng, nhưng không ngăn được burst traffic hàng trăm request/giây trước khi ngân sách chạm trần.
  - Kết hợp luồng `Auth (401) → Rate Limit (429) → Input Validation (422) → Cost Guard (402)` giúp bảo vệ toàn diện cả hạ tầng lẫn hóa đơn LLM.

## Part 5: Scaling & Reliability

### Exercise 5.1: Health checks (Liveness vs Readiness)

- **Phân biệt `/health` và `/ready` (`05-scaling-reliability/develop/app.py`):**
  1. **`GET /health` (Liveness probe, dòng 104–144):** trả lời câu hỏi *"process/container còn sống không?"*. Kiểm tra trạng thái nội bộ (uptime, memory via `psutil` nếu có) và trả `200 OK` khi app còn chạy bình thường — nếu timeout hoặc trả lỗi, platform/orchestrator sẽ **restart container**.
  2. **`GET /ready` (Readiness probe, dòng 147–168):** trả lời câu hỏi *"instance đã sẵn sàng nhận traffic chưa?"*. Trả `200 OK` kèm `in_flight_requests` khi `_is_ready == True`; trả **`503 Service Unavailable`** khi đang khởi động, đang shutdown (`_is_ready = False`), hoặc ở bản production khi mất kết nối Redis (`production/app.py` dòng 208–215) — load balancer dựa vào đây để **ngừng đẩy traffic mới vào** mà không vội kill container.
- **Kết quả kiểm thử thực tế (`curl -i`):**
  ```http
  $ curl -i http://localhost:8000/health
  HTTP/1.1 200 OK
  {"status":"ok","uptime_seconds":0.3,"version":"1.0.0","environment":"development","timestamp":"2026-11-25T09:32:46.315208+00:00","checks":{"memory":{"status":"ok","note":"psutil not installed"}}}

  $ curl -i http://localhost:8000/ready
  HTTP/1.1 200 OK
  {"ready":true,"in_flight_requests":1}
  ```

### Exercise 5.2: Graceful shutdown

- **Cơ chế hoạt động (`05-scaling-reliability/develop/app.py`):**
  - Middleware `track_requests` (dòng 72–81) đếm số request đang xử lý (`_in_flight_requests += 1` khi vào, `-= 1` trong `finally`).
  - Đăng ký `signal.signal(signal.SIGTERM, handle_sigterm)` (dòng 186) để ghi log và chạy `uvicorn.run(..., timeout_graceful_shutdown=30)` (dòng 198).
  - Khi nhận `SIGTERM`, `uvicorn` ngừng nhận request mới, đợi các request in-flight hoàn thành rồi mới kích hoạt phần shutdown của `lifespan` (`_is_ready = False`, vòng chờ `_in_flight_requests > 0` tối đa 30s ở dòng 54–66) và thoát sạch.
- **Kết quả kiểm thử thực tế** (gửi 2 request `POST /ask` song song rồi `kill -TERM <PID>` sau `0.2s`):
  - Cả 2 request đang chạy đều **hoàn thành và trả `HTTP 200`** (không bị cắt ngang):
    - `Req 1`: `{"answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận."} [HTTP 200]`
    - `Req 2`: `{"answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic."} [HTTP 200]`
  - Log server ghi nhận thứ tự chuẩn: `INFO: Shutting down` → hoàn tất 2 request `200 OK` → `Waiting for application shutdown.` → `🔄 Graceful shutdown initiated...` → `✅ Shutdown complete` → `Received signal 15 — uvicorn will handle graceful shutdown`.

### Exercise 5.3: Stateless design

- **Tại sao state trong RAM bị lỗi khi scale ngang?** Nếu lưu `conversation_history = {}` trong biến memory của process Python, mỗi container instance có vùng RAM riêng. Request lượt 1 của User A rơi vào `Instance 1` (lưu vào RAM của `Instance 1`), sang lượt 2 Nginx chuyển sang `Instance 2` thì `Instance 2` không thấy lịch sử hội thoại cũ → mất ngữ cảnh hoặc lỗi phiên làm việc.
- **Cách refactor trong `05-scaling-reliability/production/app.py`:**
  - Tách toàn bộ session & lịch sử hội thoại sang **Redis** (`REDIS_URL=redis://redis:6379/0`, dòng 37–40).
  - Hàm `save_session()` (dòng 59–63) lưu JSON dưới key `session:{session_id}` bằng `_redis.setex(..., 3600, serialized)` (TTL 1 giờ); `load_session()` đọc lại từ Redis; `append_to_history()` (dòng 76–90) cập nhật tối đa 20 messages (10 turns). Nhờ vậy bất kỳ instance nào cũng phục vụ được mọi user và vẫn giữ state khi restart.

### Exercise 5.4 & 5.5: Load balancing (Nginx + 3 instances) & Test stateless

- **Kiến trúc & cấu hình (`05-scaling-reliability/production/docker-compose.yml` & `nginx.conf`):**
  - Nginx lắng nghe cổng `8080` (`"8080:80"`), dùng Docker DNS `resolver 127.0.0.11 valid=10s` để phân giải tên service `agent:8000` (round-robin sang 3 replicas), gắn header `X-Served-By $upstream_addr` và cấu hình `proxy_next_upstream error timeout http_503` (tối đa 3 lần thử) để tự chuyển sang instance khác nếu 1 instance lỗi.
- **Kết quả `docker compose -p k5-day14-scaling ps`** (sau khi `touch .env.local` và chạy `docker compose -p k5-day14-scaling up -d --build --scale agent=3`):
  ```text
  NAME                       IMAGE                    COMMAND                  SERVICE   CREATED          STATUS                    PORTS
  k5-day14-scaling-agent-1   k5-day14-scaling-agent   "python -m uvicorn a…"   agent     22 seconds ago   Up 11 seconds (healthy)   8000/tcp
  k5-day14-scaling-agent-2   k5-day14-scaling-agent   "python -m uvicorn a…"   agent     22 seconds ago   Up 11 seconds (healthy)   8000/tcp
  k5-day14-scaling-agent-3   k5-day14-scaling-agent   "python -m uvicorn a…"   agent     22 seconds ago   Up 11 seconds (healthy)   8000/tcp
  k5-day14-scaling-nginx-1   nginx:alpine             "/docker-entrypoint.…"   nginx     22 seconds ago   Up 11 seconds             0.0.0.0:8080->80/tcp, [::]:8080->80/tcp
  k5-day14-scaling-redis-1   redis:7-alpine           "docker-entrypoint.s…"   redis     22 seconds ago   Up 22 seconds (healthy)   6379/tcp
  ```
- **Kết quả chạy `python3 test_stateless.py`** (5 requests trong cùng session `194455da-7090-4242-a7f4-629f4d7cd93a`):
  ```text
  Request 1: [instance-789420]
  Request 2: [instance-3af704]
  Request 3: [instance-789420]
  Request 4: [instance-0a2846]
  Request 5: [instance-3af704]

  Total requests: 5
  Instances used: {'instance-0a2846', 'instance-3af704', 'instance-789420'}
  ✅ All requests served despite different instances!

  --- Conversation History ---
  Total messages: 10
  ✅ Session history preserved across all instances via Redis!
  ```
  - **Giải thích:** 5 requests được Nginx phân tán đều qua cả **3 instances** (`instance-789420`, `instance-3af704`, `instance-0a2846`), nhưng khi đọc `/chat/{session_id}/history` vẫn còn đủ `10` messages (5 lượt user + 5 lượt assistant) vì toàn bộ lịch sử nằm tập trung trong Redis.
- **Kiểm chứng fault tolerance khi dừng 1 instance:**
  - Tạo session `b3326bd3-248a-42df-af67-c079564c6d66` (Turn 1 do `instance-0a2846` xử lý), chạy `docker stop k5-day14-scaling-agent-1`, rồi gửi Turn 2 với cùng `session_id`: hệ thống tự định tuyến sang `instance-3af704` (`"turn":3,"storage":"redis"`), và `GET /chat/b3326bd3-248a-42df-af67-c079564c6d66/history` trả về đủ `count: 4` messages không mất dữ liệu.
  - Dọn sạch stack sau khi test: `docker compose -p k5-day14-scaling down`.

## Part 6: Final Project — Production Readiness Check

Chạy `.venv/bin/python check_production_ready.py --public-url https://k5-l3a-day14-lexuanphuc-2a202603655.onrender.com` trong `06-lab-complete/` (chế độ đầy đủ có Docker):

```text
================================================================
  📋 Checklist Deliverable
     ✅ Dockerfile (multi-stage, < 500 MB)
     ✅ docker-compose.yml (agent + redis)
     ✅ .dockerignore
     ✅ Health check endpoint (GET /health)
     ✅ Readiness endpoint (GET /ready)
     ✅ API Key authentication
     ✅ Rate limiting
     ✅ Cost guard
     ✅ Config từ environment variables
     ✅ Structured logging
     ✅ Graceful shutdown
     ✅ Public URL ready (Railway / Render config)
----------------------------------------------------------------
  Result: 12/12 tiêu chí đạt · 44/44 checks passed
  🎉 PASS 12/12 — PRODUCTION READY! Deploy nào!
================================================================
```

*(Chi tiết đo được: Docker image `297 MB`, `docker stop` thoát `exit code 0` trong `0.4s`, `7 dòng JSON` log hợp lệ, rate limit giữ state qua Redis khi restart agent, `GET https://k5-l3a-day14-lexuanphuc-2a202603655.onrender.com/health → 200`.)*

---

## AI Log

| Thời điểm / Phần      | Đã hỏi AI gì                                                                                                                                                            | Nhận được gì                                                                                                                                                          | Tự kiểm tra & chỉnh sửa                                                                                                                          |
| --------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| Part 1 — Exercise 1.1 | Nhờ hỗ trợ phân tích các anti-pattern trong `01-localhost-vs-production/develop/app.py` và đối chiếu với bản `production/`.                                             | Danh sách 7 anti-pattern kèm vị trí dòng code và cách bản `production` khắc phục.                                                                                     | Tự đọc lại code `develop/app.py` và `production/app.py` để xác nhận đúng số dòng và nội dung trước khi lưu vào `MISSION_ANSWERS.md`.             |
| Part 1 — Exercise 1.2 | Nhờ chạy thử `01-localhost-vs-production/develop/app.py`, kiểm thử endpoint `/`, `/ask`, `/health` và ghi nhận xét vào `MISSION_ANSWERS.md`. | Chạy thực tế qua venv, thu output `curl -i` (`200` cho `/` và `/ask?question=Hello`, `404` cho `/health`) và log terminal in ra key. | Tự đối chiếu output HTTP và log server trước khi lưu vào `MISSION_ANSWERS.md`. |
| Part 1 — Exercise 1.3 | Nhờ chạy thử `01-localhost-vs-production/production/app.py`, kiểm thử `/health`, `/ready`, `/metrics`, `/ask`, `SIGTERM` và điền bảng so sánh vào `MISSION_ANSWERS.md`. | Output thực tế trên `0.0.0.0:8001` (HTTP 200 cho cả 4 endpoint, thoát sạch khi nhận `SIGTERM`) và bảng so sánh 6 tiêu chí Develop vs Production.                      | Tự kiểm chứng bằng `curl -i`, phát hiện thêm hành vi `logging.warning` trước `basicConfig` trong code và xác nhận `.env` không bị track bởi Git. |
| Part 2 — Exercise 2.1 | Nhờ hỗ trợ phân tích và trả lời 4 câu hỏi về `02-docker/develop/Dockerfile`.                                                                                            | 4 câu trả lời chi tiết về base image `python:3.11`, `WORKDIR /app`, Docker layer cache khi copy `requirements.txt` trước và sự khác nhau giữa `CMD` với `ENTRYPOINT`. | Tự đọc lại `02-docker/develop/Dockerfile` và `02-docker/README.md` để đối chiếu số dòng và nội dung trước khi lưu vào `MISSION_ANSWERS.md`.      |
| Part 2 — Exercise 2.2 | Nhờ kiểm thử container `my-agent:develop` và ghi kích thước cùng kết quả test vào `MISSION_ANSWERS.md`. | Kết quả `curl -i` cho `/health` (`200`), `/ask?question=What%20is%20Docker%3F` (`200`) và dung lượng `1.67GB`. | Tự kiểm tra trực tiếp container đang chạy trên cổng `8000` và `docker images my-agent:develop`. |
| Part 2 — Exercise 2.3 | Nhờ chạy build `02-docker/production/Dockerfile` (`my-agent:advanced`), đo kích thước so với `my-agent:develop` và giải thích multi-stage build trong `MISSION_ANSWERS.md`. | Kết quả đo thực tế (`1.67GB` vs `265MB`, giảm `84.12%`) và phân tích vai trò Stage 1 (`builder`) / Stage 2 (`runtime`). | Tự chạy `docker build`, `docker images \| grep my-agent` và `docker image inspect` trên máy để kiểm chứng số byte chính xác trước khi lưu vào `MISSION_ANSWERS.md`. |
| Part 2 — Exercise 2.4 | Nhờ bật stack `02-docker/production/docker-compose.yml`, vẽ sơ đồ kiến trúc, giải thích giao tiếp giữa các service và test qua Nginx. | Sơ đồ 4 service (`nginx`, `agent`, `redis`, `qdrant`), kết quả `docker compose ps` và output `curl -i` qua `http://localhost/health` và `/ask`. | Tự kiểm tra `docker-compose.yml`, `nginx.conf`, chạy stack với `-p k5-day14-docker`, test HTTP `200` qua Nginx và `down` stack gọn gàng. |
| Part 4 — Exercise 4.1 | Nhờ phân tích `04-api-gateway/develop/app.py` (nơi kiểm tra API key, hành vi sai key, cách rotate key), chạy test và ghi kết quả vào `MISSION_ANSWERS.md`. | Câu trả lời 3 câu hỏi đọc code (`APIKeyHeader`, `verify_api_key`, `401`/`403`, zero-downtime rotation) và output `curl -i` thực tế cho 3 trường hợp (`401`, `403`, `200`). | Tự dừng container cũ, chạy server với `AGENT_API_KEY=secret-key-123`, test đủ 3 lệnh `curl -i` và tắt server trả lại cổng `8000`. |
| Part 4 — Exercise 4.2 | Nhờ cài `pyjwt`, phân tích luồng JWT trong `04-api-gateway/production/auth.py` và kiểm thử `/auth/token`, `/ask`, `/admin/stats`. | Giải thích luồng `HS256` stateless + RBAC và output `curl -i` thực tế cho 5 trường hợp (`200` login, `401` thiếu token, `403` token sai, `200` `/ask`, `403` `/admin/stats`), đã che JWT token. | Tự kiểm chứng luồng đăng nhập `student`/`demo123`, kiểm tra không để lộ JWT thật trong `MISSION_ANSWERS.md` và giải phóng cổng `8000`. |
| Part 4 — Exercise 4.3 | Nhờ phân tích `04-api-gateway/production/rate_limiter.py`, chạy vòng lặp 20 requests với token `student` và ghi kết quả vào `MISSION_ANSWERS.md`. | Giải thích thuật toán Sliding Window, ngưỡng `10` vs `100` req/phút, cách bypass cho admin, cùng log 20 requests (`1..10` đạt `200`, `11..20` bị `429`) và full header `429`. | Tự chạy vòng lặp 20 lần trên máy, kiểm tra header `X-RateLimit-*` / `Retry-After` và đảm bảo che token + giải phóng cổng `8000`. |
| Part 4 — Exercise 4.4 | Nhờ phân tích `04-api-gateway/production/cost_guard.py`, thiết kế hàm `check_budget` dùng Redis (10 USD/tháng) và giải thích vai trò kết hợp Rate Limit + Cost Guard. | Phân tích cơ chế check global/user budget (`503`/`402`), đoạn code Redis `budget:{user_id}:{YYYY-MM}` dùng `INCRBYFLOAT` + TTL 32 ngày và so sánh Rate Limit vs Cost Guard. | Tự đối chiếu logic với `cost_guard.py` (dòng 20–110) và `CODE_LAB.md` Exercise 4.4 trước khi lưu vào `MISSION_ANSWERS.md`. |
| Part 5 — Exercise 5.1–5.5 | Nhờ kiểm thử `05-scaling-reliability/develop/app.py` (health, ready, SIGTERM) và chạy stack 3 instances `05-scaling-reliability/production` (`test_stateless.py` + `docker stop` 1 instance). | Kết quả thực tế `/health` & `/ready`, 2 request song song vẫn trả `200` khi nhận `SIGTERM`, output `test_stateless.py` qua 3 instances (`10` messages) và fault tolerance khi tắt `agent-1`. | Tự chạy lệnh `docker compose -p k5-day14-scaling ...`, `python3 test_stateless.py`, kiểm tra history sau khi dừng 1 container rồi `down` stack trả cổng `8080`. |
| Part 6 — Final Project | Nhờ hướng dẫn hoàn thiện 11 file khung trong `06-lab-complete/` (tạo `render.yaml`, dọn `main.py`) và chạy `check_production_ready.py`. | Mẫu cấu hình chuẩn 12-Factor, Redis sliding-window rate limit, cost guard, JSON logging, multi-stage Dockerfile (`exec uvicorn`) và file `render.yaml`. | Tự cấu hình các file trong `06-lab-complete/`, chạy bản đầy đủ `check_production_ready.py` đạt `PASS 12/12 (44/44 checks passed)` và dán kết quả vào `MISSION_ANSWERS.md`. |
| Part 3 — Cloud Deployment | Nhờ kiểm tra URL Render live, tạo `DEPLOYMENT.md`, so sánh `railway.toml` vs `render.yaml` và tóm tắt pipeline Cloud Run (`Exercise 3.3`). | Output thực tế 4 lệnh CP6 (`200`, `200`, `401`, `200`), bảng so sánh 2 file config và mô tả 4 bước `cloudbuild.yaml` + `service.yaml`. | Tự deploy Web Service & Key Value lên Render, kiểm chứng lại qua `--public-url` và xác nhận không commit `AGENT_API_KEY` thật vào repo. |
| Part 7 — Benchmark local (CP7) | Nhờ thêm metric `agent_question_length_chars` (`develop/app.py`), chạy load test & eval v1/v2, sửa `KNOWLEDGE_BASE`, tạo CI workflow và điền mục 1–3 của `BENCHMARK_REPORT.md`. | Đủ 10 file JSON trong `reports/` (`eval_v2_fixed.json` đạt `100.0%` `23/23`), file `.github/workflows/eval.yml` và số liệu phần 1–3 trong `BENCHMARK_REPORT.md`. | Tự chạy toàn bộ `load_test.py` và `run_eval.py` trên máy, đối chiếu từng con số trong `BENCHMARK_REPORT.md` khớp 100% file JSON đã lưu. |
| Part 7 — Observability stack (CP8) | Nhờ sửa `PYTHONUSERBASE` trong `production/Dockerfile`, chạy stack `k5-day14-observability` (Locust `scale=1` vs `scale=3`, Jaeger trace, `promtool`, 4 thí nghiệm alert), chụp 4 ảnh và điền mục 4–6 của `BENCHMARK_REPORT.md`. | CSV `scale_1_stats.csv` & `scale_3_stats.csv` trong `benchmark-results/`, 4 ảnh PNG trong `screenshots/`, `trace_id` khớp JSON log, thời gian 4 alert firing thực tế và phân tích hoàn chỉnh mục 4–6. | Tự kiểm tra từng ảnh PNG bằng mắt, đối chiếu mọi con số trong `BENCHMARK_REPORT.md` khớp CSV/log/Prometheus, sau đó `docker compose -p k5-day14-observability down -v` và kiểm tra sạch `.env`/secret. |
