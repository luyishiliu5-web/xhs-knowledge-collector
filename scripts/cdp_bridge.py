"""
CDP Bridge 客户端 - 从用户 Windows Chrome 获取 cookie
通过 Hermes CDP Bridge 扩展的 HTTP API（http://localhost:18790）
"""
import json
import time
import logging
import subprocess
import os
from pathlib import Path
from typing import Optional
from urllib.request import Request, urlopen
from urllib.error import URLError

logger = logging.getLogger(__name__)

BRIDGE_URL = "http://localhost:18790"
TIMEOUT = 10
SERVER_DIR = Path("/mnt/d/hermes/workspace/projects/hermes-cdp-bridge")
START_SCRIPT = SERVER_DIR / "start.sh"


class CdpBridgeError(Exception):
    """CDP Bridge 连接异常"""
    pass


def _http_post(path: str, body: dict) -> dict:
    """发 HTTP POST 到 CDP Bridge"""
    url = f"{BRIDGE_URL}{path}"
    data = json.dumps(body).encode("utf-8")
    req = Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    try:
        with urlopen(req, timeout=TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except URLError as e:
        raise CdpBridgeError(f"连接 CDP Bridge 失败: {e}")


def _http_get(path: str) -> dict:
    """发 HTTP GET 到 CDP Bridge"""
    url = f"{BRIDGE_URL}{path}"
    try:
        with urlopen(url, timeout=TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except URLError as e:
        raise CdpBridgeError(f"连接 CDP Bridge 失败: {e}")


def health() -> dict:
    """检查 CDP Bridge 状态"""
    return _http_get("/health")


def ensure_running() -> bool:
    """
    确保 CDP Bridge 服务器在运行。如果未运行，自动启动。

    Returns:
        True 如果服务器已就绪
    """
    # 先检查是否已在运行
    try:
        h = health()
        if h.get("status") == "ok":
            return True
    except CdpBridgeError:
        pass

    # 尝试启动服务器
    if not START_SCRIPT.exists():
        print(f"[CDP Bridge] 启动脚本不存在: {START_SCRIPT}")
        return False

    print("[CDP Bridge] 服务器未运行，尝试自动启动...")
    try:
        subprocess.run(
            ["bash", str(START_SCRIPT)],
            capture_output=True,
            timeout=15,
        )
    except (subprocess.TimeoutError, FileNotFoundError) as e:
        print(f"[CDP Bridge] 启动失败: {e}")
        return False

    # 等待就绪（最多 5 秒）
    for i in range(5):
        time.sleep(1)
        try:
            h = health()
            if h.get("status") == "ok":
                print(f"[CDP Bridge] 服务器已启动 ✅")
                return True
        except CdpBridgeError:
            continue

    print("[CDP Bridge] 服务器启动超时，请手动运行: bash start.sh")
    return False


def is_connected() -> bool:
    """检查 Chrome 扩展是否已连接（自动启动服务器）"""
    try:
        h = health()
        return h.get("extension") == "connected"
    except CdpBridgeError:
        return False


def ensure_ready() -> bool:
    """
    确保 CDP Bridge 已就绪（服务器运行 + 扩展已连接）。
    自动启动服务器，但扩展连接需要用户 Chrome 已安装扩展。

    Returns:
        True 如果一切就绪
    """
    if not ensure_running():
        return False
    if is_connected():
        return True
    print("[CDP Bridge] 服务器已启动，但 Chrome 扩展未连接")
    print("          请在 Chrome 中安装 Hermes CDP Bridge 扩展")
    return False


def list_tabs() -> list[dict]:
    """列出 Chrome 中的所有标签页"""
    result = _http_get("/tabs")
    return result.get("tabs", [])


def _find_non_chrome_tab(tabs: list[dict]) -> Optional[int]:
    """找一个非 chrome:// 的标签页来发 CDP 命令"""
    for t in tabs:
        url = t.get("url", "")
        if not url.startswith("chrome://") and url and url != "about:blank":
            return t["id"]

    # 找不到就创建新标签页（通过导航一个新 tab）
    # 用第一个可用标签页
    for t in tabs:
        url = t.get("url", "")
        if url != "about:blank":
            return t["id"]

    return None


def fetch_cookies(urls: Optional[list[str]] = None, tab_id: Optional[int] = None) -> list[dict]:
    """
    从用户 Chrome 获取 cookie。

    Args:
        urls: 要获取 cookie 的 URL 列表，默认只获取小红书
        tab_id: 指定标签页 ID（自动找非 chrome:// 的页）

    Returns:
        cookie 列表，每项包含 name/value/domain/path/secure/httpOnly 等字段
    """
    if urls is None:
        urls = ["https://www.xiaohongshu.com"]

    if not tab_id:
        tabs = list_tabs()
        tab_id = _find_non_chrome_tab(tabs)

    if not tab_id:
        raise CdpBridgeError("找不到可用的标签页来获取 cookie")

    result = _http_post("/cdp", {
        "type": "cdp:command",
        "cmd": "Network.getCookies",
        "params": {"urls": urls},
        "tabId": tab_id,
    })

    if "error" in result:
        raise CdpBridgeError(f"CDP 命令失败: {result['error']}")

    return result.get("result", {}).get("cookies", [])


def get_xiaohongshu_cookies() -> list[dict]:
    """获取小红书 cookie（自动启动 CDP Bridge + 找可用标签页）"""
    if not ensure_ready():
        raise CdpBridgeError(
            "CDP Bridge 未就绪。请确保：\n"
            "  1. Chrome 中已安装 Hermes CDP Bridge 扩展\n"
            "  2. Chrome 正在运行"
        )

    return fetch_cookies(urls=["https://www.xiaohongshu.com"])


def cookies_to_patchright(cookies: list[dict]) -> list[dict]:
    """
    将 CDP Bridge 的 cookie 格式转为 Patchright context.add_cookies() 格式。
    context.add_cookies() 要求的字段: name, value, url 或 (domain + path)
    """
    pr_cookies = []
    for c in cookies:
        entry = {
            "name": c["name"],
            "value": c["value"],
            "domain": c.get("domain", ".xiaohongshu.com"),
            "path": c.get("path", "/"),
            "secure": c.get("secure", False),
            "httpOnly": c.get("httpOnly", False),
            "sameSite": c.get("sameSite", "None"),
        }
        if "expires" in c and c["expires"]:
            entry["expires"] = c["expires"]
        pr_cookies.append(entry)

    return pr_cookies
