# FastPanel

基于 PyQt5 的 Linux 桌面快捷面板，支持多种可定制组件，采用 Catppuccin 主题配色。

![Python](https://img.shields.io/badge/Python-3.8+-blue)
![PyQt5](https://img.shields.io/badge/PyQt5-5.15+-green)
![License](https://img.shields.io/badge/License-MIT-yellow)

## 功能特性

### 组件类型

| 类型 | 说明 |
|---|---|
| **CMD** | 执行命令并可选显示输出，支持动态参数 `($)` 占位符 |
| **CMD窗口** | 带交互终端的命令执行器，支持前置命令 |
| **快捷方式** | 启动应用程序、脚本或打开文件 |
| **日历** | 显示月历，支持农历、节假日和节气 |
| **天气** | 实时天气信息，包括温度曲线、多日预报、空气质量 |
| **Dock栏** | 自定义应用启动栏，支持拖拽排序 |
| **待办** | Todo 列表，支持分类和完成状态 |
| **时钟** | 多种子类型：本地时钟、世界时钟、秒表、计时器、闹钟 |

### 时钟子类型

- **时钟** — 本地时间 + 日期 + 农历，支持全屏翻页时钟
- **世界时钟** — 显示指定时区时间及与本地时差
- **秒表** — 毫秒精度计时，支持分段记录
- **计时器** — 倒计时，支持弹窗 + 声音提醒，数值持久化保存
- **闹钟** — 支持设置日期/时间，重复模式（单次/每天/工作日/周末），到时全屏提醒

### 面板管理

- 多面板切换（标签栏）
- 组件自由拖拽、调整大小
- 组件分组 / 复制 / 导出导入
- 网格吸附对齐

### 主题

内置 5 套主题：Catppuccin Mocha (默认)、Catppuccin Latte、Nord、Dracula、One Dark

## 安装

```bash
pip install PyQt5
```

## 运行

```bash
python3 main.py
```

## 使用

1. 右键网格区域 → **创建组件**，选择类型并配置
2. 拖拽组件调整位置和大小
3. 右键组件可编辑、复制、删除
4. 顶部标签栏管理多个面板

## 项目结构

```
FastPanel/
├── main.py           # 主程序（所有逻辑）
├── data.json         # 组件数据（自动生成）
├── settings.json     # 用户设置（自动生成）
├── requirements.txt  # 依赖
├── fastpanel.svg     # 应用图标
└── cities.json       # 城市数据（天气功能）
```

## 系统要求

- Python 3.8+
- PyQt5 5.15+
- Linux (Ubuntu/Debian 推荐)
- PulseAudio（闹钟/计时器声音提醒）
