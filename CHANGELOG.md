# Changelog

All notable changes to this project will be documented in this file.

## [2.1.0] - 2026-03-25

### Added
- **语音输入功能** - 基于 Vosk 离线语音识别引擎
  - 支持中文语音输入（需下载约 1.2GB 模型）
  - 全局快捷键支持（可在设置中自定义）
  - 实时显示识别结果
  - 语音指示器组件显示录音状态
  - 自动下载和安装 Vosk 依赖

### Changed
- **改进单实例锁机制**
  - 启动时自动终止旧进程，避免多实例冲突
  - 优化锁文件处理逻辑
- **设置界面改进**
  - 添加滚动区域支持，适应更多设置项
  - 新增语音模型管理界面
  - 可在设置中下载/管理语音模型

### Dependencies
- 新增可选依赖：`vosk`（语音识别，按需安装）

## [2.0.0] - 2025-03-20

### Added
- 模块化架构重构 - 将单体 main.py 拆分为包结构
- 多显示器独立面板支持
- 平台抽象层（支持 Linux/Windows/macOS）
- 安装脚本和文档完善

### Components
- 20+ 种可定制组件
- 时钟（支持多种子类型）
- 天气、日历、便签、待办
- 系统监控（CPU/内存/磁盘/网络）
- 媒体播放控制
- 剪贴板历史
- CMD 命令/窗口
- Dock 栏
- 回收站
- 等等...

### Themes
- Catppuccin Mocha（默认）
- Catppuccin Latte
- Nord
- Dracula
- One Dark

---

For older versions, see git history.
