"""
小红书内容采集 - 主入口
======================
用法:
  python scripts/main.py collect <url> [--category 分类] [--tags 标签1,标签2] [--summary] [--no-video]
  python scripts/main.py search <关键词> [--count 10] [--category 分类] [--no-video]

示例:
  python scripts/main.py collect https://www.xiaohongshu.com/explore/abc123 --category AI技术 --tags LLM,Agent
  python scripts/main.py collect https://www.xiaohongshu.com/explore/abc123 --no-video  # 跳过视频下载
  python scripts/main.py search "大模型应用" --count 5 --category AI技术
"""
import sys
import argparse
import yaml
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from browser_manager import managed_browser
from xhs_collector import XHSCollector
from wiki_writer import WikiWriter

CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"


def collect_single(
    url: str,
    category: str,
    tags: list,
    do_summary: bool = False,
    download_video: bool = True,
):
    """采集单篇笔记"""
    with managed_browser(str(CONFIG_PATH)) as (bm, context):
        page = context.new_page()
        collector = XHSCollector(str(CONFIG_PATH))

        # 模拟真人行为
        bm.simulate_human_behavior(page)

        # 采集（含视频）
        data = collector.collect(page, url, download_video=download_video)

    # 写入知识库
    writer = WikiWriter(str(CONFIG_PATH))
    if do_summary:
        writer.write(data, category, tags)
        print(f"[完成] 已写入知识库（待 AI 总结）")
    else:
        filepath = writer.write(data, category, tags)
        print(f"[完成] 已写入: {filepath}")

    return data


def collect_search(
    keyword: str,
    count: int,
    category: str,
    tags: list,
    download_video: bool = True,
):
    """搜索并批量采集"""
    with managed_browser(str(CONFIG_PATH)) as (bm, context):
        page = context.new_page()
        collector = XHSCollector(str(CONFIG_PATH))

        # 先搜索获取 URL 列表
        print(f"[搜索] 关键词: {keyword}")
        urls = collector.collect_urls_from_search(page, keyword, count)
        print(f"[搜索] 找到 {len(urls)} 条结果")

        writer = WikiWriter(str(CONFIG_PATH))
        for i, url in enumerate(urls, 1):
            print(f"\n[{i}/{len(urls)}] 采集: {url}")
            try:
                bm.simulate_human_behavior(page)
                data = collector.collect(page, url, download_video=download_video)
                filepath = writer.write(data, category, tags)
                print(f"  -> {filepath.name}")
            except Exception as e:
                print(f"  -> 失败: {e}")
                continue

            # 频率控制：两次采集之间间隔
            if i < len(urls):
                import time
                time.sleep(30)


def main():
    parser = argparse.ArgumentParser(description="小红书内容采集 -> LLMWiki")
    subparsers = parser.add_subparsers(dest="command", help="采集模式")

    # 单篇采集
    single = subparsers.add_parser("collect", help="采集单篇笔记")
    single.add_argument("url", help="小红书笔记 URL")
    single.add_argument("--category", "-c", default="未分类", help="分类目录")
    single.add_argument("--tags", "-t", default="", help="标签（逗号分隔）")
    single.add_argument("--summary", "-s", action="store_true", help="标记需要 AI 总结")
    single.add_argument(
        "--no-video",
        action="store_true",
        help="跳过视频下载（仅采集文字，速度更快）",
    )

    # 搜索采集
    search = subparsers.add_parser("search", help="搜索并批量采集")
    search.add_argument("keyword", help="搜索关键词")
    search.add_argument("--count", "-n", type=int, default=10, help="采集数量")
    search.add_argument("--category", "-c", default="未分类", help="分类目录")
    search.add_argument("--tags", "-t", default="", help="标签（逗号分隔）")
    search.add_argument(
        "--no-video",
        action="store_true",
        help="跳过视频下载（仅采集文字，速度更快）",
    )

    args = parser.parse_args()

    if args.command == "collect":
        tags = [t.strip() for t in args.tags.split(",") if t.strip()]
        download_video = not getattr(args, "no_video", False)
        collect_single(args.url, args.category, tags, args.summary, download_video)

    elif args.command == "search":
        tags = [t.strip() for t in args.tags.split(",") if t.strip()]
        download_video = not getattr(args, "no_video", False)
        collect_search(args.keyword, args.count, args.category, tags, download_video)

    else:
        # 兼容旧用法：直接传 URL
        if len(sys.argv) >= 2 and sys.argv[1] not in ("collect", "search", "-h", "--help"):
            url = sys.argv[1]
            category = "未分类"
            tags = []
            download_video = True
            for i, arg in enumerate(sys.argv[2:], 2):
                if arg == "--category" and i + 1 < len(sys.argv):
                    category = sys.argv[i + 1]
                elif arg == "--tags" and i + 1 < len(sys.argv):
                    tags = [t.strip() for t in sys.argv[i + 1].split(",") if t.strip()]
                elif arg == "--no-video":
                    download_video = False
            collect_single(url, category, tags, download_video=download_video)
            return

        parser.print_help()


if __name__ == "__main__":
    main()
