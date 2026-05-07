# i.MX8M Plus (tep-imx8mp) 系統優化指南

**平台**：NXP i.MX8M Plus SoC，Yocto Linux + Wayland + systemd  
**最後更新**：2026-05-07  
**適用版本**：pixi-dashboard deploy ≥ commit `066bd88`

---

## 一、已完成的優化項目

### 1.1 補上缺失的 systemd 服務單元

**問題**：`chromium-kiosk.service` 宣告 `After=pixi-dash.service`，但 `pixi-dash.service` 不存在，導致容器從不自動啟動。

**修復**：建立 `/etc/systemd/system/pixi-dash.service`

```ini
[Unit]
Description=PIXI Dashboard Container
Requires=docker.service
After=docker.service network-online.target local-fs.target
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
TimeoutStartSec=120
ExecStartPre=/bin/sh -c 'for i in $(seq 1 90); do [ -d /run/media/nvme0n1p1 ] && exit 0; sleep 1; done; exit 1'
ExecStart=/usr/bin/docker start pixi-dash
ExecStop=/usr/bin/docker stop -t 20 pixi-dash

[Install]
WantedBy=multi-user.target
```

**部署位置**：`deploy/systemd/pixi-dash.service` → `/etc/systemd/system/pixi-dash.service`

---

### 1.2 解決 2 分鐘開機等待瓶頸

**根本原因鏈**：

```
eth1 (NO-CARRIER，無接線)
  → systemd-networkd 將其列為托管介面 (20-eth1.network)
    → systemd-networkd-wait-online 等待「所有」托管介面 configured
      → 卡滿 120s timeout 才放棄（且狀態為 FAILED）
        → docker.service (After=network-online.target) 被完全封鎖
          → pixi-dash.service / chromium-kiosk.service 跟著延誤
```

**修復 A：wait-online drop-in**

路徑：`/etc/systemd/system/systemd-networkd-wait-online.service.d/any.conf`

```ini
[Service]
ExecStart=
ExecStart=/usr/lib/systemd/systemd-networkd-wait-online --any --timeout=20
```

`--any` 的語意：只要**任一**托管介面達到 routable 狀態即視為成功。  
eth0 通常在開機後 ~5s 取得 IP，wait-online 因此從 **2m35s 失敗** → **6s 成功**。

**修復 B：docker.service drop-in（belt-and-suspenders）**

路徑：`/etc/systemd/system/docker.service.d/no-network-online.conf`

```ini
[Unit]
After=
After=docker.socket containerd.service firewalld.service
Wants=
```

Docker daemon 只需要 kernel 網路 socket 層，不需要等待 LAN 連線就緒。  
此 drop-in 移除對 `network-online.target` 的硬依賴，確保即使 wait-online 再度失敗，docker 也能如期啟動。

**部署位置**：
- `deploy/systemd/wait-online-any.conf`
- `deploy/systemd/docker-no-network-online.conf`

**效果對比**：

| 指標 | 優化前 | 優化後 |
|------|--------|--------|
| 總開機時間 | > 2 分鐘 | ~20 秒 |
| `systemd-networkd-wait-online` | 2m35s（FAILED） | 6s（SUCCESS） |
| `docker.service` 啟動 | 被封鎖 | 1.68s |
| API `/api/snapshot` 可用 | 不啟動 | 開機後 ~20s |

---

### 1.3 停用閒置系統服務

以下服務在此平台的應用場景中無使用，全數 `systemctl disable`：

| 服務 | 原因 |
|------|------|
| `ofono.service` | 行動電話/SIM 管理，無 GSM 模組，開機佔 ~1.9s |
| `bluetooth.service` | 藍牙，工業儀表板無需求 |
| `wpa_supplicant.service` | WiFi 認證，設備走有線 eth0，無 WiFi 介面 |
| `avahi-daemon.service` | mDNS/Bonjour，工廠內網不使用 |
| `atd.service` | `at` 指令排程器，非 cron，無使用 |
| `neard.service` | NFC，原本就是 inactive(dead) |
| `nfs-statd.service` | NFS 鎖定服務，無 `/etc/exports`，inactive |
| `rpcbind.service` | NFS portmapper，無 NFS 使用 |
| `upower.service` | 電源管理 daemon，無電池 |

**執行指令**（已套用，僅供記錄）：
```bash
systemctl stop ofono bluetooth wpa_supplicant avahi-daemon atd neard nfs-statd rpcbind upower
systemctl disable ofono bluetooth wpa_supplicant avahi-daemon atd neard nfs-statd rpcbind upower
```

---

## 二、目前剩餘的優化候選項目

### 2.1 網路管理器二擇一（connman vs systemd-networkd）

**現況**：系統同時運行 `connman.service` 和 `systemd-networkd.service`，兩者皆在管理網路介面，存在潛在衝突。

**架構說明**：
- `connman`：管理 eth0（上行 LAN），`main.conf` 中已將 eth1 列入黑名單
- `systemd-networkd`：管理 eth1（`20-eth1.network`，設定 `192.168.100.1/24`，作為內部 DHCP server 的靜態 IP）
- `dnsmasq`：綁定 eth1 interface，提供 `192.168.100.2–253` DHCP 範圍

**建議方案**：若 eth1 作為 DHCP server 對下接其他裝置的功能仍需保留，維持目前架構（connman 管 eth0，networkd 管 eth1）。  
若 eth1 DHCP server 功能確認廢棄，可：
1. 移除 `/etc/systemd/network/20-eth1.network`
2. 停用 `systemd-networkd.service` 和 `dnsmasq.service`
3. 僅留 `connman` 管理所有有線介面

### 2.2 可再評估停用的服務

| 服務 | 條件 |
|------|------|
| `dnsmasq.service` | 確認 eth1 DHCP server 功能廢棄後停用 |
| `connman.service` | 確認改用純 `systemd-networkd` 管理後停用 |
| `firmwared.service` | 確認 ISP / camera firmware 載入不再需要後停用 |
| `crond.service` | 確認 `/etc/cron.d/`、`crontab -l` 均為空後停用 |
| `psplash*.service` | 若不需要開機 splash 動畫可全數停用，節省 ~0.2s |

### 2.3 enable_lanbypass_eth.service（開機 blame #1，6.1s）

目前 `systemd-analyze blame` 第一名為此服務（6.1s）。若此服務為硬體 LAN bypass 功能（某些工業板必要），應保留。  
**建議**：確認該 service 的 `ExecStart` 腳本內容，若可並行化（加 `Type=oneshot` 且無 `Before=` 關鍵依賴），考慮加入 `&` 背景執行或調整 `After=` 順序。

### 2.4 systemd-random-seed.service（開機 blame，~2.6s）

在 embedded 系統上，`/var/lib/systemd/random-seed` 首次讀取較慢（等待 entropy pool）。  
可考慮在 Yocto image 中加入 `haveged` 或啟用 `CONFIG_HW_RANDOM_IMX_RNGC` 核心 entropy source。

---

## 三、開機時序參考（優化後）

```
graphical.target @16.56s
└─ chromium-kiosk.service @12.43s +4.13s
   └─ pixi-dash.service @11.46s +0.94s
      └─ docker.service @9.76s +1.68s
         └─ network-online.target @9.73s
            └─ systemd-networkd-wait-online @4.03s +5.70s  ← 原本 2m35s
               └─ systemd-networkd @3.34s +0.66s
                  └─ network-pre.target / iptables
                     └─ basic.target @2.97s
```

---

## 四、部署檔案清單

| 本地路徑 | 遠端路徑 | 說明 |
|----------|----------|------|
| `deploy/systemd/pixi-dash.service` | `/etc/systemd/system/pixi-dash.service` | Docker 容器開機啟動 |
| `deploy/systemd/wait-online-any.conf` | `/etc/systemd/system/systemd-networkd-wait-online.service.d/any.conf` | wait-online 改為 --any 模式 |
| `deploy/systemd/docker-no-network-online.conf` | `/etc/systemd/system/docker.service.d/no-network-online.conf` | docker 移除 network-online 依賴 |

部署後執行：
```bash
systemctl daemon-reload
systemctl enable pixi-dash.service
systemctl reboot
```

驗證指令：
```bash
systemd-analyze time
systemd-analyze blame | head -10
docker ps
curl -sS http://127.0.0.1:8080/api/snapshot | head -c 200
```
