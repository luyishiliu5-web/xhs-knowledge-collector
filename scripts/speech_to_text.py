"""
视频语音转文字模块 — 字幕提取 + ASR
====================================
从下载的视频中提取语音/字幕，转为文字稿。

三层策略（按优先级）：
1. 提取内嵌软字幕（SRT/ASS/WebVTT）→ 直接得到文字
2. 使用本地 Whisper 模型做语音识别 → 转文字
3. OpenAI Whisper API → 云端兜底

不依赖多模态大模型 — 纯音频处理 + 传统 ASR。

依赖:
  - ffmpeg（音频提取、字幕提取）
  - openai-whisper（本地模型）
  - openai Python SDK（API 兜底，可选）
"""

import subprocess
import shutil
import tempfile
import json
import re
from pathlib import Path
from datetime import datetime
from typing import Optional, Tuple

import yaml


class SpeechToText:
    """视频 → 文字稿 转换器"""

    def __init__(self, config_path: str = None):
        if config_path is None:
            config_path = Path(__file__).parent.parent / "config.yaml"
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)

        self.asr_config = self.config.get("asr", {})
        self.whisper_model = self.asr_config.get("whisper_model", "medium")
        self.whisper_language = self.asr_config.get("whisper_language", "zh")
        self.use_api_fallback = self.asr_config.get("use_api_fallback", False)
        self.max_audio_seconds = self.asr_config.get("max_audio_seconds", 3600)
        # 自动检测 ffmpeg（兼容 WSL 下的 ffmpeg.exe）
        self._ffmpeg = self._find_ffmpeg()

    @staticmethod
    def _find_ffmpeg() -> Optional[str]:
        """查找系统上的 ffmpeg，兼容 WSL（Windows ffmpeg.exe）"""
        for name in ("ffmpeg", "ffmpeg.exe"):
            if shutil.which(name):
                return name
        return None

    def transcribe(self, video_path: str, note_id: str = "") -> dict:
        """
        从视频中提取完整的语音文字稿。

        Args:
            video_path: 本地视频文件路径
            note_id: 笔记 ID（用于日志）

        Returns:
            {
                "transcript": str,     # 完整文字稿
                "source": str,         # "subtitle" | "whisper_local" | "whisper_api"
                "language": str,       # 检测到的语言
                "duration_seconds": float,
                "segments": [          # 带时间戳的分段（Whisper 输出）
                    {"start": 0.0, "end": 5.2, "text": "..."},
                    ...
                ],
            }
        """
        result = {
            "transcript": "",
            "source": "",
            "language": "",
            "duration_seconds": 0.0,
            "segments": [],
        }

        vp = Path(video_path)
        if not vp.exists():
            print(f"[ASR] 视频文件不存在: {video_path}")
            return result

        print(f"[ASR] 开始处理: {vp.name}")

        # ── 策略 1: 提取软字幕 ──
        subtitle_text = self._extract_subtitles(video_path)
        if subtitle_text and len(subtitle_text) > 50:
            print(f"[ASR] ✅ 成功提取内嵌字幕 ({len(subtitle_text)} 字)")
            result["transcript"] = subtitle_text
            result["source"] = "subtitle"
            result["language"] = self._detect_language(subtitle_text)
            return result

        print("[ASR] 未发现内嵌字幕，使用语音识别...")

        # ── 策略 2: 提取音频 + 本地 Whisper ──
        audio_path = self._extract_audio(video_path)
        if audio_path and audio_path.exists():
            whisper_result = self._whisper_local(audio_path)
            # 清理临时音频
            try:
                audio_path.unlink()
            except Exception:
                pass

            if whisper_result and whisper_result.get("transcript"):
                print(
                    f"[ASR] ✅ Whisper 本地识别完成 "
                    f"({len(whisper_result['transcript'])} 字)"
                )
                return whisper_result

        # ── 策略 3: OpenAI Whisper API 兜底 ──
        if self.use_api_fallback:
            print("[ASR] 本地模型失败，尝试 OpenAI Whisper API...")
            api_result = self._whisper_api(video_path)
            if api_result and api_result.get("transcript"):
                print(
                    f"[ASR] ✅ Whisper API 识别完成 "
                    f"({len(api_result['transcript'])} 字)"
                )
                return api_result

        print("[ASR] ❌ 所有语音识别策略均失败")
        return result

    # ── 字幕提取 ─────────────────────────────────────────

    def _extract_subtitles(self, video_path: str) -> str:
        """
        从视频中提取软字幕（SRT/ASS/WebVTT 等）。
        使用 ffmpeg 检测并提取字幕流。
        """
        if not self._ffmpeg:
            return ""

        # 先查看有哪些字幕流
        try:
            probe = subprocess.run(
                [
                    self._ffmpeg, "-i", video_path,
                    "-c", "copy", "-map", "0:s:0",
                    "-f", "srt", "-",
                ],
                capture_output=True, text=True, timeout=30,
            )
            if probe.returncode == 0 and probe.stdout.strip():
                text = self._clean_srt(probe.stdout)
                if text:
                    return text
        except Exception:
            pass

        # 尝试导出到临时文件
        with tempfile.NamedTemporaryFile(
            suffix=".srt", delete=False, mode="w+", encoding="utf-8"
        ) as tmp:
            tmp_path = tmp.name

        try:
            result = subprocess.run(
                [
                    self._ffmpeg, "-y",
                    "-i", video_path,
                    "-map", "0:s:0",
                    "-c:s", "srt",
                    tmp_path,
                ],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0:
                text = Path(tmp_path).read_text(encoding="utf-8", errors="replace")
                cleaned = self._clean_srt(text)
                if cleaned:
                    return cleaned
        except Exception:
            pass
        finally:
            Path(tmp_path).unlink(missing_ok=True)

        return ""

    @staticmethod
    def _clean_srt(srt_text: str) -> str:
        """去除 SRT 的时间戳和序号，只保留纯文本"""
        # 移除序号行 "123"
        text = re.sub(r"^\d+\s*$", "", srt_text, flags=re.MULTILINE)
        # 移除时间戳行 "00:00:01,000 --> 00:00:05,000"
        text = re.sub(
            r"\d{2}:\d{2}:\d{2}[.,]\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}[.,]\d{3}",
            "",
            text,
        )
        # 移除 HTML 标签
        text = re.sub(r"<[^>]+>", "", text)
        # 合并空行
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        return "\n".join(lines)

    # ── 音频提取 ─────────────────────────────────────────

    def _extract_audio(self, video_path: str) -> Optional[Path]:
        """从视频中提取音频轨到临时 WAV 文件"""
        if not self._ffmpeg:
            print("[ASR] 未安装 ffmpeg，无法提取音频")
            return None

        audio_path = Path(video_path).with_suffix(".wav")

        try:
            result = subprocess.run(
                [
                    self._ffmpeg, "-y",
                    "-i", str(video_path),
                    "-vn",                    # 不要视频
                    "-acodec", "pcm_s16le",   # 16-bit PCM
                    "-ar", "16000",           # 16kHz 采样率（Whisper 推荐）
                    "-ac", "1",               # 单声道
                    "-t", str(self.max_audio_seconds),  # 限长
                    str(audio_path),
                ],
                capture_output=True, text=True, timeout=300,
            )
            if audio_path.exists() and audio_path.stat().st_size > 0:
                return audio_path
            print(f"[ASR] 音频提取失败: {result.stderr[-200:]}")
        except subprocess.TimeoutExpired:
            print("[ASR] 音频提取超时")
        except Exception as e:
            print(f"[ASR] 音频提取错误: {e}")

        return None

    # ── 本地 Whisper ─────────────────────────────────────

    def _whisper_local(self, audio_path: Path) -> Optional[dict]:
        """
        使用本地 openai-whisper 模型进行语音识别。
        """
        try:
            import whisper
        except ImportError:
            print("[ASR] 未安装 openai-whisper，请运行: pip install openai-whisper")
            return None

        try:
            print(f"[ASR] 加载 Whisper 模型: {self.whisper_model}...")
            model = whisper.load_model(self.whisper_model)

            print(f"[ASR] 开始语音识别（语言: {self.whisper_language}）...")
            transcribe_result = model.transcribe(
                str(audio_path),
                language=self.whisper_language if self.whisper_language != "auto" else None,
                verbose=False,
                task="transcribe",
                # 中文优化参数
                word_timestamps=False,
                condition_on_previous_text=False,
                no_speech_threshold=0.6,
                logprob_threshold=-1.0,
                compression_ratio_threshold=2.4,
            )

            segments = []
            for seg in transcribe_result.get("segments", []):
                segments.append({
                    "start": round(seg.get("start", 0), 1),
                    "end": round(seg.get("end", 0), 1),
                    "text": seg.get("text", "").strip(),
                })

            transcript = transcribe_result.get("text", "").strip()

            return {
                "transcript": transcript,
                "source": "whisper_local",
                "language": transcribe_result.get("language", self.whisper_language),
                "duration_seconds": self._get_audio_duration(audio_path),
                "segments": segments,
            }

        except Exception as e:
            print(f"[ASR] Whisper 识别失败: {e}")
            return None

    # ── OpenAI Whisper API 兜底 ───────────────────────────

    def _whisper_api(self, video_path: str) -> Optional[dict]:
        """
        使用 OpenAI Whisper API 进行云端识别。
        直接将视频文件上传（OpenAI API 支持多种格式）。
        """
        try:
            from openai import OpenAI
        except ImportError:
            print("[ASR] 未安装 openai SDK，请运行: pip install openai")
            return None

        try:
            client = OpenAI()

            # 限制文件大小（OpenAI API 限制 25MB）
            vp = Path(video_path)
            file_size_mb = vp.stat().st_size / (1024 * 1024)

            if file_size_mb > 25:
                print(f"[ASR] 视频过大 ({file_size_mb:.1f} MB > 25MB)，提取音频后上传...")
                audio_path = self._extract_audio(video_path)
                if not audio_path:
                    return None
                upload_file = open(str(audio_path), "rb")
                cleanup_audio = True
            else:
                upload_file = open(str(vp), "rb")
                cleanup_audio = False

            try:
                transcript = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=upload_file,
                    language=self.whisper_language if self.whisper_language != "auto" else None,
                    response_format="verbose_json",
                )
            finally:
                upload_file.close()
                if cleanup_audio and 'audio_path' in locals():
                    try:
                        audio_path.unlink()
                    except Exception:
                        pass

            text = transcript.text.strip()
            segments = []
            if hasattr(transcript, "segments") and transcript.segments:
                for seg in transcript.segments:
                    segments.append({
                        "start": round(seg.get("start", 0), 1),
                        "end": round(seg.get("end", 0), 1),
                        "text": seg.get("text", "").strip(),
                    })

            return {
                "transcript": text,
                "source": "whisper_api",
                "language": getattr(transcript, "language", self.whisper_language),
                "duration_seconds": getattr(transcript, "duration", 0),
                "segments": segments,
            }

        except Exception as e:
            print(f"[ASR] Whisper API 失败: {e}")
            return None

    # ── 工具方法 ──────────────────────────────────────────

    @staticmethod
    def _get_audio_duration(audio_path: Path) -> float:
        """获取音频时长（秒）"""
        ffprobe = None
        for name in ("ffprobe", "ffprobe.exe"):
            if shutil.which(name):
                ffprobe = name
                break
        if not ffprobe:
            return 0.0
        try:
            result = subprocess.run(
                [
                    ffprobe, "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    str(audio_path),
                ],
                capture_output=True, text=True, timeout=10,
            )
            return float(result.stdout.strip())
        except Exception:
            return 0.0

    @staticmethod
    def _detect_language(text: str) -> str:
        """简单的中文/英文检测"""
        chinese_chars = len(re.findall(r"[一-鿿]", text))
        total_chars = len(text.replace(" ", "").replace("\n", ""))
        if total_chars > 0 and chinese_chars / max(total_chars, 1) > 0.3:
            return "zh"
        return "en"

    @staticmethod
    def format_transcript_as_markdown(
        transcript: str,
        segments: list = None,
        title: str = "语音转文字稿",
    ) -> str:
        """
        将文字稿格式化为 Markdown。

        Args:
            transcript: 纯文本文字稿
            segments: 带时间戳的分段（可选）
            title: 标题

        Returns:
            Markdown 格式的文字稿
        """
        md = f"## {title}\n\n"

        if segments:
            md += "> ⏱ 以下内容带时间戳\n\n"
            for seg in segments:
                start = seg.get("start", 0)
                end = seg.get("end", 0)
                text = seg.get("text", "")
                # 格式化为 mm:ss
                start_str = f"{int(start // 60)}:{int(start % 60):02d}"
                end_str = f"{int(end // 60)}:{int(end % 60):02d}"
                md += f"**[{start_str} → {end_str}]** {text}\n\n"
        else:
            md += transcript + "\n\n"

        return md
