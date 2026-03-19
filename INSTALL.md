# FastPanel 安装手顺

## 环境要求

| 项目 | 最低版本 | 推荐版本 |
|---|---|---|
| Python | 3.8+ | 3.10+ |
| PyQt5 | 5.15+ | 5.15.9+ |
| 操作系统 | Ubuntu 18.04 / Windows 10 / macOS 12 | Ubuntu 22.04+ |
| 显示服务 | X11（Linux 推荐） | X11 |

---

## 快速安装（推荐）

### Linux

```bash
cd FastPanel
chmod +x install.sh
./install.sh
```

安装脚本会自动：
- 检查 Python 环境
- 安装系统依赖和 Python 包
- **添加到系统应用程序列表**（可在 GNOME 活动/启动器中搜索 "FastPanel"）
- 可选设置开机自启动

卸载：
```bash
./uninstall.sh
```

---

## 一、Linux (Ubuntu / Debian) 手动安装

### 1. 安装系统依赖

```bash
# 更新包索引
sudo apt update

# Python3 和 pip（通常已预装）
sudo apt install -y python3 python3-pip python3-venv

# Qt5 运行时依赖
sudo apt install -y python3-pyqt5

# X11 工具（桌面模式必须）
sudo apt install -y x11-utils  # 提供 xprop

# 音频控制（音量滑块、闹钟提醒）
sudo apt install -y pulseaudio-utils  # 提供 pactl

# 可选：媒体播放控制
sudo apt install -y python3-dbus
```

### 2. 安装 Python 依赖

```bash
# 方式一：直接安装
pip3 install PyQt5 psutil python-xlib

# 方式二：使用 requirements.txt
cd FastPanel
pip3 install -r requirements.txt
```

> **如遇 PyQt5 安装失败**（部分发行版），改用系统包：
> ```bash
> sudo apt install -y python3-pyqt5
> pip3 install psutil python-xlib
> ```

### 3. 运行

```bash
cd FastPanel

# 桌面模式（推荐）— 全屏置底，作为桌面层运行
python3 main.py --desktop

# 窗口模式 — 传统窗口，适合调试
python3 main.py --windowed
```

### 4. 设置开机自启（可选）

#### 方式一：在 FastPanel 设置中启用

1. 右键桌面 → 设置 → 勾选「开机自动启动」

#### 方式二：手动创建 .desktop 文件

```bash
mkdir -p ~/.config/autostart

cat > ~/.config/autostart/fastpanel.desktop << 'EOF'
[Desktop Entry]
Type=Application
Name=FastPanel
Comment=Desktop Widget Engine
Exec=python3 /你的路径/FastPanel/main.py --desktop
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
EOF
```

> 将 `/你的路径/FastPanel/` 替换为实际路径

---

## 二、Windows 安装

### 1. 安装 Python

1. 下载 [Python 3.10+](https://www.python.org/downloads/)
2. 安装时勾选 **Add Python to PATH**
3. 打开命令提示符验证：
   ```cmd
   python --version
   ```

### 2. 安装依赖

```cmd
cd FastPanel
pip install -r requirements.txt
```

### 3. 运行

```cmd
:: 桌面模式
python main.py --desktop

:: 窗口模式
python main.py --windowed
```

> **注意**：Windows 下桌面模式使用 WorkerW 嵌入，部分功能（如全局快捷键）可能受限。

---

## 三、macOS 安装

### 1. 安装 Python

```bash
# 通过 Homebrew
brew install python3
```

### 2. 安装依赖

```bash
cd FastPanel
pip3 install PyQt5 psutil
```

> macOS 下 `python-xlib` 不需要安装（X11 专属）

### 3. 运行

```bash
python3 main.py --desktop
```

> **注意**：macOS 下桌面模式使用 NSWindow 层级，部分功能受限。

---

## 四、依赖说明

| 包名 | 用途 | 必需 |
|---|---|---|
| `PyQt5` | GUI 框架 | ✅ |
| `psutil` | 系统监控（CPU/内存/磁盘/网络） | ✅ |
| `python-xlib` | X11 全局快捷键、剪贴板粘贴 | ✅ Linux |
| `dbus-python` | 媒体播放控制 (MPRIS) | ❌ 可选 |

### requirements.txt 内容

```
PyQt5>=5.15
psutil>=5.8
python-xlib>=0.31
```

---

## 五、常见问题

### Q: 启动后看不到 FastPanel，桌面没有变化？

A: FastPanel 在桌面层运行，被其他窗口覆盖时看不到。使用 `Super+D`（显示桌面）或最小化所有窗口即可看到。也可以在系统托盘中点击 FastPanel 图标。

### Q: 提示 "已有实例运行"？

A: FastPanel 有单实例保护。如果之前异常退出，删除锁文件后重试：
```bash
rm -f ~/.fastpanel.lock
python3 main.py --desktop
```

### Q: PyQt5 安装报错 "No matching distribution"？

A: Python 3.12+ 可能不支持旧版 PyQt5。尝试：
```bash
# 使用系统包
sudo apt install python3-pyqt5

# 或安装特定版本
pip3 install PyQt5==5.15.9
```

### Q: 桌面闪烁或被系统桌面覆盖？

A: 这通常是 GNOME 桌面图标扩展 (ding) 冲突。FastPanel 会自动禁用它，但如果仍有问题：
```bash
# 手动禁用
gnome-extensions disable ding@rastersoft.com
```

### Q: 全局快捷键不起作用？

A: 可能与系统快捷键冲突。在 FastPanel 设置中修改为不冲突的组合键。全局快捷键仅支持 X11 环境。

### Q: 怎么完全退出 FastPanel？

A: 三种方式：
1. 右键桌面 → 退出 FastPanel
2. 系统托盘 → 退出
3. 终端中 `pkill -f "python3 main.py"`

### Q: 数据保存在哪里？

A: 
- 组件数据：`FastPanel/data.json`
- 用户设置：`FastPanel/settings.json`
- 备份这两个文件即可迁移全部配置和组件

---

## 六、升级

```bash
cd FastPanel

# 备份数据
cp data.json data.json.bak
cp settings.json settings.json.bak

# 拉取最新代码（如果使用 git）
git pull

# 更新依赖
pip3 install -r requirements.txt --upgrade

# 重启
pkill -f "python3 main.py"
python3 main.py --desktop
```

---

## 七、卸载

```bash
# 停止运行
pkill -f "python3 main.py"

# 移除自启动
rm -f ~/.config/autostart/fastpanel.desktop

# 恢复 GNOME 桌面图标
gnome-extensions enable ding@rastersoft.com

# 删除锁文件
rm -f ~/.fastpanel.lock

# 删除项目目录
rm -rf FastPanel/
```
