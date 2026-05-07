# Log Splitter 獨立執行檔 (Standalone App) 部署與設定 SOP

## 1. 程式部署 (Deploy)
*   請將 `Realtime_Log_Splitter.exe` 檔案複製到目標主機。
*   此執行檔已透過 PyInstaller 打包為單一檔案 (`--onefile`)，**不需要安裝 Python 或任何套件**，即可在 Windows 10/11 電腦上直接點擊執行。

## 2. 系統相依性要求 (System Requirements)
由於程式內部已將所有依賴套件（如通訊用的 `paramiko`, 介面用的 `PyQt5`）全部封裝打包，使用者在新的 Windows PC 上不需做複雜的系統環境設定。
您只需確保：
1. **Windows 10 或 Windows 11 作業系統**。
2. **區域網路連線**：確保執行程式的主機與產線設備（預設 IP `192.168.100.1`）處於同一個網路區段，且能互 Ping 通。

## 3. SSH 連線憑證 (如果需要金鑰)
*   程式內建透過 SSH 通道進行資料傳輸。
*   如果是使用帳密登入，程式的 SSH 通道可直接運作（建議在程式碼內或使用憑證來自動化）。
*   若設備強制使用 SSH Key，請將私鑰 (例如 `id_rsa`) 放置於這台電腦的預設 ssh 存放路徑（通常為 `C:\Users\<UserName>\.ssh\`）。

## 4. 疑難排解 (Troubleshooting)
*   **無法開啟程式**：部分防毒軟體（或 Windows Defender）可能會對 PyInstaller 打包的未簽章 exe 產生誤判並阻擋。如果被隔離或閃退，請將此執行檔手動加入防毒軟體的**白名單 (Exceptions)**。
*   **介面上的 SSH Test 呈現 Fail ✗**：
    1. 確認網線是否插妥，網路配置是否正確。
    2. 開啟 cmd，輸入 `ping 192.168.100.1`，確認是否有回應。
    3. 確認介面填寫的 DST 路徑格式是否正確，例如：`root@192.168.100.1:/run/media/nvme0n1p1/rawlogs/`。

## 5. 常見注意事項
*   當程式在背景進行 Log 分割與同步時，請勿任意關閉視窗或強行拔除網路線，以免資料中斷。
*   可隨時使用介面右上角的「**=**」按鈕來鎖定面板，防止產線作業人員誤觸參數設定。
