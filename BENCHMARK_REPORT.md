# Benchmark & Observability Report — Day 14

> Copy file này thành `BENCHMARK_REPORT.md` trong repo của bạn và điền đầy đủ.
> Mọi con số phải lấy từ report JSON / CSV / screenshot thật, không ước lượng.

**Họ tên:** Le Xuan Phuc — 2A202603655
**Ngày chạy:** 2026-11-25
**Môi trường:** Apple M4 Pro (24GB RAM), Docker Desktop (14 CPU / 8GB RAM)

---

## 1. SLO của agent

| SLI | SLO | Lý do chọn ngưỡng này |
|---|---|---|
| p95 latency `/ask` | `< 500 ms` | Đảm bảo 95% người dùng nhận phản hồi dưới 0.5 giây (trải nghiệm chat mượt), cao hơn mức latency nền (~180–230ms) để dung nạp dao động nhẹ nhưng đủ chặt để phát hiện suy giảm hiệu năng. |
| Error rate `/ask` | `< 2.0 %` | Error budget 2% vừa cho phép tỷ lệ lỗi upstream ngẫu nhiên (~1% trong mock LLM) vừa cảnh báo kịp thời nếu tỷ lệ lỗi hệ thống tăng bất thường. |
| Accuracy trên golden dataset | `≥ 85 %` | Đảm bảo chất lượng RAG đạt mức tin cậy tối thiểu trước khi merge/deploy (với bản hoàn chỉnh sau khi bổ sung KB kỳ vọng đạt 100% và 0 regression). |

---

## 2. Benchmark hiệu năng (develop, `load_test.py`)

### 2.1 Concurrency vs latency (agent v2)

| Concurrency | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Error rate | SLO |
|---|---|---|---|---|---|---|
| 1 | 3.89 | 193.2 | 225.7 | 1706.6 | 0.00% | PASS |
| 10 | 44.42 | 188.7 | 218.1 | 1699.0 | 1.00% | PASS |
| 50 | 107.30 | 190.2 | 236.8 | 1705.9 | 2.33% | FAIL (error rate 2.33% > 2.0%) |
| 100 | 77.78 | 297.4 | 2723.3 | 3075.3 | 2.33% | FAIL (p95 2723.3ms > 500ms, error 2.33% > 2.0%) |

**Nhận xét:** RPS có tăng tuyến tính theo concurrency không? Vì sao?

Không. Từ `concurrency=1` (3.89 req/s) lên `10` (44.42 req/s) và `50` (107.3 req/s), RPS tăng mạnh nhờ FastAPI async xử lý song song nhiều tác vụ chờ I/O (`asyncio.sleep` mô phỏng retrieval & LLM). Tuy nhiên tới `concurrency=100`, RPS **giảm xuống 77.78 req/s** và p95 vọt lên `2723.3 ms` vì single-process `uvicorn` bị bão hòa event loop / hàng đợi kết nối và chịu ảnh hưởng cộng dồn của các request chậm (`tail latency`), làm thời gian chờ mỗi request kéo dài.

### 2.2 Tail latency

| `MOCK_SLOW_RATE` | avg (ms) | p95 (ms) | p99 (ms) |
|---|---|---|---|
| 0 | 187.7 | 217.0 | 221.9 |
| 0.03 (mặc định) | 265.0 | 456.8 | 1704.2 |
| 0.1 | 312.3 | 1686.9 | 1704.6 |

**Nhận xét:** Chỉ số nào nhạy nhất với request chậm? Vì sao SLO không nên đặt theo average?

**p99** (và **p95** khi tỷ lệ slow ≥ 5–10%) nhạy nhất với request chậm: chỉ với 3% request chậm (`MOCK_SLOW_RATE=0.03`), `avg` chỉ tăng nhẹ từ `187.7 ms` lên `265.0 ms`, nhưng `p99` nhảy vọt gần **8 lần** từ `221.9 ms` lên `1704.2 ms`. Khi lên 10% (`0.1`), `p95` cũng vọt từ `456.8 ms` lên `1686.9 ms` và đánh rớt SLO. Nếu đặt SLO theo `average`, phần lớn request nhanh sẽ "kéo trung bình xuống" và che lấp trải nghiệm tệ hại của nhóm người dùng gặp tail latency.

---

## 3. Benchmark chất lượng (develop, `eval/run_eval.py`)

| Chỉ số | Agent v1 | Agent v2 | Agent v2 (sau khi sửa KB) |
|---|---|---|---|
| Accuracy | 4.3% (1/23) | 91.3% (21/23) | 100.0% (23/23) |
| Avg tokens / câu | 56.8 | 108.7 | 113.7 |
| Tổng cost (USD) | $0.000400 | $0.000756 | $0.000790 |
| Cost / câu đúng (USD) | $0.00039975 | $0.00003599 | $0.00003436 |
| Quality gate | FAIL | PASS (baseline v1, min 80%) | PASS (baseline v2, min 100%) |

**Những câu v2 trả lời sai ban đầu và cách bạn sửa:**

| ID | Keyword bị thiếu | Bạn đã sửa gì |
|---|---|---|
| `security-02` | `token`, `hết hạn`, `chữ ký` | Thêm entry vào `KNOWLEDGE_BASE` trong `utils/mock_llm.py` với từ khóa `["jwt"]` giải thích JWT chứa thông tin user, chữ ký số và thời điểm hết hạn. |
| `scaling-03` | `cpu`, `memory`, `custom metrics` | Thêm entry vào `KNOWLEDGE_BASE` trong `utils/mock_llm.py` với từ khóa `["hpa", "kubernetes", "autoscal"]` mô tả Kubernetes HPA scale theo CPU, memory hoặc custom metrics. |

**Nhận xét về trade-off chất lượng / chi phí / latency giữa v1 và v2:**

- **Chất lượng:** v2 (có retrieval RAG) tăng độ chính xác vượt trội từ `4.3%` lên `91.3%` và `100.0%` sau khi bổ sung KB.
- **Chi phí & Token:** v2 đưa thêm context vào prompt nên `avg tokens/câu` tăng gần gấp đôi (`108.7`–`113.7` so với `56.8`) và tổng chi phí tăng gần gấp đôi (`$0.000790` vs `$0.000400`). Tuy nhiên xét trên **cost / câu đúng**, v2 (`$0.00003436`) **rẻ hơn ~11.6 lần** so với v1 (`$0.00039975`) vì v1 trả lời sai 22/23 câu nên hầu hết chi phí bị lãng phí.
- **Latency:** v2 thêm bước retrieval (~20ms) nên chậm hơn nhẹ khi bình thường (`p95` eval tăng từ `189.0 ms` lên `223.0 ms`), đây là đánh đổi rất xứng đáng cho chất lượng câu trả lời. *(Lưu ý: `p95 = 1527.4 ms` ở lần chạy `eval_v2_fixed` là do 2/23 câu dính `MOCK_SLOW_RATE=0.03` trên mẫu nhỏ 23 câu, không phải do sửa KB).*
- **CI Quality Gate (`.github/workflows/eval.yml`):** `run_eval.py` trả exit code `0` khi đạt ngưỡng `--min-accuracy` và không có regression so với `--baseline`, ngược lại trả exit code `1` (đã kiểm chứng thực tế khi chạy `v1` với `--baseline reports/eval_v2.json` nhận `exit code = 1`). Khi gắn lệnh này vào GitHub Actions trên `pull_request` (`.github/workflows/eval.yml`), mọi PR làm giảm accuracy dưới 85% hoặc gây regression sẽ làm job fail và tự động chặn merge.

---

## 4. Observability stack (production)

### 4.1 Screenshot & câu hỏi Exercise 7.4

- [x] Dashboard Grafana khi đang có tải (thấy rõ Golden Signals): [grafana-dashboard.png](screenshots/grafana-dashboard.png)
- [x] Một trace chậm trong Jaeger (thấy span nào chiếm thời gian): [jaeger-slow-trace.png](screenshots/jaeger-slow-trace.png)
- [x] Một trace lỗi trong Jaeger (có event `exception`): [jaeger-error-trace.png](screenshots/jaeger-error-trace.png)
- [x] Trang Alerts của Prometheus với ít nhất 1 alert đang **firing** (cả 4 alert cùng firing): [prometheus-alert-firing.png](screenshots/prometheus-alert-firing.png)

**Trả lời Exercise 7.4 (quan sát từ Prometheus & Grafana khi có tải):**
1. **p95 và avg:** Trên Prometheus (`[2m]`), `p95 = 293.39 ms` (`293.86 ms` trên Grafana panel), `avg = 232.37 ms`. Khoảng cách (~61 ms) cho thấy phần lớn request hoàn thành quanh ~190 ms, còn một phần nhỏ request chậm (`~1.7 s`) kéo cả avg lẫn p95 lên (và đẩy p99 lên `1.7 s`).
2. **Requests/s theo instance:** Nginx phân phối traffic **rất đều** theo round-robin giữa các instance (`172.19.0.4:8000` đạt `30.21 req/s`, `172.19.0.8:8000` đạt `30.38 req/s`).
3. **Vì sao `input tokens/s` > `output tokens/s`:** Prometheus đo `input = 4648.37 tokens/s`, `output = 2429.84 tokens/s` (gần gấp đôi) vì agent `v2` (RAG) đưa thêm `SYSTEM_PROMPT` và tài liệu retrieve từ `KNOWLEDGE_BASE` vào prompt đầu vào (`~83` input tokens vs `~44` output tokens mỗi request).
4. **`curl -i http://localhost:8080/metrics`:** Trả về **`404 Not Found`** từ `nginx/1.28.3`, vì `nginx.conf` chủ động chặn `location = /metrics { return 404; }` để không lộ thông tin nội bộ (routes, lưu lượng, instance) ra ngoài; Prometheus nằm trong Docker network `obs_net` nên scrape trực tiếp `agent:8000/metrics`.

### 4.2 Thí nghiệm "phá hệ thống"

- **Unit test alert rules (`promtool test rules /p/alert_rules_test.yml`):** `SUCCESS`.

| # | Thay đổi | Alert nào firing | Thời gian từ lúc đổi → firing | Panel nào phản ánh rõ nhất |
|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.2` | `AgentHighErrorRate` (`for: 1m`) | `80.1 s` (`pending` ở `20.0 s`) | `Error rate` & `Requests/s theo status code` (`503`) |
| B | `MOCK_SLOW_RATE=0.3` | `AgentHighLatencyP95` (`for: 2m`) | `140.2 s` (`pending` ở `20.0 s`) | `Latency p95` & `Latency /ask — p50 / p95 / p99` |
| C | `LLM_MODEL=mock-llm-large` | `LLMCostBurnRateHigh` (`for: 2m`) | `140.2 s` (`pending` ở `20.0 s`) | `Cost burn rate (USD/giờ)` & `LLM cost (1h)` |
| D | `docker pause` 1 instance | `AgentInstanceDown` (`for: 30s`) | `45.1 s` sau khi pause (`pending` sau `15.1 s`) | `Instances up` & `Requests/s theo instance` |
| E | `AGENT_VERSION=v1` | Không có alert nào firing | Không firing | `Retrieval hit ratio` giảm/mất, `Tokens/s` giảm, bảng version chuyển `v1` |

**Thí nghiệm E không làm alert nào firing. Bạn sẽ phát hiện loại sự cố này trong production bằng cách nào?**

Alert hạ tầng chỉ nhìn thấy HTTP status, latency, CPU/RAM hay cost, nên không biết câu trả lời đúng hay sai về mặt ngữ nghĩa. Trong production cần kết hợp:
1. Chạy **offline eval trên golden dataset** (`eval/run_eval.py`) như quality gate trong CI/CD trước khi deploy.
2. Chạy **online eval** (lấy mẫu một tỷ lệ traffic thật chấm tự động bằng LLM-as-judge hoặc đối chiếu grounding).
3. Theo dõi các **proxy metric chất lượng** trên dashboard (`retrieval hit ratio`, `agent_info{version=...}`) và **tín hiệu từ người dùng** (thumbs up/down, tỷ lệ hỏi lại ngay sau đó).

### 4.3 Debug bằng trace

Chọn 1 trace chậm nhất tìm được trong Jaeger (`service=observable-agent`):

- `trace_id` (slow trace): `79e685bb6f49cb3fb08c8585c8392c90`
- Tổng thời gian (`POST /ask`): `1725.64 ms` (`1.7s` hiển thị trên Jaeger UI; `agent.run`: `1722.84 ms`, `agent.retrieve_context`: `24.41 ms`)
- Span chiếm nhiều thời gian nhất: `chat mock-llm-small` (`1698.22 ms`, chiếm `98.4%` tổng thời gian — do mock LLM dính tail latency)
- Dòng log tương ứng (grep theo `trace_id`):

```json
{"ts": "2026-11-25T10:36:27.689976+00:00", "level": "INFO", "service": "observable-agent", "instance": "b487ed0cc6cf", "event": "llm_call", "trace_id": "79e685bb6f49cb3fb08c8585c8392c90", "span_id": "39cb06dbe3a4262f", "request_id": "eeb0c69235c5", "model": "mock-llm-small", "agent_version": "v2", "input_tokens": 83, "output_tokens": 44, "cost_usd": 3.9e-05, "llm_ms": 1696.4}
```

- **Trace lỗi đối chiếu (`5e4dd1a7f2d2076769392004454e2e62`, HTTP `503`):** tổng thời gian `119.70 ms`; span `chat mock-llm-small` (`98.10 ms`) và `agent.run` (`115.44 ms`) ghi nhận tag `error=true` kèm event `exception`, khớp dòng log JSON:
  `{"ts": "2026-11-25T10:35:02.254939+00:00", "level": "INFO", "service": "observable-agent", "instance": "8128e1ac8f57", "event": "llm_error", "trace_id": "5e4dd1a7f2d2076769392004454e2e62", "span_id": "965f2975bb3f4fa9", "request_id": "d5c3c982297b", "error": "Upstream LLM error: 503 Service Unavailable (mock)"}`

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

Số liệu đọc trực tiếp từ [scale_1_stats.csv](benchmark-results/scale_1_stats.csv) và [scale_3_stats.csv](benchmark-results/scale_3_stats.csv) (dòng `Aggregated`, kèm giá trị riêng của `POST /ask` trong ngoặc):

| Số instance | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---|---|---|---|---|---|
| 1 | `65.74` (`POST /ask`: `59.61`) | `190` | `220` | `1700` | `79 / 7846` (`1.01%`; `POST /ask`: `79 / 7114`, `1.11%`) |
| 3 | `66.01` (`POST /ask`: `59.83`) | `190` | `220` (`POST /ask`: `230`) | `1700` | `75 / 7877` (`0.95%`; `POST /ask`: `75 / 7139`, `1.05%`) |

**Giải thích kết quả:** Scale có cải thiện p95 không? Nút thắt nằm ở đâu?

Không. Khi tăng từ `1` lên `3` instance, RPS gần như giữ nguyên (`65.74` vs `66.01 req/s`), `p50` (`190 ms`), `p95` (`220–230 ms`) và `p99` (`1700 ms`) không đổi. Nguyên nhân:
1. **Nút thắt nằm ở latency của LLM call** (`~150–200 ms` cho request thường và `~1.7 s` cho ~3% tail latency): thêm nhiều replica không thể làm LLM bên ngoài trả lời nhanh hơn.
2. Với tải 100 users của Locust (mỗi user có wait time giữa các request, tổng nhu cầu chỉ ~66 req/s), **1 instance FastAPI async đã dư sức xử lý I/O đồng thời mà chưa bão hòa CPU**. Scale lên 3 instance giúp tăng **ngưỡng chịu tải tối đa (headroom)** khi traffic tăng gấp nhiều lần và tăng **high availability** (nếu 1 instance chết, Nginx tự chuyển traffic sang 2 instance còn lại).

---

## 6. Kết luận

- **3 điều học được về benchmark & observability:**
  1. **Tail latency (`p95`/`p99`) quan trọng hơn `avg`:** Chỉ 3% request chậm đã làm `p99` tăng gần 8 lần (`221.9 ms → 1704.2 ms`), và khi 10% request chậm `p95` nhảy lên `1686.9 ms` trong khi `avg` vẫn nhìn tương đối thấp (`312.3 ms`).
  2. **Ba trụ cột Metrics – Traces – Logs bổ trợ cho nhau:** Prometheus/Grafana phát hiện bất thường và bắn alert (`AgentHighLatencyP95`, `AgentHighErrorRate`), Jaeger chỉ đúng span nào gây chậm (`chat mock-llm-small` chiếm `98.4%`), còn `trace_id` nối thẳng sang log JSON chi tiết.
  3. **Hiệu năng tốt không đồng nghĩa chất lượng tốt:** Alert hạ tầng không bắt được lỗi suy giảm độ chính xác (như tụt về `v1`), nên bắt buộc phải có **eval trên golden dataset** làm quality gate trong CI/CD cùng chỉ số `cost / câu đúng`.
- **Nếu đưa agent này lên production thật, sẽ thêm metric / alert nào nữa?**
  1. **Metric & alert từ góc nhìn tầng gateway/LB (Nginx/Cloud):** tỷ lệ lỗi `502`/`504` ở Nginx (vì nếu agent treo quá timeout, chính agent không tự đếm được các request bị cắt ở gateway) và **synthetic health probe** từ bên ngoài.
  2. **Metric chất lượng & RAG online:** tỷ lệ retrieval miss (`retrieval_hits{status="miss"}`), điểm online eval / feedback người dùng (`user_feedback_total{rating="down"}`), và alert **Cost/Budget per user** hoặc **429 rate-limit spike** để phát hiện sớm hành vi lạm dụng API.
