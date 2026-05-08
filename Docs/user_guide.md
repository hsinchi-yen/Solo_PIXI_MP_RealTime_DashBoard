# PIXI Modules MP 監控系統 — 使用教學

**文件版本**：1.0.0  
**最後更新**：2026-05-08  
**適用對象**：PE Engineer（製程工程師）、班長、操作員  
**適用系統**：PIXI Modules MP 監控 Dashboard + Real-time Log Splitter

---

## 目錄

1. [系統架構簡介](#1-系統架構簡介)
2. [操作員篇 — 看懂 Dashboard](#2-操作員篇--看懂-dashboard)
3. [班長篇 — 監控產量與上傳資料](#3-班長篇--監控產量與上傳資料)
4. [PE Engineer 篇 — 系統設定與維護](#4-pe-engineer-篇--系統設定與維護)
5. [Real-time Log Splitter 使用教學](#5-real-time-log-splitter-使用教學)
6. [常見狀況處理](#6-常見狀況處理)

---

## 1. 系統架構簡介

```
生產線測試站 (Station 10/20/30...)
    │  產生測試 log (.txt)
    ▼
NVMe SSD (/run/media/nvme0n1p1/rawlogs/)
    │  即時監控
    ▼
PIXI Dashboard (http://192.168.x.x:8080)
    │  可從線上任一台電腦開瀏覽器查看
    ▼
DB Server (選用)：Upload 彙整資料
```

**Real-time Log Splitter** 是一支獨立的 Windows 桌面程式，執行在 PC 端，負責透過 SSH 把 embedded 設備上的 rawlogs 依 Station 分類複製到本地資料夾，方便後續分析。

---

## 2. 操作員篇 — 看懂 Dashboard

> **您只需要看畫面，不需要設定任何東西。**  
> 如果畫面顯示異常，請通知班長或 PE Engineer。

### 2.1 如何開啟 Dashboard

1. 在線上任一台 PC 開啟瀏覽器（Chrome / Edge）
2. 輸入網址：`http://192.168.100.1:8080`（IP 請依現場實際設定）
3. 畫面會自動顯示即時資料，不需要登入

> Dashboard 也會自動顯示在設備旁的螢幕上（Kiosk 模式）。

---

### 2.2 畫面各區說明

#### 頁首區（Header）

```
┌──────────────────────────────────────────────────────────┐
│ PIXI Modules MP   WO: [工單號] QTY: [目標]   CPU RAM TEMP │
│ Monitoring DashBOARD                         2026-05-08  │
│                                              14:30:25    │
└──────────────────────────────────────────────────────────┘
```

| 顯示項目 | 說明 |
|---------|------|
| WO | 目前生產工單號碼 |
| QTY | 今日目標生產數量 |
| CPU | 設備 CPU 使用率。超過 80% 會變**橘色**警示 |
| RAM | 設備可用記憶體 |
| TEMP | CPU 溫度。超過 70°C 會變**橘色**警示 |
| 日期/時鐘 | 設備目前時間 |

---

#### 狀態列（OPS Strip）

```
 MODE: REMOTE   WO: 5101-260129012   DB: READY   WO ROOT: READY   RAWLOGS: READY
```

| 標籤 | 顏色 | 代表意義 |
|------|------|---------|
| MODE | 綠色 LOCAL | 在設備本機操作（可修改設定） |
| MODE | 橘色 REMOTE | 從其他電腦連線（僅能查看） |
| WO | 綠色 | 工單已設定 |
| DB | 綠色 READY | 資料庫連線正常，可以上傳 |
| DB | 紅色 OFFLINE | 資料庫無法連線 |
| DB | 橘色 LOCKED | DB 功能只限本機操作 |
| WO ROOT | 綠色 READY | NVMe 工單目錄存在 |
| RAWLOGS | 綠色 READY | log 目錄存在且正常監控 |

> 正常生產時，以上全部應為**綠色**。有任何紅色或橘色請通知班長。

---

#### KPI 看板

```
┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌────────┐ ┌────────────┐ ┌───────────┐
│ 123 │ │  98 │ │   3 │ │   2 │ │ 97.0%  │ │   61.5%    │ │   2.4%    │
│TOTAL│ │PASS │ │FAIL │ │STOP │ │ YIELD ↑│ │COMPLETION ↑│ │RETEST RATE│
└─────┘ └─────┘ └─────┘ └─────┘ └────────┘ └────────────┘ └───────────┘
```

| KPI | 說明 | 正常狀態 |
|-----|------|---------|
| **TOTAL** | 今日測試總數 | 持續增加 |
| **PASS** | 測試通過數 | 綠色 |
| **FAIL** | 測試失敗數 | 紅色，過多請通報 PE |
| **STOP** | 測試中斷數 | 橘色，出現時請通報班長 |
| **YIELD** | 良率 = PASS ÷ TOTAL | 綠色 ≥ 90%；橘色 ≥ 80%；紅色閃爍 < 80% |
| **COMPLETION** | 完成率 = TOTAL ÷ QTY | 藍色顯示進度 |
| **RETEST RATE** | 重測比例 | 橘色，越低越好 |

> ↑↓ 箭頭代表過去 5 分鐘的趨勢：↑ 上升，↓ 下降，→ 持平。

---

#### ① 每小時完成數圖表

- 顯示 07:00 至 19:00 每小時的測試完成數量
- 柱子越高 = 該小時生產越多
- 滑鼠移到柱子上可看到精確數字

---

#### ② 結果分佈圖

- 水平長條圖，顯示 PASS / FAIL / STOP 各佔百分比
- 正常生產：PASS 應佔最大比例

---

#### 最近測試記錄（右側表格）

| 欄位 | 說明 |
|------|------|
| Station | 測試站編號（10/20/30...） |
| Time | 測試完成時間 |
| MAC1 / MAC2 | 產品 MAC Address |
| Result | PASS（綠）/ FAIL（紅）/ STOP（橘） |
| Duration | 測試花費時間 |
| Failure Items | FAIL 時顯示失敗測項（點擊可展開） |

> 新記錄出現時會有短暫閃光：
> - 綠色閃光 = PASS（正常）
> - 紅色閃光 = FAIL（注意）
> - 橘色閃光 = STOP（通知班長）

---

#### 底部連線指示燈

| 指示燈顏色 | 狀態 |
|-----------|------|
| 🟢 綠色常亮 | 正常，資料即時更新 |
| 🔴 紅色閃爍 | 連線中斷，畫面資料可能不是最新的 |

> 連線中斷時不要緊張，頁面保留最後已知資料。通常 30 秒內會自動重連。若超過 1 分鐘仍未恢復，通知班長或 PE。

---

### 2.3 日夜模式切換

點選畫面右下角的 **☀ DAY / 🌙 DARK** 按鈕可切換明暗主題，系統會記住您的選擇。

---

## 3. 班長篇 — 監控產量與上傳資料

> 班長除了查看 Dashboard 之外，還需要管理 WO 工單與資料上傳。

### 3.1 開始新的生產工單

> **注意**：工單設定只能在**設備本機**瀏覽器操作（`http://localhost:8080`）。從其他電腦連線時，WO / QTY 欄位會鎖定。

1. 在設備本機開啟 `http://localhost:8080`
2. 確認 **OPS Strip → MODE** 顯示為 **LOCAL**（綠色）
3. 若欄位鎖定，點選 **🔓 Edit** 解鎖

**設定步驟：**

| 步驟 | 操作 |
|------|------|
| ① 選擇 WO | 從 WO 下拉選單選取工單號（若沒有，選 `custom` 手動輸入） |
| ② 點 ↻ 按鈕 | 重新整理工單列表（若剛建立新工單目錄） |
| ③ 輸入 QTY | 填入今日目標生產數量 |
| ④ 點 💾 Save | 儲存設定，WO / QTY 欄位會自動鎖定 |

儲存後，**WO PATH** 標籤應顯示**綠色**（目錄存在）。

---

### 3.2 收工 / 換工單

1. 點選 🗑 **Clear** 按鈕清除目前工單設定
2. 重新執行 3.1 的步驟設定新工單

---

### 3.3 篩選查看特定站別或異常記錄

在「RECENT TESTS」右側面板可使用篩選功能：

| 篩選器 | 用法 |
|--------|------|
| Station 下拉 | 只看指定測試站的記錄 |
| Result 下拉 | 只看 PASS / FAIL / STOP |
| 快捷 Station 按鈕 | 點選 STA10、STA20… 快速切換 |
| Anomaly Priority | 開啟後，FAIL / STOP 記錄會排列到最上方 |
| 關鍵字搜尋 | 輸入 MAC Address 或失敗測項名稱快速查找 |

---

### 3.4 上傳資料到資料庫

> 此功能需要 DB 連線正常（OPS Strip DB 顯示綠色 READY）。

#### 首次設定 DB 連線

1. 在設備本機開啟 `http://localhost:8080`
2. 點選頁首的 **⚙️** 按鈕，開啟 Database Settings
3. 填入資料庫設定（由 PE Engineer 提供）：
   - Host、Port、DB Name、User、Password
4. 點 **Test Connection** 確認連線成功（出現綠色「✓ Success」通知）
5. 點 **Save** 儲存

#### 手動上傳

- 確認 WO 已設定、DB 已連線（READY）
- 點選 **Upload** 按鈕 → 出現「Upload started」通知
- 上傳進度顯示在 Upload 按鈕右側

#### 自動上傳

- 點選 **Auto Upload** 按鈕，切換為 **Auto Upload: ON**
- 系統會定期自動上傳新增記錄，無需手動操作
- 再次點選可關閉自動上傳

---

### 3.5 監控異常指標

| 情況 | 建議行動 |
|------|---------|
| YIELD < 90%（橘色） | 確認 FAIL 原因，通知 PE |
| YIELD < 80%（紅色閃爍） | 立即通報 PE，評估停線 |
| STOP 數量增加 | 確認各站測試狀態，通知 PE |
| RETEST RATE 超過 5% | 確認重測原因，通知 PE |
| 連線燈號紅色超過 1 分鐘 | 通知 PE 確認 Dashboard 服務狀態 |

---

## 4. PE Engineer 篇 — 系統設定與維護

### 4.1 Log 目錄切換

生產中可能需要切換 log 監控目錄（例如換 WO 或測試新站台）：

**方法一：快捷切換（推薦）**

- 畫面底部 Footer 有兩個快速切換按鈕：
  - **WO Root**：切換到 `/run/media/nvme0n1p1`（工單根目錄）
  - **Rawlogs**：切換到 `/run/media/nvme0n1p1/rawlogs`（預設 rawlogs）

**方法二：手動輸入路徑**

1. 在 Footer 的路徑輸入框填入目標路徑
2. 按 Enter 或點 **▶ Apply** 套用
3. OPS Strip 的 **RAWLOGS** 標籤應轉為綠色 READY

**方法三：圖形瀏覽**

1. 點選路徑輸入框旁的 📁 按鈕
2. 在 Select Directory 視窗中瀏覽到目標目錄
3. 點 **Select** 確認，系統自動套用

---

### 4.2 清除 Log 檔案（Sweep）

> **警告**：此操作會永久刪除目前 log 目錄下的所有 `.txt` 檔案，無法復原。

1. 確認 Footer 路徑輸入框顯示正確目錄
2. 點選 🧹 **Sweep** 按鈕
3. 確認對話框中點 **Delete** 確認
4. 通知訊息顯示「Sweep complete: N file(s) deleted」

> 建議在換工單前執行，避免新工單混入舊 log 資料。

---

### 4.3 系統健康確認

每日開工前建議確認以下狀態（可從任一瀏覽器查看）：

| 檢查項目 | 正常狀態 | 檢查方式 |
|---------|---------|---------|
| Dashboard 服務 | 可開啟網頁 | `http://192.168.100.1:8080` |
| WO ROOT | 綠色 READY | OPS Strip |
| RAWLOGS | 綠色 READY | OPS Strip |
| SSE 連線 | 綠燈常亮 | 右下角指示燈 |
| CPU 溫度 | < 70°C | Header TEMP |
| DB 連線 | 綠色 READY | OPS Strip DB |

---

### 4.4 Dashboard 服務管理（IMX8MP）

需要在設備上執行以下指令（SSH 進入設備）：

```bash
# 確認服務狀態
systemctl status pixi-dash.service --no-pager

# 重啟服務（設定變更後）
sudo systemctl restart pixi-dash.service

# 確認容器正在執行
docker ps --filter name=pixi-dash

# 查看即時 log（除錯用）
docker logs -f pixi-dash

# 強制刷新 WO 列表快取
curl -s 'http://localhost:8080/api/work-orders?refresh=1'
```

---

### 4.5 熱更新前端檔案

若修改了 `dashboard.js` / `style.css` / `index.html` 但不想重建 image：

```bash
# 在設備上執行
docker cp frontend/dashboard.js pixi-dash:/app/frontend/dashboard.js
docker cp frontend/style.css    pixi-dash:/app/frontend/style.css
docker cp frontend/index.html   pixi-dash:/app/frontend/index.html
docker restart pixi-dash
```

更新後，讓遠端瀏覽器強制重整（**Ctrl+Shift+R**）以清除快取。

---

### 4.6 存取權限設計

| 功能 | 本機 (localhost:8080) | LAN 遠端瀏覽器 |
|------|----------------------|---------------|
| 查看 Dashboard 資料 | ✓ | ✓ |
| 修改 WO / QTY | ✓ | ✗（鎖定） |
| 修改 Log 目錄 | ✓ | ✗（鎖定） |
| Sweep 清除 log | ✓ | ✗（鎖定） |
| DB Settings | ✓ | ✗（鎖定） |
| Upload / Auto Upload | ✓ | ✗（鎖定） |

---

## 5. Real-time Log Splitter 使用教學

> **Log Splitter** 是一支 Windows 桌面程式（`tn_log_splitter.exe`），負責把設備上的 rawlogs 依站台分類，複製到 PC 本地端方便分析。

### 5.1 程式啟動

1. 雙擊 `tn_log_splitter.exe`（或開發版執行 `python realtime_splitter_app.py`）
2. 程式預設為**淺色主題**。點選右上角 🌙 按鈕可切換深色主題
3. 點選左上角 **▲/▼** 按鈕可收合/展開設定面板

---

### 5.2 介面說明

```
┌──────────────────────────────────────────────────────┐
│  tn_log  PIXI Modules Log Splitter  ● [IDLE]  ☀ ▲   │  ← Header
├──────────────────────────────────────────────────────┤
│ ┌─ Config ─────────────────────────────────────────┐ │
│ │ SRC  [root@192.168.100.1:/run/media/nvme0n1p1/] 📁│ │  ← 來源路徑
│ │ DST  [C:\TestLogs\]                           📁  │ │  ← 目標路徑
│ │ STA  [Station: 10 ▼]   Interval [60] sec         │ │  ← 站別/間隔
│ │          [🔍 SSH Test]  [▶ Start]  [■ Stop]       │ │
│ └──────────────────────────────────────────────────┘ │
├──────────────────────────────────────────────────────┤
│  STATUS: 0 copied  0 skipped  0 failed  Next: 45s    │
├──────────────────────────────────────────────────────┤
│  [Split Log]                    [Upload Feed]        │
└──────────────────────────────────────────────────────┘
```

---

### 5.3 設定步驟

#### Step 1：設定來源路徑（SRC）

- 格式：`user@host:/remote/path/`
- 預設：`root@192.168.100.1:/run/media/nvme0n1p1/rawlogs/`
- 代表：SSH 連線到 `192.168.100.1`，讀取 `/run/media/nvme0n1p1/rawlogs/` 下的 log

> 如果 rawlogs 在設備其他位置，修改 `/rawlogs/` 部分即可。

#### Step 2：設定目標路徑（DST）

- 點選 📁 按鈕瀏覽選擇本地資料夾
- 例如：`C:\TestLogs\5101-260129012\`
- 建議每個工單建立獨立子資料夾

#### Step 3：選擇 Station（STA）

- 從下拉選單選擇站別：10 / 20 / 30 / 40 / 50 / 60 / 70 / 80
- 選擇後，log 檔會自動分類到 `DST\STA{站別}\` 子資料夾

#### Step 4：設定掃描間隔（Interval）

- 預設 60 秒掃描一次
- 建議值：生產中 30~60 秒；分析用 120~300 秒

#### Step 5：測試 SSH 連線

1. 點選 **🔍 SSH Test** 按鈕
2. 等待連線測試結果（約 3~10 秒）
3. LED 指示燈：
   - 🟢 綠色 = SSH 連線成功
   - 🔴 紅色 = 連線失敗（確認 IP / SSH Key 設定）
4. 下方 Split Log 面板會顯示詳細診斷訊息

> **首次使用**：程式會自動嘗試使用本機 SSH Key（`~/.ssh/id_rsa` 等）。若尚未設定 SSH Key 信任，請聯絡 PE Engineer 執行 `ssh-copy-id`。

---

### 5.4 啟動與停止

**啟動：** 點選 **▶ Start** 按鈕
- 程式狀態指示燈從灰色（IDLE）變為綠色（WATCHING）
- 等待第一次掃描（立即執行第一輪）
- Header 顯示正在監控的 Station ID

**執行中：**
- 狀態指示燈為橘色（BUSY）代表正在複製檔案
- Status 列顯示：已複製/已跳過/失敗 的檔案數
- `Next: Xs` 顯示距離下次掃描的倒數秒數

**停止：** 點選 **■ Stop** 按鈕
- 等待目前正在進行的複製完成後停止

---

### 5.5 Split Log 面板（日誌）

下方 **Split Log** 面板即時顯示複製進度與錯誤訊息：

| 訊息範例 | 代表意義 |
|---------|---------|
| `✓ Copied: ABC123.txt → STA10/` | 成功複製 |
| `- Skipped: ABC123.txt (exists)` | 檔案已存在，跳過 |
| `✗ Failed: SSH error` | SSH 連線中斷 |
| `[Scan] Found 15 new files` | 本輪找到 15 個新檔案 |

---

### 5.6 設定自動儲存

Log Splitter 使用 Windows Registry 自動儲存設定（`QSettings`）：
- 關閉後重開，SRC / DST / Station / Interval 都會自動還原
- 不需要手動儲存

---

### 5.7 PE Engineer 操作注意事項

| 項目 | 說明 |
|------|------|
| SSH Key 設定 | 建議使用 `ssh-copy-id root@192.168.100.1` 設定無密碼登入 |
| 多站台同時監控 | 開啟多個程式視窗，分別設定不同 Station 與 DST 子資料夾 |
| 網路中斷自動重連 | 每次掃描都會重新建立 SSH 連線，無需手動重啟 |
| 首次連線 host key | 可能出現 SSH host key 驗證提示，在 Split Log 面板查看診斷訊息 |

---

## 6. 常見狀況處理

### Dashboard 相關

| 症狀 | 可能原因 | 處理方式 |
|------|---------|---------|
| 畫面顯示「0 筆資料」 | Log 目錄設定錯誤 | Footer 確認 LOG DIR 路徑，點 **▶ Apply** |
| WO PATH 顯示紅色 | WO 目錄不存在於 NVMe | 確認 WO 號碼正確，或 NVMe 是否掛載 |
| OPS Strip 全部橘色 LOCKED | 從遠端瀏覽器連入 | 改用設備本機 `http://localhost:8080` |
| SSE 連線燈號持續紅色 | Dashboard 服務異常 | PE: `systemctl status pixi-dash.service` |
| YIELD 閃爍紅色 | 良率低於 80% | 立即通報 PE，確認各站測試狀態 |
| Upload 按鈕無法點擊 | DB 未連線或 WO 未設定 | 確認 OPS Strip DB 狀態與 WO 選擇 |
| 工單重開後 WO/QTY 消失 | Config 未持久化 | 請 PE 確認 Docker volume 掛載設定 |

### Log Splitter 相關

| 症狀 | 可能原因 | 處理方式 |
|------|---------|---------|
| SSH Test 失敗（紅色 LED） | IP 錯誤或 SSH Key 未授權 | 確認 SRC 路徑；聯絡 PE 設定 ssh-copy-id |
| 狀態一直顯示 IDLE | 未點 Start | 點 **▶ Start** 按鈕 |
| 複製後本地找不到檔案 | DST 路徑設定有誤 | 確認 DST 路徑是否存在；檢查磁碟空間 |
| 所有檔案都顯示 Skipped | 檔案已在目標資料夾 | 正常現象；只有新檔案才會複製 |
| 程式啟動後 SRC 路徑是空的 | 第一次使用 | 手動填入 `root@192.168.100.1:/run/media/nvme0n1p1/rawlogs/` |

---

## 附錄：快速參考

### Dashboard 網址
| 環境 | 網址 |
|------|------|
| 設備本機 | `http://localhost:8080` |
| 區網遠端 | `http://192.168.100.1:8080`（IP 依現場） |

### 顏色含義一覽
| 顏色 | 系統意義 |
|------|---------|
| 🟢 綠色 | 正常 / PASS / 連線 OK |
| 🔴 紅色 | 異常 / FAIL / 連線中斷 |
| 🟠 橘色 | 警示 / STOP / 需注意 |
| 🔵 藍色 | 資訊 / 進度 / 一般狀態 |

### KPI 正常範圍（參考值）
| KPI | 正常 | 警示 | 緊急 |
|-----|------|------|------|
| YIELD | ≥ 90% | 80~90% | < 80% |
| RETEST RATE | < 3% | 3~10% | > 10% |
| CPU 使用率 | < 60% | 60~80% | > 80% |
| CPU 溫度 | < 60°C | 60~70°C | > 70°C |

---

*文件維護：PE Engineer Team*  
*最後更新：2026-05-08*
