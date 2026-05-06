# 多站点数据测试验证

## 测试目标

验证 Dashboard 能正确识别和显示来自多个测试站点（STA10-STA80）的日志数据。

---

## 测试数据示例

### **Station 20 数据**
```
STA20_20260428_085216_001F7B6CB81E_001F7B6CB81F_PASS.txt
STA20_20260428_085412_001F7B6CB826_001F7B6CB827_PASS.txt
STA20_20260428_085604_001F7B6CB82A_001F7B6CB82B_PASS.txt
```

### **Station 30 数据**
```
STA30_20260417_083630_001F7B6CA886_001F7B6CA887_PASS.txt
STA30_20260417_083900_001F7B6CA88E_001F7B6CA88F_PASS.txt
STA30_20260417_084054_001F7B6CA890_001F7B6CA891_PASS.txt
STA30_20260417_084313_001F7B6CA898_001F7B6CA899_PASS.txt
STA30_20260417_084510_001F7B6CA8A0_001F7B6CA8A1_PASS.txt
STA30_20260417_084801_001F7B6CA8A6_001F7B6CA8A7_PASS.txt
STA30_20260417_085011_001F7B6CA8AE_001F7B6CA8AF_PASS.txt
```

### **Station 10 数据**
```
STA10_20260400_085200_001F7B6CB810_001F7B6CB80A_PASS.txt
```

### **混合站点数据（实际生产场景）**
```
STA10_20260506_143000_001F7B6CB810_001F7B6CB811_PASS.txt
STA20_20260506_143005_001F7B6CB820_001F7B6CB821_FAIL.txt
STA30_20260506_143010_001F7B6CB830_001F7B6CB831_PASS.txt
STA40_20260506_143015_001F7B6CB840_001F7B6CB841_PASS.txt
STA10_20260506_143020_001F7B6CB812_001F7B6CB813_PASS.txt
STA50_20260506_143025_001F7B6CB850_001F7B6CB851_STOP.txt
```

---

## 验证步骤

### **1. 解析器测试**

```python
# tests/test_parser.py
def test_parse_multiple_stations():
    """验证解析器能正确识别 STA10-STA80"""
    test_files = [
        "STA10_20260506_143000_001F7B6CB810_001F7B6CB811_PASS.txt",
        "STA20_20260506_143005_001F7B6CB820_001F7B6CB821_FAIL.txt",
        "STA30_20260506_143010_001F7B6CB830_001F7B6CB831_PASS.txt",
        "STA80_20260506_143015_001F7B6CB880_001F7B6CB881_STOP.txt",
    ]
    
    for filename in test_files:
        m = FILENAME_RE.match(filename)
        assert m is not None, f"Failed to parse: {filename}"
        station_id = m.group(1)
        assert station_id.startswith("STA"), f"Invalid station ID: {station_id}"
        station_num = int(station_id[3:])
        assert 10 <= station_num <= 80, f"Station number out of range: {station_num}"
```

### **2. Dashboard 显示测试**

#### **步骤 A：准备测试数据**
```bash
# 在远端机器创建测试文件
ssh root@10.20.31.106
cd /run/media/nvme0n1p1/rawlogs/

# 复制示例数据（从 tests/fixtures/ 复制并重命名）
# 或使用 Log Splitter UI 生成真实数据
```

#### **步骤 B：访问 Dashboard**
```
http://10.20.31.106:8080
```

#### **步骤 C：验证显示**

**Recent TESTS 表格应显示：**

| Station | Time | MAC1 | MAC2 | Result | Duration |
|---------|------|------|------|--------|----------|
| STA30 | 08:50:11 | 001F7B6CA8AE | 001F7B6CA8AF | PASS | — |
| STA30 | 08:48:01 | 001F7B6CA8A6 | 001F7B6CA8A7 | PASS | — |
| STA30 | 08:45:10 | 001F7B6CA8A0 | 001F7B6CA8A1 | PASS | — |
| STA30 | 08:43:13 | 001F7B6CA898 | 001F7B6CA899 | PASS | — |
| STA20 | 08:56:04 | 001F7B6CB82A | 001F7B6CB82B | PASS | — |
| STA20 | 08:54:12 | 001F7B6CB826 | 001F7B6CB827 | PASS | — |
| STA20 | 08:52:16 | 001F7B6CB81E | 001F7B6CB81F | PASS | — |
| STA10 | 08:52:00 | 001F7B6CB810 | 001F7B6CB80A | PASS | — |

**验证要点：**
- ✅ Station 列正确显示站点 ID（STA10, STA20, STA30 等）
- ✅ 不同站点的数据混合显示，按时间倒序排列
- ✅ 每条记录的 MAC 地址、结果状态正确显示
- ✅ 无站点 ID 的旧格式文件显示 `—`

---

## 预期结果

### **解析器 (app/parser.py)**
- ✅ 正则表达式 `STA\d{2}` 匹配 STA10-STA99
- ✅ 解析函数返回 `station_id` 字段（如 "STA10", "STA30"）
- ✅ 旧格式文件 `station_id` 为空字符串 `""`

### **状态管理 (app/state.py)**
- ✅ 去重逻辑按 MAC1 跨站点去重
- ✅ 不同站点、相同 MAC1 → 保留最新时间戳的记录
- ✅ Recent records 包含所有站点数据

### **前端显示 (frontend/)**
- ✅ Recent TESTS 表格第一列显示 Station ID
- ✅ `station_id` 存在时显示原值（如 "STA30"）
- ✅ `station_id` 为空时显示占位符 `—`
- ✅ 列宽适配：桌面 56px，移动 48px

---

## 故障排查

### **问题 1：Station 列显示为空**
- **原因**：后端未返回 `station_id` 字段
- **检查**：浏览器开发者工具 → Network → `/api/logs` 响应
- **预期**：JSON 中包含 `"station_id": "STA30"`

### **问题 2：Station 列全部显示 `—`**
- **原因**：使用旧格式文件名（无 STATION ID 前缀）
- **解决**：使用 Log Splitter UI 重新生成新格式文件

### **问题 3：多个站点数据显示混乱**
- **原因**：去重逻辑错误
- **检查**：`app/state.py` 的 `_ingest_unlocked` 函数
- **验证**：相同 MAC1 只保留最新记录

### **问题 4：表格列宽太窄**
- **原因**：`.col-station` 宽度不足
- **调整**：修改 `frontend/style.css` 中的列宽设置

---

## 性能验证

### **大数据量测试**

```bash
# 生成 1000 条多站点测试数据
for i in {1..1000}; do
  station=$((10 + (i % 8) * 10))  # STA10, STA20, ..., STA80
  timestamp=$(date +%Y%m%d_%H%M%S)
  mac1=$(printf "%012X" $((16#001F7B6CB800 + i)))
  mac2=$(printf "%012X" $((16#001F7B6CB800 + i + 1)))
  result=("PASS" "FAIL" "STOP")
  res=${result[$((i % 3))]}
  filename="STA${station}_${timestamp}_${mac1}_${mac2}_${res}.txt"
  touch /run/media/nvme0n1p1/rawlogs/${filename}
done
```

**验证要点：**
- ✅ Recent TESTS 最多显示 120 条（配置限制）
- ✅ 页面加载时间 < 3 秒
- ✅ 滚动流畅，无卡顿
- ✅ 所有站点数据按时间正确排序

---

## 通过标准

所有以下条件满足即为通过：

1. ✅ 解析器能识别 STA10-STA80 文件名
2. ✅ API 返回包含 `station_id` 字段
3. ✅ Recent TESTS 正确显示所有站点数据
4. ✅ Station 列宽度适中，内容清晰
5. ✅ 混合站点数据按时间倒序显示
6. ✅ 去重逻辑正确（同 MAC1 只显示最新）
7. ✅ 旧格式文件显示 `—` 占位符
8. ✅ 页面性能正常（< 3 秒加载）

---

*最后更新：2026-05-06*
