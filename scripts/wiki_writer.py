"""
LLMWiki 知识库写入模块
将采集内容格式化为 Markdown 写入本地知识库目录
"""
import re
import yaml
from pathlib import Path
from datetime import datetime


class WikiWriter:
    def __init__(self, config_path: str = None):
        if config_path is None:
            config_path = Path(__file__).parent.parent / "config.yaml"
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)
        self.kb_dir = Path(config_path).parent / self.config["knowledge_base_dir"]
        self.index_path = self.kb_dir / "INDEX.md"

    def write(self, data: dict, category: str = "未分类", tags: list = None) -> Path:
        """
        将采集数据写入知识库 Markdown 文件。

        Args:
            data: xhs_collector.collect() 返回的字典
            category: 分类目录名（如 "AI技术", "产品设计"）
            tags: 标签列表

        Returns:
            写入的文件路径
        """
        if tags is None:
            tags = []

        category_dir = self._sanitize_dirname(category)
        note_dir = self.kb_dir / category_dir
        note_dir.mkdir(parents=True, exist_ok=True)

        filename = self._make_filename(data)
        filepath = note_dir / filename

        md_content = self._render_markdown(data, category, tags)
        filepath.write_text(md_content, encoding="utf-8")

        self._update_index(filepath, data, category)
        return filepath

    def _sanitize_dirname(self, name: str) -> str:
        safe = re.sub(r"[^\w一-鿿\-]", "_", name)
        return safe.strip("_") or "未分类"

    def _make_filename(self, data: dict) -> str:
        date_str = datetime.now().strftime("%Y%m%d")
        title = data.get("title", "无标题")
        # 从标题生成文件名：去掉特殊字符，保留中文、字母、数字
        safe_title = re.sub(r"[^\w一-鿿]", "", title)
        safe_title = re.sub(r"\s+", "", safe_title)
        safe_title = safe_title[:30]  # 太长就截断
        if not safe_title:
            safe_title = "无标题"
        return f"{date_str}_{safe_title}.md"

    def _render_markdown(self, data: dict, category: str, tags: list) -> str:
        title = data.get("title", "无标题")
        author = data.get("author", "未知作者")
        url = data.get("url", "")
        content = data.get("content", "")
        likes = data.get("likes", "")
        collects = data.get("collects", "")
        publish_time = data.get("publish_time", "")
        collected_at = data.get("collected_at", "")
        comments = data.get("comments", [])

        tags_str = " ".join(f"#{t}" for t in tags) if tags else ""

        md = f"""---
category: {category}
author: {author}
url: {url}
likes: {likes}
collects: {collects}
publish_time: {publish_time}
collected_at: {collected_at}
tags: {", ".join(tags)}
---

# {title}

{tags_str}

> 作者: **{author}** | 点赞: {likes} | 收藏: {collects} | 发布时间: {publish_time}
>
> 原文链接: {url}

---

## 笔记内容

{content}

---

## 评论 ({len(comments)} 条)

"""
        if comments:
            for i, c in enumerate(comments, 1):
                comment_author = c.get("author", "匿名")
                comment_text = c.get("text", "")
                md += f"\n**{i}. {comment_author}**\n\n{comment_text}\n"
        else:
            md += "\n暂无评论\n"

        md += f"\n---\n*采集于 {collected_at} | 来源: 小红书*"
        return md

    def write_summary(self, data: dict, summary: str, category: str = "未分类", tags: list = None):
        """
        写入 AI 总结版本（在原始笔记基础上附加 AI 总结）
        """
        filepath = self.write(data, category, tags)
        original = filepath.read_text(encoding="utf-8")

        ai_section = f"""

---

## AI 总结

{summary}
"""
        filepath.write_text(original + ai_section, encoding="utf-8")

    def _update_index(self, filepath: Path, data: dict, category: str):
        """
        维护知识库 INDEX.md，按分类索引所有笔记。
        """
        rel_path = filepath.relative_to(self.kb_dir)
        title = data.get("title", "无标题")
        collected_at = data.get("collected_at", "")[:10]
        author = data.get("author", "")

        entry = f"- [{title}]({rel_path.as_posix()}) — {author} ({collected_at})"

        if self.index_path.exists():
            content = self.index_path.read_text(encoding="utf-8")
        else:
            content = f"# LLMWiki 知识库索引\n\n> 自动采集自小红书 | 最后更新: {datetime.now().isoformat()[:10]}\n\n"

        # 按分类组织
        section_header = f"\n## {category}\n"
        if section_header not in content:
            content += section_header

        if entry not in content:
            lines = content.split("\n")
            insert_at = None
            for i, line in enumerate(lines):
                if line.strip() == section_header.strip():
                    insert_at = i + 1
                    break

            if insert_at is not None:
                lines.insert(insert_at, entry)
                content = "\n".join(lines)
            else:
                content += entry + "\n"

        # 更新最后更新时间
        content = re.sub(
            r"最后更新: \d{4}-\d{2}-\d{2}",
            f"最后更新: {datetime.now().isoformat()[:10]}",
            content,
        )

        self.index_path.write_text(content, encoding="utf-8")
