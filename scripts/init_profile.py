"""
Profile 初始化脚本 - 首次手动登录小红书
======================================
运行此脚本会打开一个 Chrome 窗口，使用专用的 user_data_dir。
你在里面手动登录小红书后，关闭窗口即可。
之后所有采集操作都会复用这个登录态。

用法: python scripts/init_profile.py
"""
import sys
import yaml
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from browser_manager import BrowserManager


def main():
    print("=" * 60)
    print("  小红书 Profile 初始化")
    print("=" * 60)
    print()
    print("接下来会打开一个 Chrome 窗口。")
    print("请执行以下步骤：")
    print()
    print("  1. 在打开的 Chrome 中访问 https://www.xiaohongshu.com")
    print("  2. 手动扫码或手机号登录")
    print("  3. 确认登录成功后，随意浏览一两篇笔记（模拟真用户）")
    print("  4. 回到这里按 Enter，我会帮你关闭浏览器")
    print()
    print("登录态将保存到 user_data/ 目录，以后无需重复登录。")
    print("=" * 60)
    input("按 Enter 开始...")

    config_path = Path(__file__).parent.parent / "config.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    user_data_dir = str(Path(config_path).parent / config["user_data_dir"])
    print(f"\n[Profile] 用户数据目录: {user_data_dir}")

    bm = BrowserManager(str(config_path))
    context = bm.launch()

    page = context.new_page()
    page.goto("https://www.xiaohongshu.com", wait_until="domcontentloaded")
    print("[Profile] 已打开小红书首页，请手动登录...")

    input("\n完成登录后按 Enter 关闭浏览器...")

    bm.close()
    print("[Profile] 登录态已保存 ✓")
    print("可以使用 main.py 开始采集了。")


if __name__ == "__main__":
    main()
