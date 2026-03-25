#!/bin/bash
# FastPanel 安装脚本 (Linux)
# 用法: chmod +x install.sh && ./install.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_NAME="FastPanel"
DESKTOP_FILE_NAME="fastpanel.desktop"
ICON_NAME="fastpanel"

echo "========================================="
echo "  ⚡ FastPanel 安装程序"
echo "========================================="
echo ""

# 1. 检查 Python
echo "[1/5] 检查 Python 环境..."
if ! command -v python3 &>/dev/null; then
    echo "❌ 未找到 python3，请先安装：sudo apt install python3 python3-pip"
    exit 1
fi
PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "  ✅ Python $PY_VER"

# 2. 安装系统依赖
echo ""
echo "[2/5] 安装系统依赖..."
DEPS_NEEDED=""
command -v xprop &>/dev/null || DEPS_NEEDED="$DEPS_NEEDED x11-utils"
command -v pactl &>/dev/null || DEPS_NEEDED="$DEPS_NEEDED pulseaudio-utils"
dpkg -s python3-pyqt5 &>/dev/null 2>&1 || DEPS_NEEDED="$DEPS_NEEDED python3-pyqt5"

if [ -n "$DEPS_NEEDED" ]; then
    echo "  需要安装：$DEPS_NEEDED"
    sudo apt install -y $DEPS_NEEDED
else
    echo "  ✅ 系统依赖已满足"
fi

# 3. 安装 Python 依赖
echo ""
echo "[3/6] 安装 Python 依赖..."
pip3 install --user psutil python-xlib vosk 2>/dev/null || pip3 install psutil python-xlib vosk
echo "  ✅ Python 依赖已安装"

# 4. 下载语音识别模型
echo ""
echo "[4/6] 下载语音识别模型（Vosk 中文 ~42MB）..."
VOSK_MODEL_DIR="$HOME/.fastpanel/vosk-models"
VOSK_MODEL_NAME="vosk-model-small-cn-0.22"
if [ -d "$VOSK_MODEL_DIR/$VOSK_MODEL_NAME" ]; then
    echo "  ✅ 语音模型已存在"
else
    mkdir -p "$VOSK_MODEL_DIR"
    VOSK_ZIP="$VOSK_MODEL_DIR/$VOSK_MODEL_NAME.zip"
    echo "  下载中..."
    if curl -L -o "$VOSK_ZIP" "https://alphacephei.com/vosk/models/$VOSK_MODEL_NAME.zip" 2>/dev/null || \
       wget -O "$VOSK_ZIP" "https://alphacephei.com/vosk/models/$VOSK_MODEL_NAME.zip" 2>/dev/null; then
        echo "  解压中..."
        unzip -q -o "$VOSK_ZIP" -d "$VOSK_MODEL_DIR"
        rm -f "$VOSK_ZIP"
        echo "  ✅ 语音模型已下载"
    else
        echo "  ⚠️ 下载失败，可稍后在 FastPanel 设置中下载"
    fi
fi

# 5. 创建桌面入口（应用程序列表）
echo ""
echo "[5/6] 添加到应用程序列表..."

DESKTOP_DIR="$HOME/.local/share/applications"
ICON_DIR="$HOME/.local/share/icons/hicolor/scalable/apps"
mkdir -p "$DESKTOP_DIR" "$ICON_DIR"

# 复制图标
if [ -f "$SCRIPT_DIR/fastpanel.svg" ]; then
    cp "$SCRIPT_DIR/fastpanel.svg" "$ICON_DIR/$ICON_NAME.svg"
    echo "  ✅ 图标已安装"
fi

# 创建 .desktop 文件
cat > "$DESKTOP_DIR/$DESKTOP_FILE_NAME" << DESKTOP_EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=FastPanel
GenericName=Desktop Widget Engine
Comment=桌面小部件引擎 — 支持 20+ 种可定制组件
Exec=python3 $SCRIPT_DIR/main.py --desktop
Icon=$ICON_NAME
Terminal=false
Categories=Utility;System;
Keywords=widget;desktop;panel;monitor;
StartupNotify=false
DESKTOP_EOF

chmod +x "$DESKTOP_DIR/$DESKTOP_FILE_NAME"
echo "  ✅ 已添加到应用程序列表"

# 更新桌面数据库
update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true
gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" 2>/dev/null || true

# 6. 是否设置开机自启
echo ""
read -p "[6/6] 是否设置开机自动启动？(y/N): " AUTOSTART
if [[ "$AUTOSTART" =~ ^[Yy]$ ]]; then
    AUTOSTART_DIR="$HOME/.config/autostart"
    mkdir -p "$AUTOSTART_DIR"
    cp "$DESKTOP_DIR/$DESKTOP_FILE_NAME" "$AUTOSTART_DIR/$DESKTOP_FILE_NAME"
    echo "  ✅ 已设置开机自启"
else
    echo "  跳过（可后续在 FastPanel 设置中启用）"
fi

echo ""
echo "========================================="
echo "  ✅ 安装完成！"
echo "========================================="
echo ""
echo "启动方式："
echo "  1. 在应用程序列表中搜索 \"FastPanel\""
echo "  2. 或在终端运行："
echo "     python3 $SCRIPT_DIR/main.py --desktop"
echo ""
echo "卸载方式："
echo "     bash $SCRIPT_DIR/uninstall.sh"
echo ""
