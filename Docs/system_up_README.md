# PIXI Modules MP Monitoring DashBOARD — 啟動說明

> 本專案有兩個使用情境：
> - **開發環境（Windows PC）**：直接用 Python 或 Docker Desktop 執行。
> - **正式部署（IMX8MP 設備，Linux）**：用純 Docker 指令在設備上執行。

---

## 方法一：直接用 Python 執行（開發用，最快）

> 在專案根目錄執行：
> ```
> cd D:\TN_Tool_Projects\Solo_PIXI_MP_RealTime_DashBoard
> ```

```powershell
# 1. 安裝依賴（第一次才需要）
pip install -r requirements.txt

# 2. 啟動伺服器
python -m uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```

啟動後開啟瀏覽器：**http://localhost:8080**

> `--reload` 旗標僅供開發時使用；正式環境請移除。

---

## 方法二：Docker Compose（Windows 開發用）

### 前置條件
- Docker Desktop 已安裝並**正在執行**

### 步驟

```powershell
# 建置 image 並啟動（前景，可看即時 log）
docker-compose up --build

# 建置 image 並背景執行
docker-compose up --build -d

# 查看即時 log
docker-compose logs -f

# 停止並移除容器
docker-compose down
```

啟動後開啟瀏覽器：**http://localhost:8080**

### Volume 說明（docker-compose.yml）

| 容器路徑 | 對應本機路徑 | 模式 | 說明 |
|----------|-------------|------|------|
| `/app/rawlogs` | `./rawlogs` | rw | Log 檔目錄 |
| `/app/config` | `./config` | rw | 設定檔目錄（mission.json 持久化） |
| `/run/media/nvme0n1p1` | `/run/media/nvme0n1p1` | rw | NVMe 掛載根目錄（含 WO 目錄與 rawlogs） |

---

## 方法三：純 Docker（IMX8MP 正式部署）

在目標設備（Linux）上執行以下指令。

> **架構說明**
> - `app/`（後端程式碼）與 `frontend/`（HTML / JS / CSS）是**建置時 bake 進 image**，不是 bind mount。
> - 只有 `config/`（設定持久化）、`rawlogs/`（日誌）、NVMe 根目錄 是執行時掛載的。
> - 更新程式碼有兩個途徑：
>   - **快速熱更新**（測試用）：`docker cp` + `docker restart`，不需重建 image。
>   - **正式更新**：`git pull` → `docker build` → 重新部署，讓新版永久生效。

### 3-1 建置 image

```bash
# 進入專案目錄
cd /home/Solo_PIXI_MP_RealTime_DashBoard

# 拉取最新程式碼
git pull

# 建置 image
docker build -t pixi-dashboard .
```

### 3-2 啟動容器（完整掛載版）

```bash
docker run -d \
  --restart unless-stopped \
  --network host \
  -v /home/Solo_PIXI_MP_RealTime_DashBoard/config:/app/config:rw \
  -v /run/media/nvme0n1p1/rawlogs:/app/rawlogs:rw \
  -v /run/media/nvme0n1p1:/run/media/nvme0n1p1:rw \
  -v /run/media/nvme0n1p1:/nvme0n1p1:rw \
  -v /proc:/host/proc:ro \
  -v /sys:/host/sys:ro \
  --name pixi-dash \
  pixi-dashboard
```

> **所有的 `-v` 都必須掛載。**
>
> | host 路徑 | 容器路徑 | 用途 |
> |-----------|----------|------|
> | `/home/.../config` | `/app/config` | mission.json 持久化（WO / QTY / LOG DIR） |
> | `/run/media/nvme0n1p1/rawlogs` | `/app/rawlogs` | App 預設 log 掃描路徑 |
> | `/run/media/nvme0n1p1` | `/run/media/nvme0n1p1` | WO 工單目錄掃描根目錄 |
> | `/run/media/nvme0n1p1` | `/nvme0n1p1` | 路徑別名（後端 browse API 白名單） |
> | `/proc` | `/host/proc` | 供系統資源監控抓取實體機資訊 (CPU/RAM) |
> | `/sys` | `/host/sys` | 供系統資源監控抓取實體機資訊 (溫度) |
>
> 註：採用 `--network host` 即可存取主機的實體網卡，無需 `-p 8080:8080` 映射。

### 3-3 維運操作

#### ▶ 停止容器
```bash
docker stop pixi-dash
```

#### ▶ 重新啟動已停止的容器（不重建 image）
```bash
docker start pixi-dash
```

#### ▶ 重啟容器（不重建 image，快速重開）
```bash
docker restart pixi-dash
```

#### ▶ 快速熱更新（code 有修改，不重建 image，測試用）

> 適合臨時驗證：修改後的檔案直接注入正在跑的容器，重啟生效。
> 正式上線仍建議走 3-4 完整重建流程。

```bash
# 1. 確認最新檔案已在 host 端（git pull 或 scp）
cd /home/Solo_PIXI_MP_RealTime_DashBoard

# 2. 注入更新的檔案到容器
docker cp app/main.py      pixi-dash:/app/app/main.py
docker cp frontend/dashboard.js pixi-dash:/app/frontend/dashboard.js
docker cp frontend/index.html   pixi-dash:/app/frontend/index.html

# 3. 重啟容器讓後端 Python 重新載入
docker restart pixi-dash

# 4. 驗證版本（前端 cache-bust 版本號是否正確）
curl -s http://localhost:8080/ | grep -o 'dashboard.js?v=[0-9]*'
```

> `frontend/` 檔案（JS / HTML / CSS）不需要重啟即可驗證，瀏覽器強制重整（Ctrl+Shift+R）即可；
> `app/main.py` 等 Python 後端修改**必須** `docker restart` 才會生效。

#### ▶ 完整重建 image 並重新部署（正式上線）

```bash
# 1. 停止並移除舊容器
docker stop pixi-dash && docker rm pixi-dash

# 2. 拉取最新程式碼
cd /home/Solo_PIXI_MP_RealTime_DashBoard
git pull

# 3. 重新建置 image
docker build -t pixi-dashboard .

# 4. 重新啟動容器（含掛載）
docker run -d \
  --restart unless-stopped \
  --network host \
  -v /home/Solo_PIXI_MP_RealTime_DashBoard/config:/app/config:rw \
  -v /run/media/nvme0n1p1/rawlogs:/app/rawlogs:rw \
  -v /run/media/nvme0n1p1:/run/media/nvme0n1p1:rw \
  -v /run/media/nvme0n1p1:/nvme0n1p1:rw \
  -v /proc:/host/proc:ro \
  -v /sys:/host/sys:ro \
  --name pixi-dash \
  pixi-dashboard
```

#### ▶ 完全清除（包含舊 image，徹底重來）

```bash
docker stop pixi-dash && docker rm pixi-dash
docker rmi pixi-dashboard
cd /home/Solo_PIXI_MP_RealTime_DashBoard
git pull
docker build -t pixi-dashboard .
docker run -d \
  --restart unless-stopped \
  --network host \
  -v /home/Solo_PIXI_MP_RealTime_DashBoard/config:/app/config:rw \
  -v /run/media/nvme0n1p1/rawlogs:/app/rawlogs:rw \
  -v /run/media/nvme0n1p1:/run/media/nvme0n1p1:rw \
  -v /run/media/nvme0n1p1:/nvme0n1p1:rw \
  -v /proc:/host/proc:ro \
  -v /sys:/host/sys:ro \
  --name pixi-dash \
  pixi-dashboard
```

### 3-4 常用維運指令

```bash
# 確認容器是否在跑
docker ps --filter name=pixi-dash

# 查看即時 log
docker logs -f pixi-dash

# 進入容器 shell（除錯用）
docker exec -it pixi-dash sh

# 確認 WO 目錄是否可見
docker exec pixi-dash ls /run/media/nvme0n1p1

# 強制刷新 WO 下拉快取
curl -s 'http://localhost:8080/api/work-orders?refresh=1'

# 確認 API 正常
curl -s 'http://localhost:8080/api/access'

# 確認路徑健康狀態（含 WO 查詢）
curl -s 'http://localhost:8080/api/path-health'
curl -s 'http://localhost:8080/api/path-health?wo=5101-260129012'

# 確認前端版本號
curl -s 'http://localhost:8080/' | grep -o 'dashboard.js?v=[0-9]*'
```

---

## 常見問題排解

| 症狀 | 原因 | 解法 |
|------|------|------|
| `ModuleNotFoundError` | 套件未安裝 | `pip install -r requirements.txt` |
| Docker build 失敗 | Docker 未啟動 | 先啟動 Docker |
| `address already in use` | Port 8080 已被佔用 | `docker stop pixi-dash` 或改用 `-p 8081:8080` |
| 畫面顯示「0 筆資料」 | rawlogs 路徑設定錯誤 | 在 UI 底部 LOG DIR 輸入正確路徑，按 **▶ Apply** |
| LOG DIR Browse 看不到 `/run/media/nvme0n1p1` | 舊版後端白名單或容器未重建 | 重新 build/redeploy 後執行 `curl -s 'http://localhost:8080/api/browse-dir?path=/run/media/nvme0n1p1'`，確認 `current` 回傳該路徑 |
| WO / QTY 重開後消失 | 未掛載 `/app/config`，`mission.json` 不持久 | 啟動容器時加入 `-v /home/Solo_PIXI_MP_RealTime_DashBoard/config:/app/config:rw` |
| WO 下拉是空的 | NVMe 未掛載進容器 | 確認 `-v /run/media/nvme0n1p1:/run/media/nvme0n1p1:rw` 存在；執行 `curl localhost:8080/api/work-orders?refresh=1` 驗證 |
| WO PATH 燈號顯示 MISSING 但 Upload 正常 | 舊版 `path_health` 未用 `_find_wo_dir()` | 更新 `app/main.py` 並 `docker cp` + `docker restart` |
| SCP 更新後畫面沒變 | `app/` 與 `frontend/` 是 baked image，SCP 只更新 host 端 | 用 `docker cp` 注入容器，再 `docker restart` |
| Auto Upload 按鈕顏色與狀態不同步 | 舊版混用 style.color 與 CSS class | 更新 `frontend/dashboard.js` 並 `docker cp` + 重整瀏覽器 |
| SSE 連線燈號一直紅色 | 伺服器未啟動或防火牆阻擋 | 確認容器正常運行，檢查防火牆設定 |
| 遠端連入控制項反灰 | 安全機制：修改權限僅限 localhost | 在設備本機瀏覽器開啟 `http://localhost:8080` 操作 |

---

## 執行測試

```powershell
python -m pytest tests/ -v
```

---

*最後更新：2026-05-07*
