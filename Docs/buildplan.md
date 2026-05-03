# 產線即時監控看板系統 — 建置計畫書

**文件版本：** v1.0  
**建立日期：** 2026-05-03  
**適用對象：** 測試工程師 / 產線班長 / 管理員  
**推播技術：** Server-Sent Events (SSE)  
**部署平台：** i.MX 8M Plus · Yocto + Wayland · Docker + Uvicorn

---

## 1. 專案背景與目標

### 1.1 背景說明

現行產線測試流程以 IQ112 測試儀搭配 Qualcomm QCA9377 模組進行 BT / Wi-Fi RF 測試，每次測試完成後自動產出結構化 log 檔案至指定目錄。目前無即時彙整機制，班長與工程師須手動翻閱 log 才能掌握生產狀況，無法在第一時間發現異常趨勢。

本系統目標為建立一套**零資料庫、低功耗、即時推播**的產線看板，將 log 目錄作為唯一資料來源，直接解析並推送至 Web 前端，讓所有相關人員在任一瀏覽器上即時掌握生產品質狀態。

### 1.2 核心目標

| 目標 | 說明 |
|------|------|
| 即時性 | log 落地後 ≤ 1 秒內更新前端畫面 |
| 低功耗部署 | 系統整體功耗目標 ≤ 5W（i.MX 8M Plus 平台） |
| 零資料庫 | 重啟後重新掃描目錄補回歷史資料，不依賴任何外部資料庫 |
| 多端同時檢視 | 支援多個瀏覽器同時連線，資料一致 |
| 易維護 | 容器化部署，升級不影響產線運作 |

---

## 2. Log 資料規格

### 2.1 檔案命名規則

```
{fixture_id}_{date}_{time}_{MAC1}_{MAC2}_{result}.txt
```

**範例：**
```
5101-260129012_20260417_092007_001F7B6CA918_001F7B6CA919_PASS.txt
5101-260129012_20260417_092030_001F7B6CA918_001F7B6CA919_STOP.txt
5101-260129012_20260417_092154_001F7B6CA91E_001F7B6CA91F_FAIL.txt
```

| 欄位 | 說明 | 範例 |
|------|------|------|
| `fixture_id` | 治具/工站識別碼 | `5101-260129012` |
| `date` | 測試日期 YYYYMMDD | `20260417` |
| `time` | 測試開始時間 HHMMSS | `092007` |
| `MAC1` | 主要 MAC 位址 | `001F7B6CA918` |
| `MAC2` | 次要 MAC 位址 | `001F7B6CA919` |
| `result` | 測試結果 | `PASS` / `FAIL` / `STOP` |

### 2.2 Log 內文結構

```
MAC1:    001F7B6CA918
MAC2:    001F7B6CA919
Start:   2026/04/17 09:20:07

1. ATC_CONNECT_TESTER
   Serial number: IQ112EA2387
   Test time: 0.05sec

2. ATC_INSERT_DUT
   Technology: BT
   DUT DLL: QCA_9377.dll
   DUT_VERSION=1.0.2 (2024-05-14)
   ...

5. BT_TX_BDR
   Frequency: 2402, Packet Type: 1DH1, Tx Power: 5.0

   Ini Freq Error      21.708 KHz     (75.0 ~ -75.0)   <-- pass
   Freq Drift         -0.698 KHz      (25.0 ~ -25.0)   <-- pass
   ...

End:       2026/04/17 09:21:24
Test Time: 01:16.7

   **** P A S S ****
```

### 2.3 三種結果類型定義

| 結果 | 觸發條件 | 去重複邏輯 |
|------|----------|------------|
| **PASS** | 所有步驟全數通過 | **依 MAC1 去重複**（同一 MAC 重測後取最新一筆 PASS） |
| **FAIL** | 任一量測項目超出規格，重試後仍失敗 | **不去重複**，每筆獨立記錄 |
| **STOP** | 測試中途人工或條件中斷 | **不去重複**，每筆獨立記錄 |

> **PASS 去重複說明：** 同一 MAC1 可能因重投料而出現多個 PASS 檔案（例如先 FAIL 後修復再測試 PASS）。統計良品數時，以 MAC1 為 key，只計入最新一筆 PASS，避免重複計算產出數量。

### 2.4 FAIL 失效模式分類

從現有 log 觀察到兩種主要失效模式：

| 模式 | 失效項目 | 範例值 | 規格 |
|------|----------|--------|------|
| **BT Freq Error** | `Ini Freq Error` 超差 | −153 KHz | ±75 KHz |
| **BT Power Low** | `Power` 低於下限 | −1.7 dBm | 0 ~ 10 dBm |

---

## 3. 系統架構

### 3.1 整體架構圖

```
┌─────────────────────────────────────────────────────┐
│                   i.MX 8M Plus                      │
│                                                     │
│  ┌─────────────┐    ┌──────────────────────────┐   │
│  │  Log 目錄   │───▶│     Docker Container      │   │
│  │  /log/data/ │    │                          │   │
│  └─────────────┘    │  ┌────────────────────┐  │   │
│                     │  │  watchdog (Python)  │  │   │
│                     │  │  監聽 inotify 事件  │  │   │
│                     │  └────────┬───────────┘  │   │
│                     │           │ 新檔案事件    │   │
│                     │  ┌────────▼───────────┐  │   │
│                     │  │  Log Parser        │  │   │
│                     │  │  解析 → 結構化資料  │  │   │
│                     │  └────────┬───────────┘  │   │
│                     │           │               │   │
│                     │  ┌────────▼───────────┐  │   │
│                     │  │  State Manager     │  │   │
│                     │  │  in-memory 狀態庫   │  │   │
│                     │  └────────┬───────────┘  │   │
│                     │           │ push event    │   │
│                     │  ┌────────▼───────────┐  │   │
│                     │  │  FastAPI + Uvicorn  │  │   │
│                     │  │  SSE /api/stream    │  │   │
│                     │  │  REST /api/snapshot │  │   │
│                     │  └────────┬───────────┘  │   │
│                     └───────────┼──────────────┘   │
└─────────────────────────────────┼───────────────────┘
                                  │ HTTP / SSE
                    ┌─────────────┼──────────────┐
                    │             │              │
              ┌─────▼──┐   ┌──────▼─┐   ┌───────▼──┐
              │Browser │   │Browser │   │Browser   │
              │(班長)  │   │(工程師)│   │(管理員)  │
              └────────┘   └────────┘   └──────────┘
```

### 3.2 技術選型

| 層次 | 技術 | 選用理由 |
|------|------|----------|
| 後端框架 | FastAPI | 原生支援 `StreamingResponse`（SSE）；async 架構低 CPU 佔用 |
| ASGI 伺服器 | Uvicorn | 輕量、生產級、與 FastAPI 原生搭配 |
| 目錄監控 | watchdog + inotify | 純事件驅動，無輪詢，i.MX Linux 核心原生支援 |
| 資料層 | Python in-memory dict | 無資料庫依賴，重啟掃描補回 |
| 前端 | Vanilla JS + EventSource API | 無框架負擔，瀏覽器原生支援 SSE |
| 容器 | Docker + docker-compose | 隔離部署，映像檔目標 < 150MB |

---

## 4. 功能規格

### 4.1 統計指標（Dashboard KPI 區）

| 指標 | 計算方式 | 更新頻率 |
|------|----------|----------|
| **良品數 (PASS)** | 去重複 MAC1 後的 PASS 總數 | 每筆新 log 觸發 |
| **不良品數 (FAIL)** | 所有 FAIL 檔案總數（不去重） | 每筆新 log 觸發 |
| **中斷數 (STOP)** | 所有 STOP 檔案總數（不去重） | 每筆新 log 觸發 |
| **良率 (Yield %)** | PASS ÷ (PASS + FAIL) × 100 | 每筆新 log 觸發 |
| **當班 UPH** | 過去 60 分鐘內 PASS 數 | 滾動計算 |
| **測試總筆數** | PASS + FAIL + STOP 合計 | 每筆新 log 觸發 |

### 4.2 即時流水紀錄（Recent Tests 區）

- 顯示最近 50 筆測試結果（含三種狀態）
- 每筆顯示：時間、MAC1、MAC2、結果、測試耗時、失敗項目摘要
- 新紀錄從頂部插入，舊紀錄向下推移
- FAIL 紀錄額外顯示：失敗步驟名稱 + 失敗量測項目

### 4.3 STOP 警示區

- STOP 事件獨立顯示於警示區，不混入流水紀錄
- 顯示觸發時間、MAC、在哪個測試步驟中斷
- 警示區底色醒目（橙色系），提醒班長確認

### 4.4 失效分析摘要（Failure Analysis 區）

- 統計各失效項目的出現次數（例：`Ini Freq Error` × 5，`Power` × 2）
- 以橫條圖方式呈現 Top N 失效項目
- 協助工程師快速識別系統性問題

### 4.5 啟動時歷史補回

- 服務啟動時掃描 log 目錄中所有現有檔案
- 依檔名時間戳排序後逐一解析，重建 in-memory 狀態
- 補回完成後再開始監聽新檔案，確保不遺漏

---

## 5. SSE 推播協議設計

### 5.1 Endpoint 定義

| Endpoint | Method | 說明 |
|----------|--------|------|
| `GET /api/stream` | SSE | 長連線推播，持續推送事件 |
| `GET /api/snapshot` | REST | 首次連線取得完整當前狀態 |
| `GET /` | HTTP | 前端靜態頁面 |

### 5.2 SSE Event 格式

```
event: stats_update
data: {"pass": 42, "fail": 3, "stop": 1, "yield": 93.3, "uph": 38}

event: new_record
data: {"mac1": "001F7B6CA918", "mac2": "001F7B6CA919", "result": "PASS",
       "time": "09:20:07", "duration": "01:16.7", "failed_items": []}

event: stop_alert
data: {"mac1": "001F7B6CA918", "time": "09:20:30", "step": "BT_TX_BDR"}

event: heartbeat
data: {"ts": 1745893200}
```

### 5.3 斷線重連策略

- SSE 規範內建斷線重連（瀏覽器原生）
- 伺服器端設定 `retry: 3000`（3 秒後重試）
- 重連後前端自動呼叫 `/api/snapshot` 補齊狀態，避免漏失事件

---

## 6. 硬體部署規格

### 6.1 i.MX 8M Plus 平台

| 項目 | 規格 | 備註 |
|------|------|------|
| SoC | NXP i.MX 8M Plus | Cortex-A53 × 4 @ 1.8GHz |
| 建議 RAM | 2GB 以上 | 系統 + Docker + 應用 合計 < 512MB |
| 儲存 | 8GB eMMC 以上 | Log 目錄建議外掛 USB 或 NFS |
| 作業系統 | Yocto Linux + Wayland | meta-openembedded 提供 Python 3 |
| 容器引擎 | Docker CE (containerd) | 需確認 kernel cgroups v2 支援 |
| 網路 | GbE | 連接廠內區域網路 |
| 估算功耗 | 3 ~ 5W | 含網路、無 GPU 負載 |

### 6.2 Yocto Kernel 必要 Config

```
CONFIG_CGROUPS=y
CONFIG_CGROUP_DEVICE=y
CONFIG_CPUSETS=y
CONFIG_MEMCG=y
CONFIG_NAMESPACES=y
CONFIG_NET_NS=y
CONFIG_PID_NS=y
CONFIG_IPC_NS=y
CONFIG_UTS_NS=y
CONFIG_INOTIFY_USER=y       # watchdog 依賴
CONFIG_VETH=y
CONFIG_BRIDGE=y
CONFIG_OVERLAY_FS=y         # Docker overlay2 storage driver
```

### 6.3 替代硬體方案（備選）

若 i.MX 8M Plus 在 Docker 支援或採購上有限制，以下為替代低功耗方案：

| 方案 | CPU | 功耗 | Docker 支援 | 建議程度 |
|------|-----|------|-------------|----------|
| Raspberry Pi 5 (4GB) | Cortex-A76 × 4 | 5~8W | ✅ 原生 | ⭐⭐⭐ 快速部署首選 |
| Orange Pi 5 (RK3588S) | A76×4 + A55×4 | 5~7W | ✅ 良好 | ⭐⭐⭐ 效能最強 |
| Radxa ROCK 5B (RK3588) | 同上 + PCIe | 6~8W | ✅ 良好 | ⭐⭐ 工業擴充性佳 |
| BeagleBone AI-64 (TDA4VM) | A72×2 | 3~4W | ⚠️ 有限 | ⭐ 功耗最低但生態薄 |

---

## 7. Dashboard GUI 設計理念

### 7.1 核心設計原則

**遠距可讀性優先**  
看板通常掛牆上或置於產線側邊，操作者距離 2–5 公尺。所有關鍵數字使用 64px 以上粗體，顏色語義必須直覺。

**深色主題**  
工廠燈光複雜（強光 + 反射），深色底（近黑）提供最穩定對比，避免螢幕反光干擾閱讀。

**三色語義系統**

| 顏色 | 狀態 | 用途 |
|------|------|------|
| 🟢 綠色 `#00FF88` | PASS | 良品計數、良率指標 |
| 🔴 紅色 `#FF3B3B` | FAIL | 不良品計數、失敗紀錄列 |
| 🟠 橙色 `#FF9500` | STOP | 中斷警示區、中斷紀錄 |

### 7.2 畫面佈局（1920×1080 基準）

```
┌────────────────────────────────────────────────────────────────┐
│  HEADER：Fixture ID ｜ 當班時間 ｜ 連線狀態指示燈              │
├──────────┬──────────┬──────────┬──────────┬───────────────────┤
│  PASS    │  FAIL    │  STOP    │  良率    │  UPH              │
│  【042】 │  【003】 │  【001】 │  93.3%   │  38/hr            │
├──────────┴──────────┴──────────┴──────────┴───────────────────┤
│  STOP 警示區（有 STOP 事件時顯示，橙底醒目）                  │
│  09:20:30 ｜ MAC: 001F7B6CA918 ｜ 中斷於 BT_TX_BDR           │
├────────────────────────────────┬───────────────────────────────┤
│  即時流水紀錄（最新 50 筆）    │  失效項目分析                 │
│  ────────────────────────────  │  ─────────────────────────    │
│  ✅ 09:21:24 001F7B6CA918 PASS │  Ini Freq Error  ████████ 5  │
│  ❌ 09:22:04 001F7B6CA91E FAIL │  Power Low       ████ 2      │
│     ↳ BT_TX_BDR: Freq Error   │  (其他...)                    │
│  ✅ 09:22:29 001F7B6CA91E PASS │                               │
│  ...                           │                               │
└────────────────────────────────┴───────────────────────────────┘
```

### 7.3 動態行為

- **新 PASS 紀錄插入**：綠色閃爍 1 秒後恢復正常列色
- **新 FAIL 紀錄插入**：紅色整列高亮，保持 3 秒
- **STOP 事件**：警示區展開動畫 + 橙色脈衝效果
- **良率下降警戒**：良率 < 90% 時良率數字變橙色；< 80% 變紅色並閃爍
- **連線狀態指示燈**：SSE 連線正常為綠燈，斷線為紅燈閃爍

---

## 8. 專案里程碑

| 階段 | 內容 | 預估工期 |
|------|------|----------|
| **M1** | Log Parser 開發與單元測試 | 2 天 |
| **M2** | State Manager + 啟動補回邏輯 | 1 天 |
| **M3** | FastAPI SSE 後端 + API 端點 | 2 天 |
| **M4** | 前端 Dashboard 實作 | 3 天 |
| **M5** | Docker 打包 + Yocto 整合測試 | 2 天 |
| **M6** | 產線驗收測試 | 1 天 |
| **總計** | | **約 11 個工作天** |

---

## 9. 風險與對策

| 風險 | 影響 | 對策 |
|------|------|------|
| Yocto kernel 缺少 cgroups config | Docker 無法啟動 | 預先驗證 kernel config；備選方向 B：直接跑 uvicorn 不用 Docker |
| Log 目錄掛載權限問題 | watchdog 無法讀取 | docker-compose volumes 設定 + 確認 GID 一致 |
| 大量歷史 log 補回時間過長 | 服務啟動慢 | 啟動補回與 SSE 服務並行；前端顯示「補回進度」 |
| 多瀏覽器同時連線 SSE 消耗資源 | CPU 升高 | asyncio broadcast 模式；連線數設上限（預設 20） |
| Log 格式版本異動 | 解析失敗 | Parser 設計版本容錯；解析失敗的檔案寫入 error.log 並跳過 |

---

## 10. 附錄

### A. 目錄結構（應用程式）

```
dashboard/
├── Dockerfile
├── docker-compose.yml
├── app/
│   ├── main.py              # FastAPI 入口
│   ├── parser.py            # Log 解析器
│   ├── state.py             # In-memory 狀態管理
│   ├── watcher.py           # watchdog 目錄監控
│   └── sse.py               # SSE 推播管理
├── frontend/
│   ├── index.html           # 主畫面
│   ├── dashboard.js         # SSE 連線 + DOM 更新
│   └── style.css            # 深色主題樣式
└── config/
    └── settings.toml        # log 目錄路徑、連線上限等設定
```

### B. 設定檔範例（settings.toml）

```toml
[paths]
log_dir = "/data/logs"

[server]
host = "0.0.0.0"
port = 8080
max_sse_connections = 20

[dashboard]
recent_records_limit = 50
uph_window_minutes = 60
yield_warning_threshold = 90.0
yield_critical_threshold = 80.0
```
