#!/bin/bash
# FastPanel 卸载脚本 (Linux)
# 用法: chmod +x uninstall.sh && ./uninstall.sh

set -e

echo "========================================="
echo "  ⚡ FastPanel 卸载程序"
echo "========================================="
echo ""

# 1. 停止运行中的实例
echo "[1/4] 停止 FastPanel..."
pkill -f "python3.*main.py.*--desktop" 2>/dev/null && echo "  ✅ 已停止" || echo "  ℹ️  未在运行"

# 2. 移除应用列表入口
echo ""
echo "[2/4] 移除应用程序列表..."
DESKTOP_FILE="$HOME/.local/share/applications/fastpanel.desktop"
if [ -f "$DESKTOP_FILE" ]; then
    rm -f "$DESKTOP_FILE"
    echo "  ✅ 已移除"
else
    echo "  ℹ️  未找到桌面入口"
fi

# 3. 移除自启动
echo ""
echo "[3/4] 移除开机自启..."
AUTOSTART_FILE="$HOME/.config/autostart/fastpanel.desktop"
if [ -f "$AUTOSTART_FILE" ]; then
    rm -f "$AUTOSTART_FILE"
    echo "  ✅ 已移除"
else
    echo "  ℹ️  未设置自启动"
fi

# 4. 恢复 GNOME 桌面图标
echo ""
echo "[4/4] 恢复系统设置..."
gnome-extensions enable ding@rastersoft.com 2>/dev/null && echo "  ✅ 已恢复 GNOME 桌面图标" || echo "  ℹ️  无需恢复"

# 清理
rm -f "$HOME/.fastpanel.lock"
rm -f "$HOME/.local/share/icons/hicolor/scalable/apps/fastpanel.svg"
update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true

echo ""
echo "========================================="
echo "  ✅ 卸载完成！"
echo "========================================="
echo ""
echo "注意：组件数据和设置文件仍保留在项目目录中："
echo "  - data.json（组件数据）"
echo "  - settings.json（用户设置）"
echo ""
echo "如需完全删除，请手动删除项目目录。"
echo ""
