# PIXI Modules MP Monitoring DashBOARD — 啟動說明

> 所有指令皆在專案根目錄下執行：
> ```
> cd C:\Users\lance.tn\TN_Projects\Solo_PIXI_MP_RealTime_DashBoard
> ```

---

## 方法一：直接用 Python 執行（最快）

### 步驟

```powershell
# 1. 安裝依賴（第一次才需要）
pip install -r requirements.txt

# 2. 啟動伺服器
python -m uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```

啟動後開啟瀏覽器：**http://localhost:8080**

> `--reload` 旗標可讓程式碼修改後自動重啟，開發時使用；正式環境請移除。

---

## 方法二：Docker Compose（推薦正式部署）

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

### Volume 說明

| 容器路徑 | 對應本機路徑 | 說明 |
|----------|-------------|------|
| `/app/rawlogs` | `./rawlogs` | Log 檔目錄（唯讀） |
| `/app/config` | `./config` | 設定檔目錄（唯讀） |

---

## 方法三：純 Docker（不使用 Compose）

```powershell
# 1. 建置 image
docker build -t pixi-dashboard .

# 2. 執行容器（掛載 rawlogs 目錄）
docker run -p 8080:8080 -v "${PWD}\rawlogs:/app/rawlogs:ro" pixi-dashboard

# 背景執行
docker run -d -p 8080:8080 -v "${PWD}\rawlogs:/app/rawlogs:ro" --name pixi-dash pixi-dashboard

# 停止
docker stop pixi-dash
```

啟動後開啟瀏覽器：**http://localhost:8080**

---

## 常見問題排解

| 症狀 | 原因 | 解法 |
|------|------|------|
| `ModuleNotFoundError` | 套件未安裝 | `pip install -r requirements.txt` |
| Docker build 失敗 | Docker Desktop 未啟動 | 先開啟 Docker Desktop |
| `address already in use` | Port 8080 已被佔用 | 改用其他 port：`--port 8081` / `-p 8081:8080` |
| 畫面顯示「0筆資料」 | rawlogs 路徑設定錯誤 | 在 UI 右上角點 **Browse** 選取正確目錄 |
| SSE 連線燈號一直紅色 | 伺服器未啟動或防火牆阻擋 | 確認伺服器正常運行，檢查防火牆設定 |

---

## 執行測試

```powershell
python -m pytest tests/ -v
```

---

*最後更新：2026-05-03*
