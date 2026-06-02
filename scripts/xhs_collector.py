"""
小红书内容采集器 - 基于 Patchright 持久化 Profile
采集笔记正文 + 评论，输出结构化数据
"""
import time
import random
import re
import json
import yaml
from pathlib import Path
from datetime import datetime
from markdownify import markdownify as md


class XHSCollector:
    def __init__(self, config_path: str = None):
        if config_path is None:
            config_path = Path(__file__).parent.parent / "config.yaml"
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)
        self.collect_config = self.config["collect"]

    def collect(self, page, url: str) -> dict:
        """
        采集单篇笔记的内容 + 评论。
        返回结构化 dict，供 wiki_writer 使用。
        """
        note_id = self._extract_note_id(url)
        print(f"[采集] 开始采集笔记: {note_id}")

        # 导航到页面
        page.goto(url, wait_until="domcontentloaded", timeout=30000)

        # 获取重定向后的真实 URL（处理 xhslink 等短链接）
        real_url = self._clean_url(page.url)
        note_id = self._extract_note_id(real_url)
        print(f"[采集] 真实URL: {real_url}")

        # 等待内容加载
        self._wait_for_content(page)

        # 提取内容
        result = {
            "note_id": note_id,
            "url": real_url,
            "title": self._extract_title(page),
            "author": self._extract_author(page),
            "content": self._extract_content(page),
            "likes": self._extract_likes(page),
            "collects": self._extract_collects(page),
            "publish_time": self._extract_publish_time(page),
            "comments": self._extract_comments(page) if self.collect_config["comments"] else [],
            "collected_at": datetime.now().isoformat(),
        }
        print(f"[采集] 完成: {result['title'][:50]}... ({len(result['comments'])} 条评论)")
        return result

    def _extract_note_id(self, url: str) -> str:
        m = re.search(r"/explore/([a-zA-Z0-9]+)", url)
        if m:
            return m.group(1)
        m = re.search(r"/discovery/item/([a-zA-Z0-9]+)", url)
        return m.group(1) if m else url

    def _clean_url(self, url: str) -> str:
        """去除追踪参数，保留干净的笔记 URL"""
        m = re.match(r"(https?://www\.xiaohongshu\.com/(?:explore|discovery/item)/[a-zA-Z0-9]+)", url)
        return m.group(1) if m else url

    def _wait_for_content(self, page, timeout: int = 15):
        """等待页面主要内容加载完成"""
        selectors = [
            "#detail-desc",
            ".note-content",
            ".note-scroller",
            "[class*='note']",
        ]
        for sel in selectors:
            try:
                page.wait_for_selector(sel, timeout=timeout * 1000)
                return
            except Exception:
                continue
        # 最后等一个固定时间
        time.sleep(5)

    def _extract_title(self, page) -> str:
        selectors = [
            "#detail-title",
            ".title",
            "[class*='title']",
            "h1",
        ]
        for sel in selectors:
            try:
                el = page.query_selector(sel)
                if el:
                    text = el.inner_text().strip()
                    if text and len(text) > 1:
                        return text
            except Exception:
                continue
        # fallback: document title
        try:
            return page.title()
        except Exception:
            return ""

    def _extract_author(self, page) -> str:
        selectors = [
            ".username",
            ".author .name",
            "[class*='author'] [class*='name']",
            "[class*='nickname']",
            "[class*='username']",
        ]
        for sel in selectors:
            try:
                el = page.query_selector(sel)
                if el:
                    text = el.inner_text().strip()
                    if text:
                        return text
            except Exception:
                continue
        return ""

    def _extract_content(self, page) -> str:
        selectors = [
            "#detail-desc",
            ".note-content",
            ".note-scroller .content",
            "[class*='note-text']",
            "[class*='desc']",
        ]
        for sel in selectors:
            try:
                el = page.query_selector(sel)
                if el:
                    html = el.inner_html()
                    text = md(html, heading_style="ATX").strip()
                    if text and len(text) > 10:
                        return text
            except Exception:
                continue

        # fallback: 抓取整个页面可见文本
        try:
            body = page.query_selector("body")
            if body:
                text = body.inner_text()
                # 尝试提取中间部分（排除导航等）
                lines = [l.strip() for l in text.split("\n") if l.strip()]
                return "\n".join(lines[:200])  # 限长
        except Exception:
            pass
        return ""

    def _extract_likes(self, page) -> str:
        selectors = [
            "[class*='like'] [class*='count']",
            "[class*='like'] span",
            "[class*='engage-bar'] [class*='count']",
            "[class*='interact'] [class*='count']",
        ]
        return self._extract_stat(page, selectors)

    def _extract_collects(self, page) -> str:
        selectors = [
            "[class*='collect'] [class*='count']",
            "[class*='collect'] span",
            "[class*='star'] [class*='count']",
            "[class*='engage-bar'] [class*='count']:nth-child(2)",
        ]
        return self._extract_stat(page, selectors)

    def _extract_stat(self, page, selectors: list) -> str:
        for sel in selectors:
            try:
                el = page.query_selector(sel)
                if el:
                    return el.inner_text().strip()
            except Exception:
                continue
        return ""

    def _extract_publish_time(self, page) -> str:
        selectors = ["[class*='date']", "[class*='time']", "[class*='publish']"]
        for sel in selectors:
            try:
                el = page.query_selector(sel)
                if el:
                    return el.inner_text().strip()
            except Exception:
                continue
        return ""

    def _extract_comments(self, page) -> list:
        """提取评论，含拟人滚动加载"""
        comments = []
        max_comments = self.collect_config["max_comments"]

        # 先滚动到评论区
        self._scroll_to_comments_section(page)
        time.sleep(2)

        # 滚动加载更多评论
        seen = set()
        scroll_attempts = 0
        while len(comments) < max_comments and scroll_attempts < 15:
            new_comments = self._parse_visible_comments(page)
            for c in new_comments:
                if c["text"] not in seen:
                    seen.add(c["text"])
                    comments.append(c)

            # 拟人滚动
            page.evaluate("(px) => window.scrollBy(0, px)",
                          random.randint(400, 900))
            time.sleep(random.uniform(1.5, 3.5))
            scroll_attempts += 1

        return comments[:max_comments]

    def _scroll_to_comments_section(self, page):
        """滚动到评论区位置"""
        selectors = [
            "[class*='comment']",
            "[class*='comments']",
            "#comment",
        ]
        for sel in selectors:
            try:
                el = page.query_selector(sel)
                if el:
                    el.scroll_into_view_if_needed()
                    return
            except Exception:
                continue
        # fallback: 滚动到页面中部
        page.evaluate("window.scrollTo(0, document.body.scrollHeight * 0.5)")

    def _parse_visible_comments(self, page) -> list:
        """解析当前可见的评论元素"""
        comments = []
        selectors = [
            "[class*='comment-item']",
            "[class*='commentItem']",
            "[class*='comment'] [class*='item']",
        ]
        for sel in selectors:
            try:
                els = page.query_selector_all(sel)
                if els:
                    for el in els:
                        text = el.inner_text().strip()
                        if text and len(text) > 1:
                            # 提取作者和内容
                            lines = [l.strip() for l in text.split("\n") if l.strip()]
                            comment = {
                                "author": lines[0] if lines else "",
                                "text": "\n".join(lines[1:]) if len(lines) > 1 else text,
                            }
                            comments.append(comment)
                    return comments
            except Exception:
                continue
        return comments

    @staticmethod
    def collect_urls_from_search(page, keyword: str, count: int = 10) -> list:
        """
        从小红书搜索结果中采集笔记 URL 列表。
        用于批量采集场景。
        """
        search_url = f"https://www.xiaohongshu.com/search_result?keyword={keyword}"
        page.goto(search_url, wait_until="domcontentloaded")
        time.sleep(3)

        urls = []
        note_links = page.query_selector_all("a[href*='/explore/']")
        for link in note_links:
            href = link.get_attribute("href")
            if href and "/explore/" in href:
                full_url = f"https://www.xiaohongshu.com{href}" if href.startswith("/") else href
                if full_url not in urls:
                    urls.append(full_url)
            if len(urls) >= count:
                break
        return urls
