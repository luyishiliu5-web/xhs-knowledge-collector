# 小红书内容采集 & 知识库工具

> 将小红书优质笔记采集到本地 Markdown 知识库。支持图文笔记和**视频笔记**，视频自动语音转文字，评论抓取，分类索引。

## 功能

### 📝 图文采集
- **单篇采集** — 输入小红书笔记 URL，自动提取标题、正文、作者、点赞/收藏数据和评论
- **搜索批量采集** — 按关键词搜索并批量采集笔记
- **Markdown 知识库** — 采集内容自动整理为结构化 Markdown，按分类组织
- **评论抓取** — 支持滚动加载、拟人化行为模拟，采集评论区内容

### 🎬 视频采集（v4.0 新增）
- **视频检测** — DOM + Performance API 双重检测，支持 `blob:` 协议视频真实 URL 捕获
- **视频下载** — 自动下载视频文件（MP4）到本地
- **语音转文字 ASR** — 三层策略：内嵌字幕提取 → 本地 Whisper 识别 → OpenAI API 兜底
  - 支持 `tiny` / `base` / `small` / `medium` / `large` 模型
  - 推荐 `small`（中文效果好，CPU 推理约 ~14 秒）
- **视频信息记录** — 输出文件中记录视频源链接、本地路径、ASR 转录结果

### 🔐 登录态管理（v4.0 改进）
- **CDP Bridge 方案**（推荐）— 通过 [Hermes CDP Bridge](https://github.com/NousResearch/hermes-agent) 扩展从用户 Windows Chrome 实时获取 cookie，自动注入到采集浏览器
  - 无需手动登录，只要 Chrome 开着就能采集
  - 解决 Windows DPAPI 加密 cookie 无法在 Linux 解密的问题
- **传统 Profile 方案**（备选）— `init_profile.py` 手动登录（需要图形环境）

## 快速开始

### 前置条件

- Python 3.10+
- Chrome / Chromium 浏览器
- ffmpeg（视频处理用）：`sudo apt install ffmpeg`

### 安装

```bash
# 克隆仓库
git clone https://github.com/your-username/xhs-knowledge-collector.git
cd xhs-knowledge-collector

# 复制配置
cp config.yaml.example config.yaml
# 编辑 config.yaml，设置 chrome_path 和 headless 模式

# 安装依赖
pip install -r requirements.txt

# 安装浏览器（patchright 使用 Chromium for Testing）
python -m patchright install chromium
```

### 登录态设置

**方案一：CDP Bridge（推荐，仅限 Windows + WSL 环境）**

1. 安装 [Hermes CDP Bridge](https://github.com/NousResearch/hermes-agent) Chrome 扩展
2. 启动服务器：`bash /path/to/hermes-cdp-bridge/start.sh`
3. 确保 Chrome 正在运行，扩展已连接
4. 采集时自动从 Chrome 获取 cookie，无需额外操作

**方案二：传统 Profile（通用）**

```bash
python scripts/init_profile.py
```

这会打开一个 Chrome 窗口，请手动登录小红书（扫码或手机号），完成后按 Enter 关闭。登录态保存在 `user_data/` 目录。

### 采集单篇笔记

```bash
# 图文笔记采集
python scripts/main.py collect <URL> --category <分类>

# 视频笔记采集（自动下载视频 + 语音转文字）
python scripts/main.py collect <URL> --category <分类>

# 跳过视频下载（仅采集文字）
python scripts/main.py collect <URL> --category <分类> --no-video
```

示例：
```bash
python scripts/main.py collect https://www.xiaohongshu.com/explore/abc123 --category AI技术 --tags LLM,Agent
```

### 搜索批量采集

```bash
python scripts/main.py search <关键词> --count <数量> --category <分类>
```

示例：
```bash
python scripts/main.py search "大模型应用" --count 5 --category AI技术
```

## 项目结构

```
xhs-knowledge-collector/
├── config.yaml                # 配置文件
├── config.yaml.example        # 配置文件示例
├── requirements.txt           # Python 依赖
├── scripts/
│   ├── main.py                # 主入口（collect / search 命令）
│   ├── xhs_collector.py       # 小红书采集核心逻辑
│   ├── browser_manager.py     # Chrome 浏览器管理器（基于 patchright）
│   │                          #   → 自动注入 CDP Bridge cookie
│   ├── cdp_bridge.py          # CDP Bridge 客户端（v4.0 新增）
│   │                          #   → 从 Windows Chrome 获取 cookie
│   ├── video_handler.py       # 视频检测 & 下载（v4.0 新增）
│   │                          #   → DOM + Performance API 检测
│   │                          #   → blob: 协议 URL 捕获
│   ├── speech_to_text.py      # 语音转文字 ASR（v4.0 新增）
│   │                          #   → 字幕提取 → Whisper → API 兜底
│   ├── wiki_writer.py         # 知识库 Markdown 写入器
│   └── init_profile.py        # Chrome Profile 初始化（备选方案）
├── knowledge_base/            # 采集的知识库（首次运行时自动创建）
│   ├── INDEX.md               # 总索引
│   └── <分类>/                # 按分类组织的笔记目录
├── user_data/                 # Chrome 用户数据（不提交到 Git）
└── videos/                    # 下载的视频文件（不提交到 Git）
```

## 配置

通过 `config.yaml` 自定义采集行为：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `chrome_path` | — | Chrome/Chromium 浏览器可执行文件路径 |
| `headless` | `true` | 无头模式（无 GUI 环境必须启用） |
| `behavior.min_delay` | `3` | 页面加载后最小等待时间（秒） |
| `behavior.max_delay` | `8` | 页面加载后最大等待时间（秒） |
| `rate_limit.min_interval` | `30` | 两次采集的最小间隔（秒） |
| `rate_limit.max_daily` | `20` | 每日最大采集数 |
| `collect.comments` | `true` | 是否采集评论 |
| `video.download` | `true` | 是否下载视频 |
| `video.max_size_mb` | `500` | 单个视频最大大小 |
| `asr.enabled` | `true` | 是否启用语音转文字 |
| `asr.whisper_model` | `small` | Whisper 模型大小（tiny/base/small/medium/large） |

## Changelog

### v4.0 (2026-06-03)
- ✨ **新增** 视频采集：检测、下载、`blob:` URL 捕获（via Performance API）
- ✨ **新增** 语音转文字 ASR：Whisper 三层策略，推荐 `small` 模型
- ✨ **新增** CDP Bridge 登录方案：从 Windows Chrome 实时获取 cookie
- 🔧 **改进** 视频笔记正确标注类型（🎬 视频 vs 📝 图文）
- 🔧 **改进** 短链接视频检测：增加重试等待，解决延迟加载问题
- 📦 **新文件** `cdp_bridge.py`、`video_handler.py`、`speech_to_text.py`

### v3.0
- 搜索批量采集功能
- AI 总结支持
- 拟人化浏览行为模拟

## 注意事项

- 两次采集之间至少间隔 30 秒
- 每日采集不超过 20 篇（保护账号和平台）
- 仅采集公开内容
- 本项目仅供学习研究使用

## 技术方案

项目采用 **Patchright**（Playwright 的社区分支）作为浏览器自动化引擎：

### 登录态（CDP Bridge，v4.0+）
通过 Chrome 扩展 + WebSocket 桥接，从用户正在使用的 Chrome 实时获取 cookie，注入到头less采集浏览器中。解决了跨平台 cookie 加密不兼容问题。

### 视频采集（v4.0+）
小红书新版使用 MediaSource `blob:` 协议播放视频。通过 Performance API 捕获真实 MP4 地址，httpx 直链下载。语音转文字使用 OpenAI Whisper。

## 许可

MIT
