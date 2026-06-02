# 小红书内容采集 & 知识库工具

> 将小红书优质笔记采集到本地 Markdown 知识库，支持正文提取、评论抓取、AI 总结和分类索引。

## 功能

- **单篇采集** — 输入小红书笔记 URL，自动提取标题、正文、作者、点赞/收藏数据和评论
- **搜索批量采集** — 按关键词搜索并批量采集笔记
- **Markdown 知识库** — 采集内容自动整理为结构化 Markdown，按分类组织
- **AI 总结** — 配合 AI 助手（如 Claude、DeepSeek 等）自动生成笔记总结
- **评论抓取** — 支持滚动加载、拟人化行为模拟，采集评论区内容

## 快速开始

### 前置条件

- Python 3.10+
- Chrome / Chromium 浏览器

### 安装

```bash
# 克隆仓库
git clone https://github.com/your-username/xhs-knowledge-collector.git
cd xhs-knowledge-collector

# 安装依赖
pip install -r requirements.txt

# 安装浏览器（patchright 使用 Chromium for Testing）
python -m patchright install chromium

# 如果 CDN 下载失败，也可手动下载：
# 参考: https://playwright.dev/docs/browsers#install-system-dependencies
```

### 初始化登录态（首次使用）

```bash
python scripts/init_profile.py
```

这会打开一个 Chrome 窗口，请手动登录小红书（扫码或手机号），完成后按 Enter 关闭。

### 采集单篇笔记

```bash
python scripts/main.py collect <小红书笔记URL> --category <分类>
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
├── requirements.txt           # Python 依赖
├── scripts/
│   ├── main.py                # 主入口（collect / search 命令）
│   ├── xhs_collector.py       # 小红书采集核心逻辑
│   ├── browser_manager.py     # Chrome 浏览器管理器（基于 patchright）
│   ├── wiki_writer.py         # 知识库 Markdown 写入器
│   └── init_profile.py        # Chrome Profile 初始化
├── knowledge_base/            # 采集的知识库（首次运行时自动创建）
│   ├── INDEX.md               # 总索引
│   └── <分类>/                # 按分类组织的笔记目录
└── user_data/                 # Chrome 用户数据（含登录态，不提交到 Git）
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
| `collect.images` | `false` | 是否下载图片 |

## 注意事项

- 两次采集之间至少间隔 30 秒
- 每日采集不超过 20 篇（保护账号和平台）
- 仅采集公开内容
- 登录态过期后需要重新运行 `init_profile.py`
- 本项目仅供学习研究使用

## 技术方案

项目采用 **Patchright**（Playwright 的社区分支）+ **真实 Chrome Profile** 方案：
- 使用持久化浏览器上下文保持登录态
- 模拟真人浏览行为（随机延时、拟人滚动、变速操作）
- 不注入任何自动化标记，降低被检测风险
- 支持通过 CDP 协议连接到已运行的 Chrome 实例

## 许可

MIT
