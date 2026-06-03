"""
Chrome 浏览器管理器 - 基于 Patchright + 持久化 Profile
核心思路：使用真实 Chrome + 专用 user_data_dir，让小红书看到"正常用户"

Cookie 注入策略：
  优先从 CDP Bridge 获取用户 Windows Chrome 的真实 cookie，
  确保 Patchright headless Chromium 也能保持登录态。
"""
import time
import random
import yaml
import logging
from pathlib import Path
from contextlib import contextmanager
from patchright.sync_api import sync_playwright, BrowserContext

from cdp_bridge import (
    get_xiaohongshu_cookies,
    cookies_to_patchright,
    ensure_ready,
    CdpBridgeError,
)

logger = logging.getLogger(__name__)


class BrowserManager:
    def __init__(self, config_path: str = None):
        if config_path is None:
            config_path = Path(__file__).parent.parent / "config.yaml"
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)

        self.chrome_path = self.config["chrome_path"]
        self.user_data_dir = str(Path(config_path).parent / self.config["user_data_dir"])
        self.behavior = self.config["behavior"]
        self._playwright = None
        self._context = None

    def _ensure_profile_dir(self):
        Path(self.user_data_dir).mkdir(parents=True, exist_ok=True)

    def _inject_xhs_cookies(self):
        """
        从 CDP Bridge 获取用户 Chrome 的小红书 cookie，注入到当前 context。
        自动启动 CDP Bridge 服务器（如未运行）。
        如果全部不可用，静默跳过（使用 Profile 中已有 cookie）。
        """
        if not ensure_ready():
            print("[Cookie] CDP Bridge 未就绪，使用本地 Profile cookie")
            return

        try:
            cookies = get_xiaohongshu_cookies()
            if not cookies:
                print("[Cookie] 未从小红书获取到 cookie（可能未登录）")
                return

            pr_cookies = cookies_to_patchright(cookies)
            self._context.add_cookies(pr_cookies)
            print(f"[Cookie] 已从 Chrome 注入 {len(pr_cookies)} 个小程序 cookie ✅")
        except CdpBridgeError as e:
            print(f"[Cookie] CDP Bridge 获取 cookie 失败: {e}")
        except Exception as e:
            print(f"[Cookie] cookie 注入异常: {e}")

    def launch(self) -> BrowserContext:
        """
        启动 Patchright Chromium 并注入 CDP Bridge cookie。
        """
        self._ensure_profile_dir()
        self._playwright = sync_playwright().start()

        self._context = self._playwright.chromium.launch_persistent_context(
            user_data_dir=self.user_data_dir,
            executable_path=self.chrome_path,
            headless=self.config.get("headless", False),
            # 以下参数刻意留空，从 Profile 自然继承：
            # viewport=None, user_agent=None, locale=None, timezone_id=None
            # 不注入任何自动化标记
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-first-run",
                "--no-default-browser-check",
            ],
        )

        # 自动注入 CDP Bridge cookie
        self._inject_xhs_cookies()

        return self._context

    def connect_cdp(self, endpoint: str = "http://localhost:9222") -> BrowserContext:
        """
        CDP 协议连接到已运行的 Chrome 实例。
        适用场景：用户正常打开 Chrome 后，通过 CDP 连接操控。
        Chrome 需要以 --remote-debugging-port=9222 启动。
        """
        self._playwright = sync_playwright().start()
        browser = self._playwright.chromium.connect_over_cdp(endpoint)
        self._context = browser.contexts[0] if browser.contexts else browser.new_context()
        return self._context

    def simulate_human_behavior(self, page):
        """模拟真人浏览行为：随机延时、拟人滚动"""
        # 初始阅读延时
        delay = random.uniform(self.behavior["min_delay"], self.behavior["max_delay"])
        time.sleep(delay)

        # 拟人滚动：分段、变速滚动
        total_height = page.evaluate("document.body.scrollHeight")
        current = 0
        while current < total_height * 0.75:  # 最多滚动到 75%
            step = random.randint(
                self.behavior["scroll_step_min"],
                self.behavior["scroll_step_max"],
            )
            current += step
            page.evaluate(f"window.scrollTo({{top: {current}, behavior: 'smooth'}})")
            time.sleep(random.uniform(
                self.behavior["scroll_delay_min"],
                self.behavior["scroll_delay_max"],
            ))
            total_height = page.evaluate("document.body.scrollHeight")

        # 滚回顶部
        page.evaluate("window.scrollTo({top: 0, behavior: 'smooth'})")
        time.sleep(1)

    def close(self):
        if self._context:
            self._context.close()
        if self._playwright:
            self._playwright.stop()


@contextmanager
def managed_browser(config_path: str = None):
    """上下文管理器：自动启动和关闭浏览器"""
    bm = BrowserManager(config_path)
    context = bm.launch()
    try:
        yield bm, context
    finally:
        bm.close()
