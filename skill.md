---
name: xhs-knowledge-collector
description: 小红书内容采集 -> LLMWiki 知识库。采集小红书笔记正文+评论，格式化写入本地 Markdown 知识库。使用真实 Chrome Profile 保持登录态，非模拟浏览器。
version: 1.0.0
author: user
tags: [xiaohongshu, collector, knowledge-base, crawler]
---

# 小红书内容采集 & LLMWiki 知识库

将小红书优质笔记采集到本地 Markdown 知识库中，支持正文提取、评论抓取、AI 总结和分类索引。

## 前置条件

1. 运行过一次 `python scripts/init_profile.py`，在 Chrome 中手动登录小红书
2. 确认 `user_data/` 目录已生成且包含登录态

## 工作流程

### 采集单篇笔记

当用户提供小红书笔记 URL 时：

1. 调用 `python scripts/main.py collect <url> --category <分类> --tags <标签>` 启动采集
2. 采集脚本会：
   - 使用持久化 Chrome Profile 打开浏览器（已登录态）
   - 访问笔记页面，提取标题、正文、作者、点赞、收藏数据
   - 滚动加载并提取评论区内容
   - 将内容写入 `knowledge_base/<分类>/` 目录下的 Markdown 文件
   - 更新 `knowledge_base/INDEX.md` 索引
3. 采集完成后，读取生成的 Markdown 文件
4. 对内容进行 AI 总结，并将总结追加回文件

### 搜索采集

当用户想按主题批量采集时：

1. 调用 `python scripts/main.py search <关键词> --count <数量> --category <分类>`
2. 脚本会搜索关键词，获取笔记列表，逐篇采集
3. 采集结果写入知识库

### AI 总结

采集完成后，你应该：
1. 阅读笔记正文
2. 提取3-5个核心观点
3. 用2-3句话概括整体内容
4. 注明适合阅读的人群
5. 将总结写入笔记 Markdown 文件的「AI 总结」部分

总结格式：
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
knowledge_base/
├── INDEX.md              # 总索引，按分类列出所有笔记
├── AI技术/
│   └── 20260522_abc123.md
├── 产品设计/
│   └── 20260522_def456.md
└── ...
```

## 重要提示

- 两次采集之间至少间隔 30 秒
- 每日采集不超过 20 篇
- 仅采集公开内容
- 首次使用前必须运行 init_profile.py 手动登录
- 如果采集失败提示需要登录，说明 Profile 中的登录态已过期，需要重新运行 init_profile.py
