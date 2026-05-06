# Log Splitter UI — 多开同时运行指南

## 📖 使用场景

同一台电脑上同时运行多个 Log Splitter UI 实例，分别处理不同测试站点的日志文件，并同时上传到同一个远端 Dashboard 服务器。

---

## ✅ 支持的并发特性

### 1. **文件名自动区分**
每个实例选择不同的 **STATION ID**（10/20/30.../80），生成的文件名会自动包含站点前缀：

```
STA10_20260506_143022_001F7B6CB810_001F7B6CB811_PASS.txt
STA20_20260506_143025_001F7B6CB820_001F7B6CB821_PASS.txt
STA30_20260506_143030_001F7B6CB830_001F7B6CB831_PASS.txt
```

**不同站点的文件名永远不会冲突** ✓

### 2. **防重复上传机制**
- 上传前检查远端文件是否存在
- 已存在的文件自动跳过，不会覆盖
- 支持多个实例同时上传到同一 DST 目录

### 3. **独立配置存储**
- 每个实例的设置（SRC/OUT/STA/DST）独立保存
- 使用 Windows Registry 存储，不会互相干扰
- 重启程序自动恢复上次配置

---

## 🚀 多开操作步骤

### **步骤 1：启动第一个实例（Station 10）**

```powershell
# 终端 1
cd D:\TN_Tool_Projects\Solo_PIXI_MP_RealTime_DashBoard\Reference_app
python realtime_splitter_app.py
```

配置：
- **SRC**: `D:\测试数据\Station10\Log_ALL.txt`
- **OUT**: `D:\输出\Station10`
- **STA**: `10`
- **DST**: `root@10.20.31.106:/run/media/nvme0n1p1/rawlogs/`
- 点击 **Test** 确认 SSH 连接 ✅
- 点击 **💾** 保存配置
- 点击 **▶ Start** 开始监控

---

### **步骤 2：启动第二个实例（Station 20）**

```powershell
# 终端 2（新开一个 PowerShell 窗口）
cd D:\TN_Tool_Projects\Solo_PIXI_MP_RealTime_DashBoard\Reference_app
python realtime_splitter_app.py
```

配置：
- **SRC**: `D:\测试数据\Station20\Log_ALL.txt`
- **OUT**: `D:\输出\Station20`  ← **不同于 Station 10**
- **STA**: `20`  ← **不同的站点 ID**
- **DST**: `root@10.20.31.106:/run/media/nvme0n1p1/rawlogs/`  ← **可以相同**
- 点击 **Test** 确认 SSH 连接 ✅
- 点击 **💾** 保存配置
- 点击 **▶ Start** 开始监控

---

### **步骤 3：重复启动更多实例（Station 30/40/...）**

每个新实例：
1. 新开一个 PowerShell 窗口
2. 运行 `python realtime_splitter_app.py`
3. 配置不同的 **SRC**、**OUT**、**STA**
4. **DST** 可以使用相同的远端路径
5. 保存并启动

---

## ⚙️ 配置建议

### **必须不同的设置**

| 项目 | 说明 | 示例 |
|------|------|------|
| **STA** | 站点 ID | 10, 20, 30, ... |
| **SRC** | 源文件路径 | 每个站点有独立的 Log_ALL.txt |
| **OUT** | 本地输出目录 | 避免多个实例写入同一目录 |

### **可以相同的设置**

| 项目 | 说明 |
|------|------|
| **DST** | 远端目标路径 | 所有实例可共享同一个远端目录 |
| **Poll Interval** | 轮询间隔 | 推荐使用默认 60 秒 |

---

## 🛡️ 并发安全保障

### **1. 本地文件冲突**
✅ **已解决** - 每个实例使用不同的 OUT 目录，不会互相干扰

### **2. 远端文件覆盖**
✅ **已解决** - 文件名包含 STATION ID 前缀，不同站点文件名不同

### **3. SFTP 上传冲突**
✅ **已解决** - paramiko 支持并发连接，每个实例独立的 SSH 会话

### **4. 同名文件重传**
✅ **已解决** - 上传前检查远端文件存在性，已存在则跳过

---

## 📊 Dashboard 显示

远端 Dashboard 会正确识别和显示所有站点的数据：

| Station | Time | MAC1 | MAC2 | Result | Duration |
|---------|------|------|------|--------|----------|
| **STA10** | 14:30:22 | 001F7B6CB810 | 001F7B6CB811 | PASS | 01:15.3 |
| **STA20** | 14:30:25 | 001F7B6CB820 | 001F7B6CB821 | PASS | 01:14.8 |
| **STA30** | 14:30:30 | 001F7B6CB830 | 001F7B6CB831 | PASS | 01:16.1 |

**Recent TESTS** 表格会按时间顺序显示所有站点的测试记录。

---

## 🔍 故障排查

### **问题 1：SSH 连接失败**
- **原因**：网络连接问题或 SSH 服务未启动
- **解决**：每个实例点击 **Test** 按钮确认连接
- **预期**：LED 灯显示绿色 ✅

### **问题 2：文件未上传**
- **检查**：Activity Log 是否显示 "SFTP ... " 或 "SSH auth failed"
- **解决**：确认 DST 路径格式正确：`user@host:/path`

### **问题 3：Dashboard 显示重复数据**
- **原因**：可能多个实例使用了相同的 STATION ID
- **解决**：确保每个实例的 STA 设置不同

### **问题 4：程序重启后配置丢失**
- **解决**：每次修改配置后点击 **💾** 保存按钮
- **验证**：重启程序，配置应自动恢复

---

## 💡 最佳实践

### ✅ **推荐做法**

```
实例 1:
  STA = 10
  SRC = D:\Station10\Log_ALL.txt
  OUT = D:\Output\Station10
  DST = root@10.20.31.106:/run/media/nvme0n1p1/rawlogs/

实例 2:
  STA = 20
  SRC = D:\Station20\Log_ALL.txt
  OUT = D:\Output\Station20
  DST = root@10.20.31.106:/run/media/nvme0n1p1/rawlogs/  ← 相同

实例 3:
  STA = 30
  SRC = D:\Station30\Log_ALL.txt
  OUT = D:\Output\Station30
  DST = root@10.20.31.106:/run/media/nvme0n1p1/rawlogs/  ← 相同
```

### ❌ **避免做法**

```
# ❌ 错误：两个实例使用相同的 OUT 目录
实例 1: OUT = D:\Output
实例 2: OUT = D:\Output  ← 冲突！

# ❌ 错误：两个实例使用相同的 STATION ID
实例 1: STA = 10
实例 2: STA = 10  ← 会产生相同文件名！

# ❌ 错误：两个实例监控相同的 SRC 文件
实例 1: SRC = D:\Log_ALL.txt
实例 2: SRC = D:\Log_ALL.txt  ← 没有意义，应该分开
```

---

## 📌 快速检查清单

启动多个实例前，确认：

- [ ] 每个实例选择了**不同的 STATION ID**（10/20/30...）
- [ ] 每个实例使用**不同的 OUT 目录**
- [ ] 每个实例监控**不同的 SRC 文件**（各站点的 Log_ALL.txt）
- [ ] 所有实例可以使用**相同的 DST 路径**（远端目录）
- [ ] 每个实例都点击了 **Test** 按钮确认 SSH 连接 ✅
- [ ] 每个实例都点击了 **💾** 保存配置
- [ ] 远端 Dashboard 已启动并可访问

---

## 🎯 总结

✅ **支持多开**：同一台电脑可同时运行 8 个实例（Station 10-80）  
✅ **自动防冲突**：文件名包含站点 ID，不会覆盖  
✅ **并发上传**：多个实例可同时上传到同一远端目录  
✅ **独立配置**：每个实例的设置独立保存和恢复  

**推荐配置模式**：不同 STA + 不同 OUT + 相同 DST = 完美并发 🚀

---

*最后更新：2026-05-06*
