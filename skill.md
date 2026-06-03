---
name: xhs-knowledge-collector
description: 小红书内容采集 -> LLMWiki 知识库。采集小红书笔记正文+评论+视频，语音转文字，格式化写入本地 Markdown 知识库。使用真实 Chrome Profile 保持登录态。
version: 3.0.0
author: user
tags: [xiaohongshu, collector, knowledge-base, crawler, video, asr, whisper]
---

# 小红书内容采集 & LLMWiki 知识库

采集小红书笔记（图文 + 视频）到本地 Markdown 知识库。
**视频笔记会自动语音转文字**，适合采集知识科普、AI 热点、行业分析等口播类视频。

## 核心能力

```
图文笔记 → 正文 + 评论 → Markdown → AI 总结
视频笔记 → 下载视频 → 语音转文字(ASR) → 完整文字稿 → AI 总结
                              ↑
                    三层策略：字幕提取 → 本地Whisper → OpenAI API
```

## 前置条件

1. 运行过一次 `python scripts/init_profile.py`，在 Chrome 中手动登录小红书
2. 确认 `user_data/` 目录已生成且包含登录态
3. **`sudo apt install ffmpeg`** — 视频下载 + 音频提取 + 字幕提取（必须）
4. **`pip install openai-whisper`** — 语音转文字核心依赖
5. (可选) `pip install yt-dlp openai` — 复杂视频兜底 + API 兜底

## 工作流程

### 采集单篇笔记

```bash
# 完整采集（含视频下载 + 语音转文字）
python scripts/main.py collect <url> --category <分类> --tags <标签>

# 跳过视频（只采集文字）
python scripts/main.py collect <url> --no-video

# 禁用 ASR（下载视频但不做语音识别）
# 在 config.yaml 中设置 asr.enabled: false
```

### 采集流程详解

```
1. 浏览器打开笔记页面（持久化登录态）
2. 检测笔记类型
   ├── 📝 图文 → 提取标题/正文/作者/点赞/收藏
   └── 🎬 视频 → 额外执行：
        ├── 提取视频源 URL（从 __INITIAL_STATE__ JSON）
        ├── 下载视频文件 → videos/
        ├── 提取字幕（如有软字幕）  ← 策略1
        │    └── 若无,提取音频(WAV) → Whisper 识别  ← 策略2
        │         └── 若失败,OpenAI Whisper API    ← 策略3
        └── 文字稿替换笔记正文（因为视频描述通常极短）
3. 提取评论
4. 写入 knowledge_base/ 下的 Markdown 文件
5. 更新 INDEX.md
```

### 语音转文字的三种策略

| 策略 | 适用场景 | 依赖 | 质量 |
|------|---------|------|:---:|
| **软字幕提取** | 视频有内嵌 SRT/ASS 字幕 | ffmpeg | ⭐⭐⭐⭐⭐ (原文) |
| **本地 Whisper** | 无字幕的口播视频 | openai-whisper | ⭐⭐⭐⭐ |
| **OpenAI API** | 本地模型失败的兜底 | openai SDK + KEY | ⭐⭐⭐⭐⭐ |

推荐 Whisper 模型选择（config.yaml 中 `asr.whisper_model`）：
- `medium`: 推荐，中文效果好，~5GB 内存，CPU 也能跑
- `large-v3`: 精度最高，需要 ~10GB 内存/显存
- `small`: 速度快，精度可接受，适合测试

### 搜索采集

```bash
python scripts/main.py search <关键词> --count <数量> --category <分类>
python scripts/main.py search <关键词> --no-video
```

### AI 总结

采集完成后（特别是视频已转为文字稿后），你应该：

1. 阅读笔记的文字稿（视频 → Whisper 转的文字稿在「📝 语音文字稿」区域）
2. 提取 3-5 个核心观点
3. 用 2-3 句话概括整体内容
4. 注明适合阅读的人群
5. 将总结写入 Markdown 文件的「AI 总结」部分

```markdown
## AI 总结

**核心观点：**
- 观点1
- 观点2
- 观点3

**一句话概括：** ...

**适合人群：** ...
```

## 知识库结构

```
xiaohongshu-collector/
├── config.yaml                    # 所有配置
├── requirements.txt
├── SKILL.md
├── scripts/
│   ├── main.py                    # CLI 入口
│   ├── init_profile.py            # 首次登录
│   ├── browser_manager.py         # Chrome 反检测
│   ├── xhs_collector.py           # 核心采集器
│   ├── video_handler.py           # 视频检测+下载
│   ├── speech_to_text.py          # ASR 语音转文字 ← 新增
│   └── wiki_writer.py             # Markdown 写入
├── user_data/                     # Chrome 登录态
├── knowledge_base/                # 知识库输出
│   ├── INDEX.md
│   ├── AI技术/
│   │   ├── 20260522_abc123.md     # 图文笔记
│   │   └── 20260603_video456.md   # 视频笔记 🎬
│   └── 产品设计/
└── videos/                        # 视频文件
    ├── 20260603_abc123.mp4
    └── 20260603_abc123_cover.jpg
```

## 输出示例 (知识科普视频 + ASR)

```markdown
---
category: AI技术
author: AI科技前沿
url: https://www.xiaohongshu.com/explore/xxx
type: 🎬 视频
likes: 3.2万
collects: 1.5万
publish_time: 2026-06-01
collected_at: 2026-06-03T19:50:00
tags: AI, Agent, Claude
has_video: true
---

# GPT-5 来了！一文看懂最新发布的 5 大核心能力

> 作者: **AI科技前沿** | 🎬 视频 | 点赞: 3.2万 | 收藏: 1.5万

---

## 笔记内容

> 视频简介：OpenAI刚刚发布了GPT-5，这个视频带你快速了解5大核心更新

## 📝 语音文字稿

大家好啊，今天我们来聊一下 OpenAI 刚刚发布的 GPT-5。
这次更新有五个核心能力，我们先说第一个——原生多模态。
以前 GPT-4 的多模态是拼凑起来的，图片走 DALL-E，语音走 Whisper...
第二个是超长上下文，GPT-5 支持 200 万 token 的上下文窗口...
第三个是 Agent 原生支持，可以直接操作你的电脑...
（共计 3200 字的完整口播文字稿）

---

## 🎬 视频信息

- **时长**: 8分42秒
- **分辨率**: 1920×1080
- **本地文件**: [videos/20260603_xxx.mp4](videos/20260603_xxx.mp4)
- **原始链接**: [视频源](https://sns-video-al.xhscdn.com/...)
- **语音识别**: Whisper (medium) · 3200 字

---

## 评论 (15 条)

**1. 用户A**

博主总结得好清晰！第一个多模态太强了

**2. 用户B**

200万token上下文...我的M2 Mac还能跑得动吗...

---
*采集于 2026-06-03T19:50:00 | 来源: 小红书*
```

## 配置速查

```yaml
# config.yaml 关键配置

# 视频采集开关
video:
  download: true        # 是否下载视频
  quality: "highest"    # 清晰度

# 语音转文字开关
asr:
  enabled: true              # 是否启用 ASR
  whisper_model: "medium"    # 模型大小
  whisper_language: "zh"     # 中文识别
  use_api_fallback: false    # 是否启用 API 兜底
```

## 重要提示

- 两次采集之间至少间隔 30 秒
- 每日采集不超过 20 篇
- 仅采集公开内容
- 首次使用前必须运行 `init_profile.py` 手动登录
- ASR 需要 `ffmpeg` + `openai-whisper`，首次运行时 Whisper 会自动下载模型
- 本地 Whisper 在 CPU 上处理 10 分钟视频约需 2-5 分钟（取决于模型和硬件）
- 视频降噪/背景音乐可能影响识别准确率，但知识口播类通常效果很好
