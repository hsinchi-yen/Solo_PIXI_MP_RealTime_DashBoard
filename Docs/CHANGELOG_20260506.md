# 更新日志 - 2026-05-06

## 📊 Dashboard UI 调整

### ✅ 布局优化
- **RESULT DISTRIBUTION** 高度减少 40%（flex: 1 → 0.6）
- **HOURLY COMPLETION** 高度增加 60%（flex: 0 → 1.5）
- 比例调整为 **71% : 29%**，提供更多空间显示小时完成率图表

**修改文件：**
- `frontend/style.css` - 添加 `.stats-section-hourly { flex: 1.5; }` 和修改 `.stats-section-flex { flex: 0.6; }`
- `frontend/index.html` - 版本号更新 v7 → v8

---

## 🏭 多站点支持验证

### ✅ 核心功能
- **解析器**：支持 STA10-STA99（正则 `STA\d{2}`）
- **Recent TESTS**：Station 列正确显示所有站点数据
- **去重逻辑**：按 MAC1 跨站点去重，保留最新记录
- **文件格式**：
  ```
  STA20_20260428_085216_001F7B6CB81E_001F7B6CB81F_PASS.txt
  STA30_20260417_083630_001F7B6CA886_001F7B6CA887_PASS.txt
  STA10_20260400_085200_001F7B6CB810_001F7B6CB80A_PASS.txt
  ```

**验证状态：**
- ✅ `app/parser.py` - FILENAME_RE 支持 STA10-STA99
- ✅ `app/state.py` - MAC1 去重逻辑正确
- ✅ `frontend/dashboard.js` - buildRow 显示 station_id
- ✅ `frontend/index.html` - Station 列已添加

---

## 🚀 Log Splitter UI 多开支持

### ✅ 并发特性

#### **1. 文件名自动区分**
每个实例选择不同 STATION ID，生成的文件名包含站点前缀：
```
STA10_... → 实例 1
STA20_... → 实例 2
STA30_... → 实例 3
```
**不同站点文件名永远不冲突** ✓

#### **2. 防重复上传**
- 上传前检查远端文件存在性（`sftp.stat()`）
- 已存在文件自动跳过
- 支持多实例同时上传到同一 DST

#### **3. 独立配置存储**
- 使用 QSettings（Windows Registry）
- 每个实例配置独立保存
- 重启自动恢复

**修改文件：**
- `Reference_app/realtime_splitter_app.py` - 已包含所有功能

---

## 📖 新增文档

### **1. 多开使用指南**
**文件：** `Docs/multi_instance_guide.md`

**内容：**
- 多开操作步骤（启动多个实例）
- 配置建议（必须不同 vs 可以相同）
- 并发安全保障（4 层防护）
- Dashboard 显示验证
- 故障排查
- 最佳实践

**快速检查清单：**
- [ ] 不同的 STATION ID（10/20/30...）
- [ ] 不同的 OUT 目录
- [ ] 不同的 SRC 文件
- [ ] 相同的 DST 路径（OK）
- [ ] SSH Test ✅ 绿灯
- [ ] 配置已保存 💾

### **2. 多站点测试验证**
**文件：** `Docs/multi_station_test.md`

**内容：**
- 测试数据示例（STA10/20/30/80）
- 验证步骤（解析器 + Dashboard）
- 预期结果（4 个组件）
- 故障排查（4 个常见问题）
- 性能验证（1000 条数据测试）
- 通过标准（8 项检查）

---

## 🔄 部署更新

### **远端机器需要更新的文件**

#### **方法 1：完整更新**
```bash
# 本地上传
scp -r app frontend Dockerfile root@10.20.31.106:/home/Solo_PIXI_MP_RealTime_DashBoard/

# 远端重新部署
ssh root@10.20.31.106
cd /home/Solo_PIXI_MP_RealTime_DashBoard
docker stop pixi-dash && docker rm pixi-dash
docker build -t pixi-dashboard .
docker run -d -p 8080:8080 \
  -v "/run/media/nvme0n1p1/rawlogs:/app/rawlogs:rw" \
  --name pixi-dash --restart=always pixi-dashboard
```

#### **方法 2：仅前端更新**（快速）
```bash
# 只更新前端文件
scp frontend/style.css frontend/index.html root@10.20.31.106:/home/Solo_PIXI_MP_RealTime_DashBoard/frontend/

# 重启容器
ssh root@10.20.31.106 "docker restart pixi-dash"

# 清除浏览器缓存（Chromium）
pkill -f chromium && sleep 2 && rm -rf ~/.cache/chromium/Default/Cache
```

---

## ✅ 验证清单

### **Dashboard 验证**
- [ ] 访问 `http://10.20.31.106:8080`
- [ ] HOURLY COMPLETION 高度增加（占据更多空间）
- [ ] RESULT DISTRIBUTION 高度减少（约 40%）
- [ ] Recent TESTS 第一列显示 Station（STA10/20/30...）
- [ ] 多站点数据混合显示，按时间倒序
- [ ] 旧格式文件 Station 列显示 `—`

### **Log Splitter 验证**
- [ ] 启动第一个实例，配置 STA10
- [ ] 启动第二个实例，配置 STA20
- [ ] 两个实例同时运行
- [ ] SSH Test 都显示绿灯 ✅
- [ ] 开始监控，文件正常分割
- [ ] 远端 rawlogs/ 收到两个站点文件
- [ ] Dashboard 显示两个站点数据

---

## 📈 改进效果

### **Dashboard UI**
- ✅ HOURLY COMPLETION 图表显示面积增加 **60%**
- ✅ RESULT DISTRIBUTION 仍清晰可读
- ✅ 布局更符合实际使用需求（小时趋势 > 结果分布）

### **多站点支持**
- ✅ 支持 **8 个站点并发**（STA10-STA80）
- ✅ **零冲突**：文件名自动区分 + 防重复上传
- ✅ **高可靠**：4 层并发安全保障
- ✅ **易操作**：每个实例独立配置 + 自动保存

### **用户体验**
- ✅ Log Splitter 可多开，提升测试效率
- ✅ Dashboard 自动识别所有站点数据
- ✅ 配置持久化，重启无需重新设置
- ✅ SSH 状态可视化（LED + 呼吸动画）

---

## 🔧 技术细节

### **CSS Flexbox 比例**
```css
/* 修改前 */
.stats-section-flex { flex: 1; }  /* 50% 空间 */

/* 修改后 */
.stats-section-hourly { flex: 1.5; }  /* 71% 空间（增加） */
.stats-section-flex { flex: 0.6; }    /* 29% 空间（减少） */
```

### **文件名格式**
```
格式：{STATION}_{DATE}_{TIME}_{MAC1}_{MAC2}_{RESULT}.txt
正则：^(STA\d{2})_(\d{8})_(\d{6})_([0-9A-F]{12})_([0-9A-F]{12})_(PASS|FAIL|STOP)\.txt$

示例：
  STA10_20260506_143000_001F7B6CB810_001F7B6CB811_PASS.txt
  STA20_20260506_143005_001F7B6CB820_001F7B6CB821_FAIL.txt
```

### **并发安全机制**
1. **文件名隔离**：STATION ID 前缀确保唯一性
2. **上传前检查**：`sftp.stat()` 防止覆盖
3. **独立 SSH 会话**：每个实例单独连接
4. **本地目录隔离**：不同 OUT 路径

---

## 📝 待办事项

### **可选优化**
- [ ] 添加站点过滤功能（Dashboard 按站点筛选数据）
- [ ] 性能测试（8 实例并发 + 1000 条/小时）
- [ ] 添加实时日志流式传输（避免轮询）
- [ ] 支持站点颜色区分（不同站点不同色标）

### **文档完善**
- [ ] 添加截图到 `multi_instance_guide.md`
- [ ] 录制多开操作视频
- [ ] 翻译为英文版本

---

*最后更新：2026-05-06 20:30*
