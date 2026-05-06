# PIXI Modules MP Monitoring DashBOARD — 啟動說明

> 本專案有兩個使用情境：
> - **開發環境（Windows PC）**：直接用 Python 或 Docker Desktop 執行。
> - **正式部署（IMX8MP 設備，Linux）**：用純 Docker 指令在設備上執行。

---

## 方法一：直接用 Python 執行（開發用，最快）

> 在專案根目錄執行：
> ```
> cd C:\Users\lance.tn\TN_Projects\Solo_PIXI_MP_RealTime_DashBoard
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
| `/app/config` | `./config` | rw | 設定檔目錄 |
| `/run/media/nvme0n1p1` | `/run/media/nvme0n1p1` | rw | NVMe 掛載根目錄（含 WO 目錄與 rawlogs） |

---

## 方法三：純 Docker（IMX8MP 正式部署）

在目標設備（Linux）上執行以下指令。

### 3-1 建置 image

```bash
# 進入專案目錄
cd /home/Solo_PIXI_MP_RealTime_DashBoard

# 建置 image
docker build -t pixi-dashboard .
```

### 3-2 啟動容器（完整掛載版）

```bash
docker run -d \
  --restart unless-stopped \
  -p 8080:8080 \
  -v /run/media/nvme0n1p1/rawlogs:/app/rawlogs:rw \
  -v /run/media/nvme0n1p1:/run/media/nvme0n1p1:rw \
  --name pixi-dash \
  pixi-dashboard
```

> **注意：兩個 `-v` 都必須掛載。**
> - 第一個：將 rawlogs 目錄映射到容器內的 `/app/rawlogs`（App 預設 log 路徑）。
> - 第二個：將整個 NVMe 根目錄映射到容器內，讓 WO 工單下拉掃描 `/run/media/nvme0n1p1` 時能找到子目錄（如 `5101-260100001`）。

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

#### ▶ 完整重建 image 並重新部署（code 有更新時）
```bash
# 1. 停止並移除舊容器
docker stop pixi-dash && docker rm pixi-dash

# 2. 重新建置 image（進入專案目錄後執行）
cd /home/Solo_PIXI_MP_RealTime_DashBoard
docker build -t pixi-dashboard .

# 3. 重新啟動容器
docker run -d \
  --restart unless-stopped \
  -p 8080:8080 \
  -v /run/media/nvme0n1p1/rawlogs:/app/rawlogs:rw \
  -v /run/media/nvme0n1p1:/run/media/nvme0n1p1:rw \
  --name pixi-dash \
  pixi-dashboard
```

#### ▶ 完全清除（包含舊 image，徹底重來）
```bash
docker stop pixi-dash && docker rm pixi-dash
docker rmi pixi-dashboard
cd /home/Solo_PIXI_MP_RealTime_DashBoard
docker build -t pixi-dashboard .
docker run -d \
  --restart unless-stopped \
  -p 8080:8080 \
  -v /run/media/nvme0n1p1/rawlogs:/app/rawlogs:rw \
  -v /run/media/nvme0n1p1:/run/media/nvme0n1p1:rw \
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
```

---

## 常見問題排解

| 症狀 | 原因 | 解法 |
|------|------|------|
| `ModuleNotFoundError` | 套件未安裝 | `pip install -r requirements.txt` |
| Docker build 失敗 | Docker 未啟動 | 先啟動 Docker |
| `address already in use` | Port 8080 已被佔用 | `docker stop pixi-dash` 或改用 `-p 8081:8080` |
| 畫面顯示「0 筆資料」 | rawlogs 路徑設定錯誤 | 在 UI 右上角點 **Browse** 選取正確目錄 |
| WO 下拉是空的 | NVMe 未掛載進容器 | 確認 `-v /run/media/nvme0n1p1:/run/media/nvme0n1p1:rw` 存在；執行 `curl localhost:8080/api/work-orders?refresh=1` 驗證 |
| SSE 連線燈號一直紅色 | 伺服器未啟動或防火牆阻擋 | 確認容器正常運行，檢查防火牆設定 |
| 遠端連入控制項反灰 | 安全機制：修改權限僅限 localhost | 在設備本機瀏覽器開啟 `http://localhost:8080` 操作 |

---

## 執行測試

```powershell
python -m pytest tests/ -v
```

---

*最後更新：2026-05-06*
