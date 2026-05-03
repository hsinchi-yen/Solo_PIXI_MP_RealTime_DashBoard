# 實作方向拆解

**所屬專案：** 產線即時監控看板系統  
**推播方案：** Server-Sent Events (SSE)  
**文件版本：** v1.0

---

## 總覽：模組依賴關係

```
┌──────────────┐     ┌──────────────┐
│  M1: Parser  │────▶│  M2: State   │
└──────────────┘     └──────┬───────┘
                            │
┌──────────────┐            ▼
│  M2: Watcher │────▶┌──────────────┐     ┌──────────────┐
└──────────────┘     │  M3: FastAPI │────▶│  M4: Frontend│
                     │  SSE Backend │     │  Dashboard   │
                     └──────────────┘     └──────────────┘
                            │
                     ┌──────▼───────┐
                     │  M5: Docker  │
                     │  Packaging   │
                     └──────────────┘
```

---

## M1 — Log Parser（解析器）

### 職責

讀取單一 log 檔案，輸出標準化的 Python dict 結構。對外完全隔離，不依賴其他模組。

### 輸入

- 單一 `.txt` 檔案路徑（絕對路徑）

### 輸出結構

```python
{
    "filename": "5101-260129012_20260417_092007_001F7B6CA918_001F7B6CA919_PASS.txt",
    "fixture_id": "5101-260129012",
    "datetime": "2026-04-17T09:20:07",
    "mac1": "001F7B6CA918",
    "mac2": "001F7B6CA919",
    "result": "PASS",           # "PASS" | "FAIL" | "STOP"
    "duration": "01:16.7",      # 來自 "Test Time:" 行
    "test_items": [
        {
            "step": 5,
            "name": "BT_TX_BDR",
            "measurements": [
                {
                    "name": "Ini Freq Error",
                    "value": 21.708,
                    "unit": "KHz",
                    "upper": 75.0,
                    "lower": -75.0,
                    "status": "pass"    # "pass" | "fail"
                },
                ...
            ]
        }
    ],
    "failed_items": [
        {
            "step_name": "BT_TX_BDR",
            "measurement": "Ini Freq Error",
            "value": -153.141,
            "unit": "KHz",
            "limit": "(75.0 ~ -75.0)"
        }
    ],
    "stop_step": None,          # STOP 時填入中斷的步驟名稱
    "retry_count": 0            # FAIL 時紀錄重試次數
}
```

### 解析邏輯拆解

#### 1. 檔名解析（Filename Parser）

```
規則：{fixture}_{YYYYMMDD}_{HHMMSS}_{MAC1}_{MAC2}_{RESULT}.txt
正則：r'^(.+)_(\d{8})_(\d{6})_([0-9A-F]{12})_([0-9A-F]{12})_(PASS|FAIL|STOP)\.txt$'
```

- fixture_id、日期時間、兩個 MAC、結果全從檔名取得
- 不需要讀取內文即可得到核心欄位（加速批次掃描）

#### 2. 內文快速解析（Content Parser）

分段策略：以步驟號 `\d+\. ` 作為分隔符號切割全文，逐段處理

```
量測行正則：
r'^\s+(\w[\w\s]+?)\s{2,}([-\d.]+)\s+(\w+)\s+\(([\d.]+)\s*~\s*([-\d.]+)\)\s+<-- (pass|fail)'

Test Time 行正則：
r'^Test Time:\s+(.+)$'

STOP 偵測：
r'\*\*\*\* S T O P \*\*\*\*'
```

#### 3. 容錯機制

| 情境 | 處理方式 |
|------|----------|
| 檔名不符命名規則 | 記錄 warning，跳過該檔 |
| 內文量測行格式異常 | 跳過該行，繼續解析其餘行 |
| 檔案讀取失敗（權限/損毀） | 記錄 error，加入 `parse_errors` 清單 |
| 非 UTF-8 編碼 | 嘗試 `latin-1` fallback |

### 測試策略

- **Unit Test**：對三種結果類型各準備 fixture 檔案測試
- **Edge Case**：空檔案、截斷檔案（測試進行中尚未寫完）、重試 3 次後 FAIL
- **效能測試**：單檔解析時間目標 < 5ms（i.MX 8M Plus 上 < 20ms）

---

## M2 — State Manager（狀態管理器）

### 職責

維護全域 in-memory 狀態，提供讀取與更新介面，負責啟動時的歷史補回邏輯。

### 資料結構設計

```python
class DashboardState:

    # PASS 去重複：key = mac1, value = 最新 PASS 紀錄
    pass_records: dict[str, ParsedLog]

    # FAIL 全量：list（不去重，依時間排序）
    fail_records: list[ParsedLog]

    # STOP 全量：list（不去重，依時間排序）
    stop_records: list[ParsedLog]

    # 近期紀錄流（三種混合，依時間排序，上限 50 筆）
    recent_records: deque[ParsedLog]  # maxlen=50

    # 失效項目統計
    failure_stats: Counter  # key = measurement name, value = count

    # 計算屬性（不儲存，按需計算）
    @property
    def pass_count(self) -> int:
        return len(self.pass_records)  # 已去重

    @property
    def fail_count(self) -> int:
        return len(self.fail_records)

    @property
    def yield_rate(self) -> float:
        total = self.pass_count + self.fail_count
        return (self.pass_count / total * 100) if total > 0 else 0.0

    @property
    def uph(self) -> int:
        # 過去 60 分鐘內的 PASS 數量
        ...
```

### 啟動補回流程（Startup Scan）

```
1. 掃描 log_dir 所有 .txt 檔案
2. 依檔名時間戳排序（舊 → 新）
3. 逐一呼叫 Parser 解析
4. 逐一呼叫 state.ingest(record)
5. 補回完成後設 state.ready = True
6. 廣播 "init_complete" 事件給所有 SSE 連線
```

> **設計要點：** 補回期間 SSE 服務已可接受連線，前端顯示「資料載入中 X/Y」進度條；補回完成後自動切換為正常看板。

### `ingest(record)` 邏輯

```
if result == "PASS":
    if mac1 already in pass_records:
        compare timestamps → keep newer one
    else:
        add to pass_records
    add to recent_records
    update uph_window

elif result == "FAIL":
    append to fail_records
    add to recent_records
    update failure_stats (Counter)

elif result == "STOP":
    append to stop_records
    add to recent_records
    trigger stop_alert event
```

### 執行緒安全

- State Manager 使用 `asyncio.Lock` 保護讀寫操作
- 所有 `ingest()` 呼叫須在 async 上下文中執行

---

## M2b — Watcher（目錄監控器）

### 職責

監控 log 目錄，偵測新檔案落地，觸發解析與狀態更新。

### 技術：`watchdog` + inotify

```python
from watchdog.observers.inotify import InotifyObserver
from watchdog.events import FileCreatedEvent, FileSystemEventHandler
```

選用 `InotifyObserver`（Linux 專用）而非通用 `Observer`，直接使用核心 inotify 事件，無輪詢 overhead。

### 事件處理流程

```
FileCreatedEvent（新檔案）
    └─▶ 檢查副檔名是否為 .txt
        └─▶ 等待 0.1 秒（確保檔案寫入完成）
            └─▶ 呼叫 Parser.parse(path)
                └─▶ 呼叫 state.ingest(record)
                    └─▶ 呼叫 sse_manager.broadcast(event)
```

> **等待策略：** inotify `IN_CLOSE_WRITE` 事件比 `IN_CREATE` 更可靠（檔案關閉後才觸發），`watchdog` 的 `InotifyObserver` 預設使用 `IN_CLOSE_WRITE`，無需額外等待。若使用其他平台 Observer，需加 0.1~0.5 秒等待。

### 與 FastAPI 整合

```python
# main.py 啟動流程
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. 啟動補回
    await startup_scan(state, log_dir)
    # 2. 啟動 watchdog（在 executor 中跑，不阻塞 event loop）
    loop = asyncio.get_event_loop()
    observer = start_watcher(log_dir, state, sse_manager, loop)
    yield
    # 3. 關閉
    observer.stop()
```

---

## M3 — FastAPI SSE 後端

### Endpoint 實作細節

#### `GET /api/stream`（SSE 長連線）

```python
@app.get("/api/stream")
async def sse_stream(request: Request):
    client_id = str(uuid4())
    queue = asyncio.Queue(maxsize=100)
    sse_manager.register(client_id, queue)

    async def event_generator():
        # 送出 retry 設定
        yield "retry: 3000\n\n"
        try:
            while True:
                if await request.is_disconnected():
                    break
                event = await asyncio.wait_for(queue.get(), timeout=30)
                yield f"event: {event['type']}\ndata: {json.dumps(event['data'])}\n\n"
        except asyncio.TimeoutError:
            # 每 30 秒送 heartbeat，防止代理逾時斷線
            yield f"event: heartbeat\ndata: {json.dumps({'ts': time.time()})}\n\n"
        finally:
            sse_manager.unregister(client_id)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no"   # 關閉 Nginx 緩衝
        }
    )
```

#### `GET /api/snapshot`（初始狀態快照）

前端首次連線或 SSE 重連後呼叫，取得完整當前狀態。

```json
{
    "stats": {
        "pass": 42,
        "fail": 3,
        "stop": 1,
        "yield": 93.3,
        "uph": 38,
        "total": 46
    },
    "recent_records": [...],   // 最近 50 筆
    "stop_alerts": [...],      // 所有 STOP 事件
    "failure_stats": {
        "Ini Freq Error": 5,
        "Power": 2
    },
    "ready": true              // 啟動補回是否完成
}
```

### SSE Manager（廣播管理）

```python
class SSEManager:
    def __init__(self, max_connections: int = 20):
        self._clients: dict[str, asyncio.Queue] = {}
        self._max = max_connections

    def register(self, client_id: str, queue: asyncio.Queue):
        if len(self._clients) >= self._max:
            raise TooManyConnectionsError()
        self._clients[client_id] = queue

    def unregister(self, client_id: str):
        self._clients.pop(client_id, None)

    async def broadcast(self, event_type: str, data: dict):
        dead = []
        for cid, q in self._clients.items():
            try:
                q.put_nowait({"type": event_type, "data": data})
            except asyncio.QueueFull:
                dead.append(cid)  # 塞不進去視為斷線
        for cid in dead:
            self.unregister(cid)
```

### SSE Event 類型總表

| Event Type | 觸發時機 | Data 內容 |
|------------|----------|-----------|
| `stats_update` | 每次新 log ingest 後 | 全量 KPI 數字 |
| `new_record` | 每次新 log ingest 後 | 單筆紀錄摘要 |
| `stop_alert` | STOP 檔案出現時 | STOP 事件詳情 |
| `init_progress` | 啟動補回進行中 | `{current, total}` |
| `init_complete` | 啟動補回完成 | 空 |
| `heartbeat` | 每 30 秒 idle 時 | `{ts}` |

---

## M4 — 前端 Dashboard

### 技術選擇：Vanilla JS + EventSource

不引入任何 JS 框架，原因：
- 目標環境可能無法訪問 CDN
- 減少 Docker image 體積
- `EventSource` 為瀏覽器原生 API，無依賴

### 前端初始化流程

```javascript
async function init() {
    // 1. 取得快照（建立初始狀態）
    const snapshot = await fetch('/api/snapshot').then(r => r.json());
    renderSnapshot(snapshot);

    // 2. 建立 SSE 連線
    const es = new EventSource('/api/stream');

    es.addEventListener('stats_update', e => {
        updateKPI(JSON.parse(e.data));
    });

    es.addEventListener('new_record', e => {
        prependRecord(JSON.parse(e.data));
    });

    es.addEventListener('stop_alert', e => {
        showStopAlert(JSON.parse(e.data));
    });

    es.addEventListener('init_progress', e => {
        showProgress(JSON.parse(e.data));
    });

    // SSE 斷線事件（瀏覽器自動重連）
    es.onerror = () => {
        setConnectionStatus('disconnected');
        // 重連成功後重新取快照
        es.onopen = async () => {
            const snap = await fetch('/api/snapshot').then(r => r.json());
            renderSnapshot(snap);
            setConnectionStatus('connected');
        };
    };
}
```

### 畫面組件清單

| 組件 | 功能 | 更新觸發 |
|------|------|----------|
| `KPIBar` | 顯示 PASS/FAIL/STOP/良率/UPH 五格 | `stats_update` |
| `StopAlertPanel` | STOP 警示列表（橙色區塊） | `stop_alert` |
| `RecentTable` | 流水紀錄表，最多 50 列 | `new_record` |
| `FailureChart` | Top N 失效項目橫條圖（純 CSS） | `stats_update` |
| `ConnectionDot` | 右上角連線狀態指示燈 | SSE open/error |
| `ProgressBar` | 啟動補回進度（補回完成後隱藏） | `init_progress` |

### 良率視覺警戒邏輯

```javascript
function updateYieldDisplay(yieldPct) {
    const el = document.getElementById('kpi-yield');
    el.textContent = yieldPct.toFixed(1) + '%';
    el.className = 'kpi-value ' + (
        yieldPct >= 90 ? 'color-pass' :
        yieldPct >= 80 ? 'color-stop' :
                         'color-fail blink'
    );
}
```

### 新紀錄插入動畫（純 CSS）

```css
.record-row {
    animation: none;
}
.record-row.new-pass {
    animation: flash-green 1s ease-out;
}
.record-row.new-fail {
    animation: flash-red 3s ease-out;
}

@keyframes flash-green {
    0%   { background-color: rgba(0, 255, 136, 0.4); }
    100% { background-color: transparent; }
}

@keyframes flash-red {
    0%   { background-color: rgba(255, 59, 59, 0.5); }
    100% { background-color: rgba(255, 59, 59, 0.1); }
}
```

---

## M5 — Docker 打包

### 映像檔策略

使用多階段建構（multi-stage build）壓縮最終映像檔：

```
Stage 1: python:3.11-slim    → 安裝依賴，生成 wheels
Stage 2: python:3.11-slim    → 僅複製 wheels + 應用程式碼
目標映像大小：< 150MB
```

### 依賴清單（requirements.txt）

```
fastapi==0.111.*
uvicorn[standard]==0.30.*
watchdog==4.*
```

> 刻意保持最小依賴，無 ORM、無資料庫驅動、無重型框架。

### docker-compose.yml 關鍵設計

```yaml
volumes:
  - /data/logs:/data/logs:ro   # log 目錄唯讀掛載
  - ./config:/app/config:ro

ports:
  - "8080:8080"

restart: unless-stopped

# i.MX 8M Plus 記憶體限制
deploy:
  resources:
    limits:
      memory: 256M
```

### Yocto 整合注意事項

| 項目 | 說明 |
|------|------|
| Docker Engine 安裝 | 透過 `meta-virtualization` layer 加入 `docker-ce` |
| Kernel config | 需在 BSP layer 中補充 cgroups / namespaces / overlay 選項 |
| 開機自啟 | 使用 systemd service 啟動 `docker-compose up -d` |
| 時區設定 | Container 內需與主機時區一致（掛載 `/etc/localtime`） |

---

## 各模組介面摘要

```
Parser
  parse(filepath: str) -> ParsedLog | None

State
  ingest(record: ParsedLog) -> None
  get_snapshot() -> SnapshotDict
  ready: bool

Watcher
  start(log_dir: str, state: State, sse: SSEManager, loop) -> Observer
  stop(observer: Observer) -> None

SSEManager
  register(client_id, queue) -> None
  unregister(client_id) -> None
  broadcast(event_type, data) -> Coroutine

FastAPI Routes
  GET /              → index.html
  GET /api/stream    → SSE StreamingResponse
  GET /api/snapshot  → JSONResponse
```

---

## 開發順序建議

```
Week 1
  Day 1-2 │ M1: Parser + 單元測試（用現有 log 檔驗證）
  Day 3   │ M2: State Manager + 補回邏輯
  Day 4-5 │ M3: FastAPI + SSE 後端（用 curl 驗證推播）

Week 2
  Day 1-3 │ M4: 前端 Dashboard
  Day 4-5 │ M5: Docker + i.MX 8M Plus 實機測試
  Day 6   │ 產線驗收
```
