"""
小红书视频处理器 - 视频检测、URL 提取与下载
============================================
支持：

1. 页面视频检测（DOM 解析 + __INITIAL_STATE__ JSON 提取）
2. 视频源 URL 提取（mp4 / m3u8 / blob）
3. 视频下载（直链 httpx + HLS/m3u8 → ffmpeg + yt-dlp 兜底）
4. 封面图 / 时长 / 分辨率等元信息提取

不依赖多模态大模型 — 纯 DOM 解析 + HTTP 下载。
"""

import re
import json
import time
import shutil
import hashlib
import subprocess
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional, Tuple

import yaml
import httpx
from markdownify import markdownify as md


class VideoHandler:
    """小红书视频检测与下载器"""

    def __init__(self, config_path: str = None):
        if config_path is None:
            config_path = Path(__file__).parent.parent / "config.yaml"
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)

        self.video_config = self.config.get("video", {})
        self.download_dir = Path(config_path).parent / self.video_config.get(
            "download_dir", "./videos"
        )
        self.max_size_mb = self.video_config.get("max_size_mb", 500)
        self.download_enabled = self.video_config.get("download", True)
        self.preferred_formats = self.video_config.get("formats", ["mp4"])
        # 自动检测 ffmpeg（兼容 WSL 下的 ffmpeg.exe）
        self._ffmpeg = self._find_ffmpeg()

    @staticmethod
    def _find_ffmpeg() -> Optional[str]:
        """查找系统上的 ffmpeg，兼容 WSL（Windows ffmpeg.exe）"""
        for name in ("ffmpeg", "ffmpeg.exe"):
            if shutil.which(name):
                return name
        return None

    # ── 检测 ──────────────────────────────────────────────

    def _capture_video_url(self, page) -> Optional[str]:
        """通过 Performance API 查找已加载的视频 URL（处理 blob: 场景）"""
        try:
            urls = page.evaluate("""() => {
                return performance.getEntriesByType('resource')
                    .filter(e => e.name.includes('.mp4') || e.name.includes('.m3u8'))
                    .map(e => e.name);
            }""")
            if urls and len(urls) > 0:
                url = urls[0]
                print(f"[Video] 从 Performance API 捕获视频 URL ✅")
                return url
        except Exception:
            pass
        return None

    def detect_video(self, page) -> bool:
        """
        检测当前页面是否包含视频笔记。
        策略：DOM 元素 + 页面初始状态 JSON 双重检测。
        """
        # 策略 1：DOM 中是否有 video 标签
        try:
            video_el = page.query_selector("video")
            if video_el:
                return True
        except Exception:
            pass

        # 策略 2：video 容器 class
        video_container_selectors = [
            "[class*='video-container']",
            "[class*='note-video']",
            "[class*='player']",
            "[class*='videoPlayer']",
            ".video-player",
            "[id*='video']",
        ]
        for sel in video_container_selectors:
            try:
                el = page.query_selector(sel)
                if el:
                    return True
            except Exception:
                continue

        # 策略 3：从 __INITIAL_STATE__ 中检测 video 数据
        try:
            init_state = self._extract_initial_state(page)
            if init_state:
                note_data = self._find_note_data(init_state)
                if note_data and self._has_video_in_data(note_data):
                    return True
        except Exception:
            pass

        return False

    def extract_video_info(self, page) -> dict:
        """
        从页面提取视频完整信息。

        返回 dict:
            has_video: bool
            video_url: str 或 None           # 直链 mp4 地址
            video_streams: list[dict]         # 多清晰度流列表 [{url, quality, format}]
            cover_url: str 或 None            # 封面图地址
            duration: int 或 None             # 时长(秒)
            width: int 或 None
            height: int 或 None
            video_desc: str 或 None           # 视频的文字描述（当正文为空时有用）
        """
        info = {
            "has_video": False,
            "video_url": None,
            "video_streams": [],
            "cover_url": None,
            "duration": None,
            "width": None,
            "height": None,
            "video_desc": None,
        }

        # ── 从 DOM <video> / <source> 提取 ──
        # 部分页面（如 xhslink 短链接）视频元素会延迟加载，最多等 5 秒
        video_el = None
        for wait_sec in [0, 1, 2, 3, 5]:
            try:
                video_el = page.query_selector("video")
                if video_el:
                    break
            except Exception:
                pass
            if wait_sec > 0:
                time.sleep(wait_sec)

        # 如果 video 是 blob: 协议，通过网络拦截获取真实 URL
        if video_el:
            info["has_video"] = True
            try:
                src = video_el.get_attribute("src") or ""
                if src.startswith("blob:"):
                    # 尝试用网络拦截找真实视频 URL
                    real_url = self._capture_video_url(page)
                    if real_url:
                        info["video_url"] = real_url
                        info["video_streams"].append({
                            "url": real_url, "quality": "default", "format": self._guess_format(real_url)
                        })
            except Exception:
                pass

        try:
            if video_el:
                info["has_video"] = True

                # src 属性
                src = video_el.get_attribute("src")
                if src and not src.startswith("blob:"):
                    info["video_url"] = src
                    info["video_streams"].append({
                        "url": src, "quality": "default", "format": self._guess_format(src)
                    })

                # <source> 子标签
                source_els = video_el.query_selector_all("source")
                for s in source_els:
                    s_src = s.get_attribute("src")
                    s_type = s.get_attribute("type") or ""
                    if s_src:
                        quality = "default"
                        # 尝试从 label/data-quality 获取清晰度
                        label = s.get_attribute("label") or s.get_attribute("data-quality") or ""
                        if label:
                            quality = label
                        info["video_streams"].append({
                            "url": s_src, "quality": quality, "format": self._guess_format(s_src)
                        })
                        if info["video_url"] is None and not s_src.startswith("blob:"):
                            info["video_url"] = s_src

                # poster（封面图）
                poster = video_el.get_attribute("poster")
                if poster:
                    info["cover_url"] = poster

                # duration
                dur = video_el.get_attribute("duration")
                if dur:
                    try:
                        info["duration"] = int(float(dur))
                    except ValueError:
                        pass
        except Exception:
            pass

        # ── 从 __INITIAL_STATE__ 提取（更可靠的视频数据源）──
        try:
            init_state = self._extract_initial_state(page)
            if init_state:
                note_data = self._find_note_data(init_state)

                if note_data:
                    video_data = self._extract_video_from_note(note_data)

                    if video_data:
                        info["has_video"] = True

                        # 视频流（通常包含多分辨率）
                        streams = video_data.get("media", {}).get("stream", {})
                        h264 = streams.get("h264", []) or streams.get("h265", [])
                        if isinstance(h264, list):
                            for s in h264:
                                s_url = s.get("masterUrl") or s.get("url") or ""
                                if s_url:
                                    info["video_streams"].append({
                                        "url": s_url,
                                        "quality": s.get("quality", s.get("definition", "default")),
                                        "format": "mp4",
                                    })
                        elif isinstance(h264, dict) and h264.get("masterUrl"):
                            info["video_streams"].append({
                                "url": h264["masterUrl"],
                                "quality": h264.get("quality", "default"),
                                "format": "mp4",
                            })

                        # 选最高清作为主视频 URL
                        if info["video_streams"] and not info["video_url"]:
                            info["video_url"] = info["video_streams"][0]["url"]

                        # 封面
                        cover_list = (
                            video_data.get("image", {})
                            .get("thumbnail", [])
                            or video_data.get("cover", [])
                        )
                        if isinstance(cover_list, list) and cover_list:
                            info["cover_url"] = cover_list[0].get("url", cover_list[0])
                        elif isinstance(cover_list, dict):
                            info["cover_url"] = cover_list.get("url", "")

                        if not info["cover_url"]:
                            info["cover_url"] = note_data.get("cover", {}).get("url", "")

                        # 元信息
                        info["duration"] = (
                            video_data.get("duration")
                            or video_data.get("videoDuration")
                            or info["duration"]
                        )
                        info["width"] = video_data.get("width")
                        info["height"] = video_data.get("height")
                        info["video_desc"] = video_data.get("desc") or video_data.get("title") or ""

                # 即使没有 video_data，笔记描述也可能是视频的说明文字
                if info["has_video"] and not info["video_desc"]:
                    info["video_desc"] = (
                        note_data.get("desc", "")
                        or note_data.get("title", "")
                        or note_data.get("displayTitle", "")
                    )
        except Exception:
            pass

        return info

    # ── 下载 ──────────────────────────────────────────────

    def download_video(
        self,
        video_info: dict,
        note_id: str = "",
        quality: str = "highest",
    ) -> Optional[Path]:
        """
        下载视频到本地。

        Args:
            video_info: extract_video_info() 的返回结果
            note_id: 笔记 ID，用于文件命名
            quality: "highest" | "lowest" | specific label

        Returns:
            下载文件的 Path，失败返回 None
        """
        if not video_info.get("has_video"):
            print("[Video] 无视频可下载")
            return None

        # 选择视频流
        target_url = self._select_stream(video_info["video_streams"], quality)
        if not target_url:
            target_url = video_info.get("video_url")
        if not target_url:
            print("[Video] 未找到可下载的视频 URL")
            return None

        self.download_dir.mkdir(parents=True, exist_ok=True)
        safe_id = re.sub(r"[^\w\-]", "_", note_id)[:60]
        filename = f"{datetime.now().strftime('%Y%m%d')}_{safe_id}.mp4"
        filepath = self.download_dir / filename

        print(f"[Video] 下载: {target_url[:100]}...")

        # 判断视频类型
        fmt = self._guess_format(target_url)
        if fmt == "m3u8":
            success = self._download_m3u8(target_url, filepath)
        else:
            success = self._download_direct(target_url, filepath)

        if success and filepath.exists():
            size_mb = filepath.stat().st_size / (1024 * 1024)
            print(f"[Video] 下载完成: {filepath.name} ({size_mb:.1f} MB)")
            return filepath

        # ── yt-dlp 兜底 ──
        print("[Video] 直链下载失败，尝试 yt-dlp 兜底...")
        success = self._download_with_ytdlp(target_url, filepath)
        if success and filepath.exists():
            return filepath

        return None

    def download_cover(self, cover_url: str, note_id: str) -> Optional[Path]:
        """下载视频封面图"""
        if not cover_url:
            return None

        self.download_dir.mkdir(parents=True, exist_ok=True)
        safe_id = re.sub(r"[^\w\-]", "_", note_id)[:60]
        ext = self._guess_image_ext(cover_url)
        filepath = self.download_dir / f"{datetime.now().strftime('%Y%m%d')}_{safe_id}_cover.{ext}"

        try:
            with httpx.Client(follow_redirects=True, timeout=60) as client:
                resp = client.get(cover_url)
                resp.raise_for_status()
                filepath.write_bytes(resp.content)
            return filepath
        except Exception as e:
            print(f"[Video] 封面下载失败: {e}")
            return None

    # ── 内部：页面数据提取 ────────────────────────────────

    def _extract_initial_state(self, page) -> Optional[dict]:
        """从页面提取 window.__INITIAL_STATE__ JSON 数据"""
        try:
            raw = page.evaluate("() => window.__INITIAL_STATE__")
            if raw:
                return json.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            pass

        # fallback: 从 <script> 标签提取
        try:
            scripts = page.query_selector_all("script")
            for s in scripts:
                text = s.inner_text()
                if "__INITIAL_STATE__" in text and "note" in text:
                    m = re.search(
                        r"window\.__INITIAL_STATE__\s*=\s*({.*?});\s*\n", text, re.DOTALL
                    )
                    if m:
                        return json.loads(m.group(1))
        except Exception:
            pass

        return None

    def _find_note_data(self, init_state: dict) -> Optional[dict]:
        """从 __INITIAL_STATE__ 中定位当前笔记数据"""
        if not init_state:
            return None

        # 常见路径
        paths = [
            ["note", "noteDetailMap"],
            ["note", "noteMap"],
            ["noteDetail", "data"],
            ["noteDetail"],
        ]

        for path in paths:
            d = init_state
            try:
                for key in path:
                    d = d.get(key, {}) if isinstance(d, dict) else d
                if isinstance(d, dict):
                    # noteDetailMap 是 {noteId: data} 映射
                    if d and any("noteId" in str(v) for v in d.values()):
                        return list(d.values())[0]
                    elif d:
                        return d
            except Exception:
                continue

        # 递归搜索（限深）
        def _search(obj, depth=0):
            if depth > 4 or not isinstance(obj, dict):
                return None
            if "video" in obj and isinstance(obj["video"], dict):
                return obj
            for v in obj.values():
                r = _search(v, depth + 1)
                if r:
                    return r
            return None

        return _search(init_state)

    def _has_video_in_data(self, note_data: dict) -> bool:
        """检查 note 数据中是否包含视频"""
        if note_data.get("type") == "video":
            return True
        if note_data.get("video"):
            return True
        if note_data.get("noteType") == "video":
            return True
        return False

    def _extract_video_from_note(self, note_data: dict) -> Optional[dict]:
        """从笔记数据中提取视频子对象"""
        video = note_data.get("video")
        if video and isinstance(video, dict):
            return video
        # 有时视频数据在 media 字段下
        media = note_data.get("media", {})
        if media.get("video"):
            return media["video"]
        if media.get("stream"):
            return media
        return None

    # ── 内部：下载实现 ────────────────────────────────────

    def _select_stream(self, streams: list, quality: str) -> Optional[str]:
        """从多清晰度流中选择一个"""
        if not streams:
            return None
        if quality == "highest":
            return streams[0]["url"]
        if quality == "lowest":
            return streams[-1]["url"]
        for s in streams:
            if s.get("quality") == quality:
                return s["url"]
        return streams[0]["url"]

    def _download_direct(self, url: str, filepath: Path) -> bool:
        """直链 mp4 下载（流式写入 + 进度条 + 大小限制）"""
        max_bytes = self.max_size_mb * 1024 * 1024
        try:
            with httpx.Client(follow_redirects=True, timeout=300) as client:
                with client.stream("GET", url, headers={
                    "Referer": "https://www.xiaohongshu.com/",
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/125.0.0.0 Safari/537.36"
                    ),
                }) as resp:
                    resp.raise_for_status()
                    total = int(resp.headers.get("content-length", 0))
                    downloaded = 0
                    with open(filepath, "wb") as f:
                        for chunk in resp.iter_bytes(chunk_size=1024 * 1024):
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total:
                                pct = downloaded / total * 100
                                bar_len = 30
                                filled = int(bar_len * downloaded / total)
                                bar = "█" * filled + "░" * (bar_len - filled)
                                print(
                                    f"\r[Video] {bar} {pct:5.1f}% "
                                    f"({downloaded / 1024 / 1024:.1f}/{total / 1024 / 1024:.1f} MB)",
                                    end="",
                                    flush=True,
                                )
                            if downloaded > max_bytes:
                                print(f"\n[Video] 超过大小限制 ({self.max_size_mb} MB)，取消下载")
                                filepath.unlink(missing_ok=True)
                                return False
                    if total:
                        print()  # 换行
                    return True
        except Exception as e:
            print(f"\n[Video] 直链下载失败: {e}")
            return False

    def _download_m3u8(self, url: str, filepath: Path) -> bool:
        """使用 ffmpeg 下载 HLS/m3u8 流"""
        if not self._ffmpeg:
            print("[Video] 未安装 ffmpeg，请运行: sudo apt install ffmpeg")
            return False

        cmd = [
            self._ffmpeg,
            "-y",
            "-loglevel", "warning",
            "-stats",
            "-headers", f"Referer: https://www.xiaohongshu.com/",
            "-i", url,
            "-c", "copy",
            "-bsf:a", "aac_adtstoasc",
            "-fs", str(self.max_size_mb * 1024 * 1024),
            str(filepath),
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            if filepath.exists() and filepath.stat().st_size > 0:
                return True
            print(f"[Video] ffmpeg 失败: {result.stderr[-500:]}")
            return False
        except subprocess.TimeoutExpired:
            print("[Video] ffmpeg 超时")
            filepath.unlink(missing_ok=True)
            return False
        except Exception as e:
            print(f"[Video] ffmpeg 错误: {e}")
            return False

    def _download_with_ytdlp(self, url: str, filepath: Path) -> bool:
        """yt-dlp 兜底下载（处理各种复杂视频源）"""
        if not shutil.which("yt-dlp"):
            print("[Video] 未安装 yt-dlp，跳过兜底。安装: pip install yt-dlp")
            return False

        cmd = [
            "yt-dlp",
            "--no-playlist",
            "--max-filesize", f"{self.max_size_mb}M",
            "--merge-output-format", "mp4",
            "-o", str(filepath),
            "--add-header", "Referer: https://www.xiaohongshu.com/",
            url,
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            if filepath.exists() and filepath.stat().st_size > 0:
                return True
            print(f"[Video] yt-dlp 失败: {result.stderr[-500:]}")
            # yt-dlp 有时会把文件写到带后缀的路径，查找一下
            stem = filepath.stem
            for f in filepath.parent.glob(f"{stem}*"):
                if f.suffix in (".mp4", ".mkv", ".webm") and f.stat().st_size > 0:
                    if f != filepath:
                        f.rename(filepath)
                        return True
            return False
        except subprocess.TimeoutExpired:
            print("[Video] yt-dlp 超时")
            return False
        except Exception as e:
            print(f"[Video] yt-dlp 错误: {e}")
            return False

    # ── 工具方法 ──────────────────────────────────────────

    @staticmethod
    def _guess_format(url: str) -> str:
        """从 URL 或文件头推断视频格式"""
        url_lower = url.split("?")[0].lower()
        if ".m3u8" in url_lower:
            return "m3u8"
        if ".mp4" in url_lower:
            return "mp4"
        if ".webm" in url_lower:
            return "webm"
        if ".mkv" in url_lower:
            return "mkv"
        if ".flv" in url_lower:
            return "flv"
        return "mp4"  # 默认

    @staticmethod
    def _guess_image_ext(url: str) -> str:
        """从 URL 推断图片扩展名"""
        url_lower = url.split("?")[0].lower()
        for ext in ("jpg", "jpeg", "png", "webp", "gif"):
            if f".{ext}" in url_lower:
                return "jpeg" if ext == "jpg" else ext
        return "jpg"

    @staticmethod
    def extract_video_desc_html(page) -> str:
        """提取视频描述区域的 HTML，转为 Markdown（当正文为空时有用）"""
        selectors = [
            "[class*='video-desc']",
            "[class*='note-desc']",
            "[class*='desc']",
            "#detail-desc",
        ]
        for sel in selectors:
            try:
                el = page.query_selector(sel)
                if el:
                    html = el.inner_html()
                    text = md(html, heading_style="ATX").strip()
                    if text and len(text) > 5:
                        return text
            except Exception:
                continue
        return ""
