# Windows 上安装 Rsync 指南

## 问题说明

当使用 rsync 远程同步路径（如 `root@10.20.31.106:/path`）时，如果系统没有安装 rsync 命令，会出现以下错误：

```
[WinError 2] 系統找不到指定的檔案。
ERR  Rsync not available: Install rsync (Git Bash/WSL) or use local path
```

## 解决方案

### 方案 1：使用 Git for Windows（推荐）

Git for Windows 自带 rsync 命令，这是最简单的安装方式。

1. **下载安装 Git for Windows**
   - 访问：https://git-scm.com/download/win
   - 下载并运行安装程序
   - 安装时选择 "Use Git and optional Unix tools from the Command Prompt"

2. **将 Git 的 usr/bin 添加到系统 PATH**
   ```
   默认路径：C:\Program Files\Git\usr\bin
   ```
   
3. **验证安装**
   ```powershell
   rsync --version
   ```
   应该显示 rsync 版本信息。

### 方案 2：使用 WSL (Windows Subsystem for Linux)

1. **启用 WSL**
   ```powershell
   wsl --install
   ```

2. **安装 Ubuntu 或其他 Linux 发行版**
   
3. **在 WSL 中安装 rsync**
   ```bash
   sudo apt-get update
   sudo apt-get install rsync
   ```

4. **从 Windows PowerShell 使用 WSL 的 rsync**
   ```powershell
   wsl rsync --version
   ```

### 方案 3：使用 Cygwin

1. 下载 Cygwin 安装程序：https://www.cygwin.com/
2. 安装时选择 `rsync` 包
3. 将 Cygwin 的 bin 目录添加到 PATH

## SSH Key 配置

安装 rsync 后，还需要配置 SSH 密钥认证：

### 1. 生成 SSH Key（如果还没有）

```powershell
ssh-keygen -t rsa -b 4096
```

按提示操作，密码可以留空（用于无密码登录）。

### 2. 复制公钥到远程服务器

```powershell
# 查看公钥内容
type $HOME\.ssh\id_rsa.pub

# 手动复制内容，然后在服务器上：
# ssh root@10.20.31.106
# mkdir -p ~/.ssh
# echo "你的公钥内容" >> ~/.ssh/authorized_keys
# chmod 600 ~/.ssh/authorized_keys
```

或使用 ssh-copy-id（如果 Git Bash 可用）：

```bash
ssh-copy-id root@10.20.31.106
```

### 3. 测试连接

```powershell
ssh root@10.20.31.106 "exit"
```

应该无需密码直接连接成功。

## 应用内测试

1. 启动 Log Splitter 应用
2. 确认 DST 字段显示：`root@10.20.31.106:/run/media/nvme0n1p1/rawlogs/`
3. 点击 **Test** 按钮
4. 查看结果：
   - ✅ **绿色呼吸灯**：连接成功
   - ❌ **红色呼吸灯**：连接失败，查看日志获取详细信息

## 故障排查

### rsync 命令找不到

**症状：** 点击 Test 按钮后弹出警告框
```
rsync command is not available on this system.
```

**解决：** 按上述方案 1-3 任选一种安装 rsync

### SSH 连接失败

**症状：** 红色呼吸灯 + 日志显示连接错误

**检查项：**
1. 网络连通性：`ping 10.20.31.106`
2. SSH 端口开放：`telnet 10.20.31.106 22`
3. SSH Key 是否配置：`ssh root@10.20.31.106 "exit"`
4. 防火墙设置

### 同步失败

**症状：** 文件已生成但同步计数为 0

**检查项：**
1. 远程路径权限：确保用户对目标目录有写权限
2. 磁盘空间：远程服务器是否有足够空间
3. 查看详细日志：应用日志窗口会显示 rsync 的错误信息

## 替代方案：使用本地路径

如果不想配置 rsync，可以使用本地文件夹作为 DST：

1. 设置 DST 为本地路径，例如：`C:\shared\rawlogs`
2. 然后手动配置 Windows 文件共享或使用其他同步工具

## 相关命令参考

```powershell
# 检查 rsync 是否可用
rsync --version

# 检查 SSH 连接
ssh root@10.20.31.106 "exit"

# 手动测试 rsync 同步
rsync -avz test.txt root@10.20.31.106:/run/media/nvme0n1p1/rawlogs/

# 查看 Git Bash 的 rsync 位置
where rsync
```
