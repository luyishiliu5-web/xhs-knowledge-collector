"""
Chrome 浏览器管理器 - 基于 Patchright + 持久化 Profile
核心思路：使用真实 Chrome + 专用 user_data_dir，让小红书看到"正常用户"
"""
import time
import random
import yaml
from pathlib import Path
from contextlib import contextmanager
from patchright.sync_api import sync_playwright, BrowserContext


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

    def launch(self) -> BrowserContext:
        """
        启动浏览器并返回持久化上下文。
        不设置 viewport/user_agent，让 Profile 自然继承指纹。
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
