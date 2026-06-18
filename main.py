# -*- coding: utf-8 -*-
"""
B 站字幕获取工具
================
功能：
    1. 用户输入 B 站视频 URL（支持完整 URL 或纯 BV 号）
    2. 自动通过 B 站官方接口获取视频元信息和字幕列表
    3. 拉取字幕 JSON 并在 GUI 中显示
    4. 同时把字幕保存为 txt 到项目目录的 subtitles 文件夹中
    5. 文件名使用视频标题（已剔除 Windows 非法字符）

新增功能（v2）：
    1. 支持 SESSDATA cookie 注入（GUI 提供隐藏输入框），解除部分视频字幕锁定
    2. 支持 Playwright 浏览器自动化（GUI 提供勾选框）作为 fallback，
       可同时获取 UP 主上传的 CC 字幕和 AI 字幕
       - 使用持久化 chrome_profile，首次手动登录后下次自动复用登录态
       - 浏览器用完后不关闭，保持打开以便复用

新增功能（v3）：
    1. 支持 Selenium + 本机 Chrome 作为第三种字幕获取方式
       - 用 undetected_chromedriver 绕过 B 站反自动化检测
       - 复制 Chrome User Data 到项目目录（避免与正在运行的 Chrome 冲突）
       - 支持 Network 拦截（抓 ai_subtitle JSON）+ DOM 抓取（拖进度条）

依赖：
    pip install requests playwright selenium undetected-chromedriver
    playwright install chromium
    tkinter 由 Python 自带（标准库），无需安装

作者：爱芮
"""

# === Windows 编码处理：让 print 不乱码（GBK -> UTF-8） ===
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# === 标准库 ===
import re
import os
import json
import shutil
import threading
import subprocess
from datetime import timedelta
import tkinter as tk
from tkinter import scrolledtext, messagebox

# === 第三方库 ===
try:
    import requests
except ImportError:
    print("=" * 60)
    print("[错误] 缺少 requests 库！")
    print("请在命令行执行：pip install requests")
    print("=" * 60)
    sys.exit(1)

# Playwright 是可选依赖（仅在用户勾选「使用 Playwright」时才需要）
# 用 try/except 包裹，缺失时给出明确提示，不强制要求所有用户都安装
try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

# Selenium + undetected_chromedriver 是可选依赖（仅在用户选择「Selenium 优先」时才需要）
try:
    import undetected_chromedriver as uc
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False


# ============================================================================
# 1. 常量与全局配置
# ============================================================================

# B 站 API 地址
BILI_VIEW_API = "https://api.bilibili.com/x/web-interface/view"

# B 站 API 强制校验的请求头
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.bilibili.com",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9",
}

# 字幕保存目录（相对当前 main.py 所在目录）
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
SUBTITLE_DIR = os.path.join(PROJECT_DIR, "subtitles")

# Playwright 持久化浏览器配置目录
# - 第一次运行时会自动创建
# - 用户在弹出的浏览器里登录 B 站一次后，cookies 会保留在这个目录
# - 下次再启动就直接带上登录态，无需重新登录
PLAYWRIGHT_USER_DATA_DIR = os.path.join(PROJECT_DIR, "chrome_profile")

# 自动登录专用的独立 profile 目录（避免和上面 fetch_subtitle_via_playwright 冲突）
PLAYWRIGHT_LOGIN_USER_DATA_DIR = os.path.join(PROJECT_DIR, "bili_login_profile")

# === Selenium 方案常量（v3 新增）===
# 用本机已安装的 Chrome 绕过 B 站对自动化的检测
# 请把下面三个路径改成你自己机器上的 Chrome / ChromeDriver / User Data 位置
# 也可以用环境变量 BILI_CHROME_EXE / BILI_CHROME_USER_DATA / BILI_CHROMEDRIVER_EXE 覆盖
import os as _os_for_chrome_paths
_CHROME_HINT_WIN = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
_CHROMEDRIVER_HINT_WIN = r"C:\Program Files\Google\Chrome\Application\chromedriver.exe"
_CHROME_USER_DATA_HINT_WIN = _os_for_chrome_paths.expandvars(
    r"%LOCALAPPDATA%\Google\Chrome\User Data"
)
CHROME_EXE = _os_for_chrome_paths.environ.get("BILI_CHROME_EXE", _CHROME_HINT_WIN)
CHROME_USER_DATA_DIR = _os_for_chrome_paths.environ.get(
    "BILI_CHROME_USER_DATA", _CHROME_USER_DATA_HINT_WIN
)
CHROMEDRIVER_EXE = _os_for_chrome_paths.environ.get(
    "BILI_CHROMEDRIVER_EXE", _CHROMEDRIVER_HINT_WIN
)

# Selenium 用的 Chrome User Data 副本目录（避免与正在运行的 Chrome 冲突）
SELENIUM_USER_DATA_DIR = os.path.join(PROJECT_DIR, "chrome_userdata_copy")

# Selenium 启动版本（本机 Chrome 大版本）
SELENIUM_CHROME_VERSION = 120

# Selenium 等待 AI 字幕生成的超时（秒）
SELENIUM_AI_SUBTITLE_WAIT = 15
# Selenium 拖进度条 DOM 抓取时，每次的间隔（秒）
SELENIUM_DOM_SCRAPE_INTERVAL = 0.5
# Selenium 登录超时（秒）
SELENIUM_LOGIN_TIMEOUT = 120

# cookies 缓存文件路径（JSON 格式）
COOKIES_CACHE_FILE = os.path.join(PROJECT_DIR, "bili_cookies.json")

# 自动登录超时（秒）
LOGIN_TIMEOUT = 120

# 登录成功后跳转的目标 URL（B 站登录成功后会跳回这里）
LOGIN_SUCCESS_URL_PREFIX = "https://www.bilibili.com"

# Windows 文件名非法字符：< > : " / \ | ? *
ILLEGAL_FILENAME_CHARS = r'<>:"/\|?*'

# 网络请求超时（秒）
REQUEST_TIMEOUT = 15

# Playwright 页面等待时间（秒）- 等待字幕数据注入 window.__INITIAL_STATE__
PLAYWRIGHT_PAGE_LOAD_WAIT = 8
PLAYWRIGHT_SUBTITLE_WAIT = 5


# ============================================================================
# 2. 工具函数
# ============================================================================

def extract_bvid(url_or_bvid: str) -> str:
    """
    从用户输入中提取 BV 号。
    支持：
        - https://www.bilibili.com/video/BV1xxxxxx?spm_id_from=...
        - BV1xxxxxx
    返回：
        提取到的 BV 号（统一为 "BV" 开头），找不到则返回空串
    """
    if not url_or_bvid:
        return ""

    text = url_or_bvid.strip()
    match = re.search(r'(BV[0-9A-Za-z]+)', text, re.IGNORECASE)
    if match:
        bvid = match.group(1)
        return bvid[:2].upper() + bvid[2:]

    return ""


def sanitize_filename(name: str) -> str:
    """
    把任意字符串变成 Windows 合法文件名。
    - 剔除 < > : " / \ | ? *
    - 去掉首尾空白和点
    - 限制长度（防止 255 限制）
    - 如果清空后没东西，返回 "untitled"
    """
    if not name:
        return "untitled"

    cleaned = re.sub(f'[{ILLEGAL_FILENAME_CHARS}]', '_', name)
    cleaned = cleaned.strip().strip('.')
    cleaned = re.sub(r'\s+', ' ', cleaned)
    if len(cleaned) > 100:
        cleaned = cleaned[:100]
    return cleaned or "untitled"


def format_timestamp(seconds: float) -> str:
    """
    把秒数格式化为 00:00:00.000 形式（SRT/VTT 风格）。
    """
    if seconds is None or seconds < 0:
        seconds = 0.0
    td = timedelta(seconds=seconds)
    total_seconds = int(td.total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60
    millis = int(round((seconds - int(seconds)) * 1000))
    if millis >= 1000:
        millis = 999
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"


# ============================================================================
# 3. 字幕获取核心逻辑（纯函数，方便单测）
# ============================================================================

def _build_headers_with_cookies(cookies: dict = None) -> dict:
    """
    根据 cookies 字典构造请求头。
    - 如果 cookies 为空，返回默认 headers
    - 否则把 cookies 拼成 "key1=value1; key2=value2" 注入到 Cookie 头

    为什么这样处理：requests 的 cookies 参数需要 url 配合才能自动处理 domain，
    而 B 站 API 跨域（api.bilibili.com vs www.bilibili.com），手动注入 Cookie 头
    是最稳的方案。
    """
    headers = dict(DEFAULT_HEADERS)
    if cookies:
        cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items() if v)
        if cookie_str:
            headers["Cookie"] = cookie_str
    return headers


def fetch_video_info(bvid: str, cookies: dict = None) -> dict:
    """
    调用 B 站 view 接口获取视频元信息。
    参数：
        bvid: 视频 BV 号
        cookies: 可选 dict, 形如 {"SESSDATA": "xxx", "buvid3": "yyy"}
                 如果提供，会作为 Cookie 头发给 B 站
    返回 dict：
        - title: 视频标题
        - bvid: BV 号
        - subtitle_list: list[dict] 字幕列表
          每项: {"subtitle_url": "...", "lan": "zh-CN", "lan_doc": "中文(简体)", "ai_type": 0/1}
        - aid: 视频 aid（备用）
    抛出：
        网络/JSON/业务错误
    """
    api = f"{BILI_VIEW_API}?bvid={bvid}"
    headers = _build_headers_with_cookies(cookies)
    resp = requests.get(api, headers=headers, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()

    if data.get("code") != 0:
        msg = data.get("message", "未知错误")
        raise RuntimeError(f"B 站 API 返回错误(code={data.get('code')}): {msg}")

    payload = data.get("data") or {}
    title = payload.get("title", "").strip()
    subtitle_block = payload.get("subtitle") or {}
    subtitle_list = subtitle_block.get("list") or []

    return {
        "title": title or f"untitled_{bvid}",
        "bvid": bvid,
        "subtitle_list": subtitle_list,
        "aid": payload.get("aid"),
    }


def fetch_subtitle_json(subtitle_url: str, cookies: dict = None) -> list:
    """
    拉取字幕 JSON 并返回 body 列表。
    B 站返回的 subtitle_url 是 // 开头，需要补 https://
    body 中每项形如：
        {"from": 0.0, "to": 5.2, "content": "你好", "location": 0}
    """
    if not subtitle_url:
        raise ValueError("subtitle_url 为空")

    if subtitle_url.startswith("//"):
        full_url = "https:" + subtitle_url
    elif subtitle_url.startswith("http"):
        full_url = subtitle_url
    else:
        full_url = "https://" + subtitle_url

    headers = _build_headers_with_cookies(cookies)
    resp = requests.get(full_url, headers=headers, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()

    body = data.get("body")
    if not isinstance(body, list):
        raise RuntimeError("字幕 JSON 格式异常：缺少 body 列表")
    return body


def format_subtitle_text(body: list) -> str:
    """
    把字幕 body 列表格式化为可读文本：
        00:00:00.000 --> 00:00:05.200: 你好
    """
    lines = []
    for item in body:
        start = item.get("from", 0.0)
        end = item.get("to", 0.0)
        content = (item.get("content") or "").strip()
        if not content:
            continue
        line = f"{format_timestamp(start)} --> {format_timestamp(end)}: {content}"
        lines.append(line)
    return "\n".join(lines)


def save_subtitle_to_file(text: str, video_title: str) -> str:
    """
    保存字幕到 subtitles 目录，返回绝对路径。
    文件名：<sanitized_title>.txt
    """
    os.makedirs(SUBTITLE_DIR, exist_ok=True)
    safe_name = sanitize_filename(video_title)
    file_path = os.path.join(SUBTITLE_DIR, f"{safe_name}.txt")
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(text)
    return file_path


# ============================================================================
# 4. 自动登录 B 站（Playwright 扫码登录 + cookies 缓存）
# ============================================================================

def save_cookies_to_cache(cookies: dict) -> None:
    """
    把 cookies dict 保存到 bili_cookies.json，同时附带保存时间。
    cookies: {"SESSDATA": "xxx", "buvid3": "yyy", ...}
    """
    payload = {
        "saved_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "cookies": dict(cookies or {}),
    }
    with open(COOKIES_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def load_cookies_from_cache() -> dict:
    """
    从 bili_cookies.json 读取 cookies。
    - 文件不存在 / 损坏 → 返回 None
    - 解析失败 / cookies 字段为空 → 返回 None
    返回：cookies dict（不含时间戳）
    """
    if not os.path.isfile(COOKIES_CACHE_FILE):
        return None
    try:
        with open(COOKIES_CACHE_FILE, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    cookies = payload.get("cookies") if isinstance(payload, dict) else None
    if not isinstance(cookies, dict) or not cookies:
        return None
    return cookies


def is_cookies_valid(cookies: dict) -> bool:
    """
    检查 cookies 是否"看起来有效"：
        - 存在 SESSDATA 字段
        - SESSDATA 不为空字符串
    严格来说 SESSDATA 过期需要打 nav 接口验证，但那种网络检查放到 worker 里更合适。
    """
    if not isinstance(cookies, dict):
        return False
    sess = cookies.get("SESSDATA") or ""
    return bool(sess and sess.strip())


def _extract_cookies_from_playwright_context(context) -> dict:
    """
    从 Playwright BrowserContext 提取需要的 cookies（B 站域名）。
    过滤 domain 包含 bilibili.com 的，统一转成 {name: value} 格式。
    """
    try:
        raw_cookies = context.cookies()
    except Exception:
        return {}
    extracted = {}
    for ck in raw_cookies:
        domain = (ck.get("domain") or "").lower()
        name = ck.get("name")
        value = ck.get("value")
        if not name or value is None:
            continue
        if "bilibili.com" not in domain:
            continue
        extracted[name] = value
    return extracted


def bili_login_with_playwright(status_callback=None, headless: bool = False) -> dict:
    """
    用 Playwright 打开 B 站登录页，等用户扫码登录。
    - status_callback: 可选 f(str) 用于把进度发到 GUI 状态栏
    - headless: True=无头(不能扫码), False=有窗口(默认，必须有窗口才能看到二维码)
    返回：登录后的 cookies dict，失败返回 None
    抛出：
        ImportError: Playwright 未安装
        RuntimeError: 启动失败 / 登录超时
    """
    if not PLAYWRIGHT_AVAILABLE:
        raise ImportError(
            "未安装 Playwright，请运行：\n"
            "  pip install playwright\n"
            "  playwright install chromium"
        )

    def emit(msg: str):
        if status_callback:
            try:
                status_callback(msg)
            except Exception:
                pass

    os.makedirs(PLAYWRIGHT_LOGIN_USER_DATA_DIR, exist_ok=True)
    emit("正在打开浏览器 ...")

    with sync_playwright() as p:
        # 优先用本机 Chrome，没有再 fallback 内置 chromium
        browser = None
        try:
            browser = p.chromium.launch_persistent_context(
                user_data_dir=PLAYWRIGHT_LOGIN_USER_DATA_DIR,
                headless=headless,
                channel="chrome",
                viewport={"width": 1280, "height": 800},
                locale="zh-CN",
            )
        except Exception:
            emit("本机 Chrome 不可用，尝试内置 chromium ...")
            try:
                browser = p.chromium.launch_persistent_context(
                    user_data_dir=PLAYWRIGHT_LOGIN_USER_DATA_DIR,
                    headless=headless,
                    viewport={"width": 1280, "height": 800},
                    locale="zh-CN",
                )
            except Exception as e:
                raise RuntimeError(
                    f"启动浏览器失败：{e}\n\n"
                    "请确认已执行：playwright install chromium"
                ) from e

        try:
            page = browser.pages[0] if browser.pages else browser.new_page()
            emit("正在打开 B 站登录页 ...")
            try:
                page.goto(
                    "https://passport.bilibili.com/login",
                    wait_until="domcontentloaded",
                    timeout=30000,
                )
            except Exception as e:
                raise RuntimeError(f"打开 B 站登录页失败：{e}") from e

            emit("请在浏览器中用 B 站 App 扫码登录（超时 120 秒） ...")

            # 轮询检测登录成功（URL 跳到 www.bilibili.com）
            import time
            deadline = time.time() + LOGIN_TIMEOUT
            success = False
            last_emit = 0.0
            while time.time() < deadline:
                try:
                    current_url = page.url or ""
                except Exception:
                    current_url = ""
                # 登录成功标志：URL 跳到 www.bilibili.com
                if current_url.startswith(LOGIN_SUCCESS_URL_PREFIX) and "passport" not in current_url:
                    success = True
                    break
                # 每 5 秒发一次"还在等"提示
                now = time.time()
                if now - last_emit > 5:
                    emit(f"等待扫码登录 ...  剩余 {int(deadline - now)} 秒")
                    last_emit = now
                page.wait_for_timeout(1000)

            if not success:
                raise RuntimeError("登录超时（120 秒未扫码/确认），请重试")

            emit("登录成功 ✓  正在获取 cookies ...")
            cookies = _extract_cookies_from_playwright_context(browser)
            if not cookies or not cookies.get("SESSDATA"):
                raise RuntimeError(
                    "登录成功但未获取到 SESSDATA cookie，"
                    "可能 B 站登录接口已变更，请反馈给开发者"
                )
            return cookies

        finally:
            # 登录流程结束，关闭浏览器
            try:
                browser.close()
            except Exception:
                pass


# ============================================================================
# 5. Playwright 备用方案（拿 AI 字幕）
# ============================================================================

def _parse_subtitle_payload(payload: dict) -> list:
    """
    把 B 站页面 window.__INITIAL_STATE__ 里抽出来的 subtitle payload
    转换成统一的 body 列表格式（与 fetch_subtitle_json 返回值一致）。
    支持的字段名：
        - video_subtitle.payload: [[from, to, content], ...] （B 站 AI 字幕新格式）
        - video_subtitle.body: [{from, to, content}, ...] （旧格式）
    """
    body = []

    # 1) 新格式 payload（[[start, end, "text"], ...]）
    inner_payload = payload.get("payload")
    if isinstance(inner_payload, list) and inner_payload:
        first = inner_payload[0]
        if isinstance(first, list) and len(first) >= 3:
            for row in inner_payload:
                try:
                    start, end, content = row[0], row[1], row[2]
                    if content:
                        body.append({
                            "from": float(start),
                            "to": float(end),
                            "content": str(content).strip(),
                        })
                except (ValueError, TypeError, IndexError):
                    continue
            if body:
                return body

    # 2) 旧格式 body（[{"from":..., "to":..., "content":...}, ...]）
    inner_body = payload.get("body")
    if isinstance(inner_body, list):
        for item in inner_body:
            if not isinstance(item, dict):
                continue
            content = (item.get("content") or "").strip()
            if not content:
                continue
            body.append({
                "from": float(item.get("from", 0.0)),
                "to": float(item.get("to", 0.0)),
                "content": content,
            })
    return body


def _find_subtitle_in_state(state: dict) -> tuple:
    """
    在 window.__INITIAL_STATE__ 中递归查找 subtitle 相关数据。
    返回 (title, body, method)：
        - title: 视频标题
        - body: 字幕 body 列表（已转为标准格式）
        - method: "ai" / "cc" / None
    """
    if not isinstance(state, dict):
        return "", [], None

    # 1) 提取视频标题
    video_info = state.get("videoInfo") or {}
    if isinstance(video_info, dict):
        title = (video_info.get("title") or "").strip()
    else:
        title = ""
    if not title:
        # 备用：从 aid 字典里找
        for key in ("videoData", "video"):
            v = state.get(key)
            if isinstance(v, dict) and v.get("title"):
                title = str(v.get("title")).strip()
                break

    # 2) 提取字幕数据（多种可能的位置）
    candidates = []

    # 路径 A: videoInfo.subtitle.subtitles（最常见）
    if isinstance(video_info, dict):
        subtitle_block = video_info.get("subtitle") or {}
        if isinstance(subtitle_block, dict):
            subtitles_list = subtitle_block.get("subtitles")
            if isinstance(subtitles_list, list):
                candidates.extend(subtitles_list)

            # 路径 B: videoInfo.subtitle.list
            legacy_list = subtitle_block.get("list")
            if isinstance(legacy_list, list):
                candidates.extend(legacy_list)

    # 路径 C: 顶层 subtitles 键
    top_subs = state.get("subtitles")
    if isinstance(top_subs, list):
        candidates.extend(top_subs)

    # 3) 优先 AI 字幕（ai_type == 1），其次第一条
    ai_sub = None
    cc_sub = None
    for sub in candidates:
        if not isinstance(sub, dict):
            continue
        # ai_type 字段：0=人工 CC 字幕, 1=AI 字幕
        is_ai = sub.get("aiType") == 1 or sub.get("ai_type") == 1
        if is_ai and ai_sub is None:
            ai_sub = sub
        elif not is_ai and cc_sub is None:
            cc_sub = sub

    chosen = ai_sub or cc_sub
    if not chosen:
        return title, [], None

    method = "ai" if (ai_sub and chosen is ai_sub) else "cc"

    # 4) 从 chosen 中构造 body
    body = _parse_subtitle_payload(chosen)
    if not body:
        # 可能是 B 站 AI 字幕新格式：chosen.subtitle_url 是个 JSON URL
        sub_url = chosen.get("subtitle_url") or chosen.get("subtitleUrl")
        if sub_url:
            try:
                body = fetch_subtitle_json(sub_url)
            except Exception:
                body = []

    return title, body, method


def fetch_subtitle_via_playwright(
    bvid: str,
    status_callback=None,
    headless: bool = True,
) -> tuple:
    """
    用 Playwright 打开 B 站视频页面，从 window.__INITIAL_STATE__ 提取字幕。
    这种方式可以拿到 AI 字幕（ai_type=1），是 API 接口拿不到的。

    参数：
        bvid: 视频 BV 号
        status_callback: 可选回调函数，签名 f(msg: str)，
                          用于把进度消息发到 GUI 状态栏
        headless: True=无头模式(无窗口), False=有窗口(便于调试)
    返回：
        (title, body, method) - 同 _find_subtitle_in_state 的返回值
        任何环节失败都抛出异常，调用方负责捕获
    抛出：
        ImportError: Playwright 未安装
        RuntimeError: 浏览器启动失败 / 找不到字幕数据
    """
    if not PLAYWRIGHT_AVAILABLE:
        raise ImportError(
            "未安装 Playwright，请运行：\n"
            "  pip install playwright\n"
            "  playwright install chromium"
        )

    def emit(msg: str):
        if status_callback:
            try:
                status_callback(msg)
            except Exception:
                pass

    url = f"https://www.bilibili.com/video/{bvid}/"
    emit(f"正在用 Playwright 打开 {url} ...")

    # 确保持久化目录存在
    os.makedirs(PLAYWRIGHT_USER_DATA_DIR, exist_ok=True)

    with sync_playwright() as p:
        # 用持久化 user_data_dir 启动，这样用户登录 B 站后 cookies 会保留
        # - 注意：channel="chrome" 会用本机已安装的 Chrome（更稳）
        # - 如果本机 Chrome 路径不可用，会自动 fallback 到 chromium
        try:
            browser = p.chromium.launch_persistent_context(
                user_data_dir=PLAYWRIGHT_USER_DATA_DIR,
                headless=headless,
                channel="chrome",  # 用本机 Chrome，没有就 fallback
                viewport={"width": 1280, "height": 800},
                locale="zh-CN",
                # 不要关闭浏览器：keep_alive 让 context 持续存在
                # 实际我们下面显式不调用 close()
            )
        except Exception:
            # fallback 到内置 chromium（需要 playwright install chromium）
            emit("本机 Chrome 不可用，尝试内置 chromium ...")
            browser = p.chromium.launch_persistent_context(
                user_data_dir=PLAYWRIGHT_USER_DATA_DIR,
                headless=headless,
                viewport={"width": 1280, "height": 800},
                locale="zh-CN",
            )

        try:
            page = browser.pages[0] if browser.pages else browser.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=30000)

            emit(f"页面已加载，等待字幕数据注入 ({PLAYWRIGHT_PAGE_LOAD_WAIT}s) ...")
            page.wait_for_timeout(PLAYWRIGHT_PAGE_LOAD_WAIT * 1000)

            # 从 window.__INITIAL_STATE__ 提取
            emit("正在提取 window.__INITIAL_STATE__ 字幕数据 ...")
            initial_state = page.evaluate("() => window.__INITIAL_STATE__ || null")

            if not initial_state:
                # 等待更久再试一次
                emit("首次未拿到数据，再等一下 ...")
                page.wait_for_timeout(PLAYWRIGHT_SUBTITLE_WAIT * 1000)
                initial_state = page.evaluate("() => window.__INITIAL_STATE__ || null")

            if not initial_state:
                raise RuntimeError(
                    "页面加载后未找到 window.__INITIAL_STATE__，\n"
                    "可能需要登录 B 站（请在浏览器里扫码登录）后重试"
                )

            title, body, method = _find_subtitle_in_state(initial_state)

            if not body:
                raise RuntimeError(
                    "页面里有 __INITIAL_STATE__ 但未找到字幕数据\n"
                    "可能原因：\n"
                    "  1. 该视频没有 CC 字幕也没有 AI 字幕\n"
                    "  2. 页面结构变了，需要更新解析逻辑"
                )

            return title, body, method

        finally:
            # 关键：不关闭浏览器！保持打开以便复用登录态
            # 浏览器进程会在主程序退出时（with 结束）自动清理
            # 但 user_data_dir 里的 cookies 会保留
            pass


# ============================================================================
# 5.5 Selenium 备用方案（v3 新增）
# ============================================================================

def _ensure_selenium_user_data(status_callback=None) -> str:
    """
    确保 Selenium 用的 Chrome User Data 副本存在。
    - 如果 `chrome_userdata_copy/` 不存在 → 从本机复制
    - 如果本机 Chrome 正在运行（文件被锁）→ 退化为直接引用本机目录
      （此时要求先关闭 Chrome，否则 Chrome 会拒绝启动）
    - 已存在 → 直接复用

    返回：可用的 user-data-dir 路径
    """
    def emit(msg: str):
        if status_callback:
            try:
                status_callback(msg)
            except Exception:
                pass

    if not SELENIUM_AVAILABLE:
        raise ImportError(
            "未安装 selenium / undetected-chromedriver，请运行：\n"
            "  pip install selenium undetected-chromedriver"
        )

    # 已存在副本：直接用
    if os.path.isdir(SELENIUM_USER_DATA_DIR):
        emit(f"复用 Chrome User Data 副本: {SELENIUM_USER_DATA_DIR}")
        return SELENIUM_USER_DATA_DIR

    # 本机 Chrome User Data 不存在：直接报错
    if not os.path.isdir(CHROME_USER_DATA_DIR):
        raise RuntimeError(
            f"本机 Chrome User Data 不存在：\n{CHROME_USER_DATA_DIR}\n\n"
            "请确认 Chrome 已正确安装"
        )

    # 尝试复制（如果 Chrome 正在运行，会复制部分文件失败，但已复制的够用）
    emit(f"复制 Chrome User Data 到 {SELENIUM_USER_DATA_DIR}（首次较慢）...")
    try:
        # ignore_dangling_symlinks=True 避免符号链接问题
        shutil.copytree(
            CHROME_USER_DATA_DIR,
            SELENIUM_USER_DATA_DIR,
            ignore_dangling_symlinks=True,
        )
        emit("Chrome User Data 复制完成 ✓")
        return SELENIUM_USER_DATA_DIR
    except Exception as e:
        # 复制失败（多半是 Chrome 正在运行锁住了某些文件）
        emit(f"复制 User Data 失败: {e}")
        emit(f"改用直接引用本机目录（请先关闭 Chrome）...")
        # 这种情况 fallback 到直接用本机 User Data
        # 必须先关闭 Chrome，否则 Selenium 启动会失败
        return CHROME_USER_DATA_DIR


def fetch_subtitle_via_selenium(
    bvid: str,
    status_callback=None,
) -> tuple:
    """
    用 Selenium + 本机 Chrome 拿 B 站 AI 字幕（v3.5 升级，基于 v5 实测验证）。

    完整流程（v5 验证成功）：
        1. 启动 undetected Chrome（本机路径 + User Data 副本）
        2. 注入 SESSDATA（从 bili_cookies.json 读）
        3. 打开视频页
        4. 主动 video.play()
        5. **hover 视频**（关键洞察：让控制条显示）
        6. **JS 强制 click 字幕按钮**（.bpx-player-ctrl-subtitle-result）
        7. **JS 强制 click 中文选项**（[data-lan="ai-zh"]）
        8. 等 AI 字幕生成（首次 10-30 秒）
        9. Network 拦截 bfs/ai_subtitle/prod URL
        10. 用 requests 带 cookies 下载 JSON
        11. 返回 (title, body, method="ai")

    失败 fallback：
        - Network 拦截失败 → 拖动进度条触发（多次 currentTime 跳转 + 持续抓取）
        - 仍没拿到 → 从 window.__INITIAL_STATE__ 抓
        - 还失败 → DOM 拖进度条抓取
        - 都没拿到 → 抛 RuntimeError

    参数：
        bvid: 视频 BV 号
        status_callback: 可选 f(msg: str) 用于把进度发到 GUI 状态栏
    返回：
        (title, body, method) - method ∈ {"ai", "dom", "cc"}
        任何环节失败都抛出异常，调用方负责捕获
    抛出：
        ImportError: Selenium / undetected_chromedriver 未安装
        RuntimeError: 浏览器启动失败 / 找不到字幕数据
    """
    if not SELENIUM_AVAILABLE:
        raise ImportError(
            "未安装 selenium / undetected-chromedriver，请运行：\n"
            "  pip install selenium undetected-chromedriver"
        )

    def emit(msg: str):
        if status_callback:
            try:
                status_callback(msg)
            except Exception:
                pass

    import time
    from selenium.webdriver.common.action_chains import ActionChains

    # 0) 准备 Chrome User Data 副本
    profile_dir = _ensure_selenium_user_data(status_callback=emit)

    # 1) 检查 Chrome 二进制是否存在
    if not os.path.isfile(CHROME_EXE):
        raise RuntimeError(
            f"本机 Chrome 不存在：\n{CHROME_EXE}\n\n"
            "请确认 Chrome 已正确安装，或修改 CHROME_EXE 常量指向你的 Chrome 路径"
        )

    # 2) 启动 undetected_chromedriver
    # 注意：v5 验证发现要保留 --window-size 让控制条 hover 后能正常出现
    emit("正在启动 Chrome（首次较慢，需 5-15 秒）...")
    options = uc.ChromeOptions()
    options.add_argument(f"--user-data-dir={profile_dir}")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1280,800")
    options.binary_location = CHROME_EXE

    # 启用网络日志（Network 拦截用）
    options.set_capability("goog:loggingPrefs", {"performance": "ALL"})

    driver = None
    try:
        try:
            driver = uc.Chrome(
                options=options,
                browser_executable_path=CHROME_EXE,
                version_main=SELENIUM_CHROME_VERSION,
                driver_executable_path=CHROMEDRIVER_EXE,
            )
        except Exception as e:
            raise RuntimeError(
                f"启动 Chrome 失败：{e}\n\n"
                "可能原因：\n"
                f"  1. Chrome 不存在或路径不对：{CHROME_EXE}\n"
                f"  2. chromedriver 版本不匹配（需要 {SELENIUM_CHROME_VERSION}）\n"
                "  3. 本机 Chrome 正在运行（先关掉再试）"
            ) from e

        emit("Chrome 启动成功 ✓")

        # 3) 注入 cookies（v5 验证：先开主页再注入，比打开视频再注入更稳）
        cached_cookies = load_cookies_from_cache()
        if cached_cookies and is_cookies_valid(cached_cookies):
            emit(f"从缓存注入 {len(cached_cookies)} 个 cookies ...")
            try:
                driver.get("https://www.bilibili.com")
                time.sleep(2)
                for name, value in cached_cookies.items():
                    try:
                        driver.add_cookie({
                            "name": name,
                            "value": value,
                            "domain": ".bilibili.com",
                            "path": "/",
                        })
                    except Exception:
                        pass
                emit("SESSDATA 注入完成 ✓")
            except Exception as e:
                emit(f"注入 cookies 失败（继续尝试视频页登录态）: {e}")

        # 4) 打开视频页
        url = f"https://www.bilibili.com/video/{bvid}/"
        emit(f"打开视频页面: {url}")
        driver.get(url)
        time.sleep(8)  # v5 实测：8 秒比较稳妥

        # 4.5) 确认登录态：没有就引导扫码
        cookies = driver.get_cookies()
        sessdata_cookie = next(
            (c for c in cookies if c.get("name") == "SESSDATA"), None
        )
        if not sessdata_cookie:
            emit("未检测到 SESSDATA，请在弹出窗口里扫码登录...")
            driver.get("https://passport.bilibili.com/login")
            emit(f"等待扫码登录（{SELENIUM_LOGIN_TIMEOUT} 秒超时）...")
            try:
                WebDriverWait(driver, SELENIUM_LOGIN_TIMEOUT).until(
                    lambda d: (
                        "www.bilibili.com" in (d.current_url or "")
                        and "passport" not in (d.current_url or "")
                    )
                )
            except Exception as e:
                raise RuntimeError(
                    f"登录超时（{SELENIUM_LOGIN_TIMEOUT} 秒内未检测到登录成功），请重新尝试"
                ) from e

            time.sleep(2)
            cookies = driver.get_cookies()
            if not any(c.get("name") == "SESSDATA" for c in cookies):
                raise RuntimeError(
                    "登录成功后仍未检测到 SESSDATA cookie，"
                    "可能 B 站登录接口已变更，请反馈给开发者"
                )
            emit("登录成功 ✓")
            # 登录后刷新视频页
            driver.get(url)
            time.sleep(5)

        # cookies 转 dict（供后续 requests 下载 JSON 用）
        cookies_dict = {
            c["name"]: c["value"]
            for c in cookies
            if c.get("name") and c.get("value")
        }

        # 5) 主动播放视频（v5 验证：必须主动 play()，否则 hover 触发不出控制条）
        emit("视频播放中...")
        try:
            video = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "video"))
            )
            driver.execute_script(
                "arguments[0].muted = true; arguments[0].play();", video
            )
            time.sleep(2)
            emit("✓ 视频已播放")
        except Exception as e:
            emit(f"视频播放失败（继续尝试）: {e}")
            video = None

        # 6) **hover 视频**（关键洞察：控制条要 hover 才会出现）
        emit("鼠标悬停视频，让控制条显示...")
        actions = ActionChains(driver)
        hover_ok = False
        if video is not None:
            try:
                actions.move_to_element(video).perform()
                time.sleep(2)
                hover_ok = True
                emit("✓ 鼠标 hover 到 video 元素")
            except Exception as e:
                emit(f"hover video 失败: {e}")
        # 二次 hover 到播放器容器（更稳）
        try:
            player = driver.find_element(
                By.CSS_SELECTOR, "#bilibili-player, .bpx-player-container"
            )
            actions.move_to_element(player).perform()
            time.sleep(1)
            emit("✓ 鼠标 hover 到播放器容器")
        except Exception as e:
            emit(f"hover 播放器容器失败: {e}")
        if not hover_ok:
            emit("警告：hover 未成功，字幕按钮可能不显示")

        # 7) **JS 强制 click 字幕按钮**（v5 验证：EC.element_to_be_clickable 经常失败，必须 JS click）
        emit("点击字幕按钮（JS 强制 click）...")
        btn_clicked = False
        click_result = driver.execute_script(
            """
            const sels = [
                '.bpx-player-ctrl-subtitle-result',
                '.bpx-player-ctrl-subtitle',
                '[class*="subtitle"][class*="result"]',
                '[class*="subtitle-result"]'
            ];
            for (const sel of sels) {
                const el = document.querySelector(sel);
                if (el) {
                    el.click();
                    return {
                        clicked: true,
                        sel: sel,
                        text: (el.textContent || '').trim()
                    };
                }
            }
            return { clicked: false };
            """
        )
        if click_result and click_result.get("clicked"):
            emit(
                f"✓ 字幕按钮 click 成功: {click_result.get('sel')} "
                f"(text='{click_result.get('text', '')[:20]}')"
            )
            btn_clicked = True
        else:
            # 兜底：滚动 + Selenium click
            try:
                btn = driver.find_element(
                    By.CSS_SELECTOR, ".bpx-player-ctrl-subtitle-result"
                )
                driver.execute_script("arguments[0].scrollIntoView();", btn)
                time.sleep(1)
                btn.click()
                emit("✓ 字幕按钮 Selenium click 成功（兜底）")
                btn_clicked = True
            except Exception as e:
                emit(f"✗ 字幕按钮 click 失败: {e}")
        time.sleep(2)

        if not btn_clicked:
            raise RuntimeError("找不到字幕按钮（视频可能没有字幕）")

        # 8) **JS 强制 click 中文选项**
        emit("选择中文 AI 字幕（JS 强制 click）...")
        zh_result = driver.execute_script(
            """
            const sels = ['[data-lan="ai-zh"]', '[data-lan="zh-CN"]', '[data-lan="zh-Hans"]'];
            for (const sel of sels) {
                const el = document.querySelector(sel);
                if (el) {
                    el.click();
                    return {
                        clicked: true,
                        sel: sel,
                        data_lan: el.getAttribute('data-lan'),
                        text: (el.textContent || '').trim()
                    };
                }
            }
            // 兜底：找含"中文"文本的
            const items = document.querySelectorAll(
                '.bpx-player-ctrl-subtitle-language-item, [class*="language-item"]'
            );
            for (const el of items) {
                if ((el.textContent || '').includes('中文')) {
                    el.click();
                    return {
                        clicked: true,
                        sel: 'fallback-text-match',
                        data_lan: el.getAttribute('data-lan'),
                        text: (el.textContent || '').trim()
                    };
                }
            }
            return { clicked: false };
            """
        )
        if not zh_result or not zh_result.get("clicked"):
            raise RuntimeError("找不到中文 AI 字幕选项")

        data_lan = zh_result.get("data_lan", "ai-zh")
        emit(f"✓ 已选 {data_lan}，等待 AI 字幕生成（30 秒）...")

        # 9) 等 AI 字幕生成（v5 验证：首次 10-30 秒，给 30 秒保险）
        time.sleep(30)

        # 10) Network 拦截 + 持续抓取（v5 验证：边等边抓 URL）
        emit("拦截 AI 字幕网络请求...")
        ai_urls = []
        hooked_json = None
        last_log_count = 0
        ai_scrape_ticks = 12  # 持续抓 12 个 5 秒 = 60 秒
        for tick in range(ai_scrape_ticks):
            try:
                logs = driver.get_log("performance")
                for log in logs[last_log_count:]:
                    msg = log.get("message", "")
                    if "bfs/ai_subtitle" in msg or "aisubtitle" in msg.lower():
                        m = re.search(
                            r'"url":"([^"]+aisubtitle[^"]+)"', msg
                        )
                        if m:
                            u = m.group(1).replace("\\/", "/")
                            if u not in ai_urls:
                                ai_urls.append(u)
                                emit(f"🎯 拦截到 AI 字幕 URL: {u[:120]}...")
                last_log_count = len(logs)
            except Exception as e:
                emit(f"读 performance log 失败: {e}")

            # 拖动进度条：每隔几次跳一次（v5 验证：有时 AI 字幕需要视频播放一段时间才生成）
            if video is not None and tick in (2, 4, 6, 8, 10):
                try:
                    dur = driver.execute_script(
                        "return arguments[0].duration", video
                    )
                    if dur and dur > 0:
                        target = min((tick * float(dur)) / 12, float(dur) - 0.5)
                        driver.execute_script(
                            f"arguments[0].currentTime = {target}", video
                        )
                        emit(f"⏩ [{tick * 5}s] 拖到 {target:.1f}s")
                except Exception:
                    pass

            time.sleep(5)

        # 11) 用 requests 带 cookie 下载 AI 字幕 JSON
        if ai_urls:
            emit(f"下载 AI 字幕 JSON（{len(ai_urls)} 个候选 URL）...")
            for u in ai_urls[:3]:
                try:
                    u_clean = u.replace("\\/", "/")
                    r = requests.get(
                        u_clean,
                        cookies=cookies_dict,
                        headers={
                            "Referer": "https://www.bilibili.com/",
                            "User-Agent": DEFAULT_HEADERS["User-Agent"],
                        },
                        timeout=REQUEST_TIMEOUT,
                    )
                    if r.status_code == 200:
                        data = r.json()
                        body = data.get("body") if isinstance(data, dict) else None
                        if isinstance(body, list) and len(body) > 0:
                            hooked_json = data
                            emit(f"✓ 拿到 {len(body)} 条 AI 字幕")
                            break
                        else:
                            emit(f"  URL 返回 body 为空: {u_clean[:80]}")
                    else:
                        emit(f"  HTTP {r.status_code}: {u_clean[:80]}")
                except Exception as e:
                    emit(f"  下载失败: {e}")

        # 12) 决定用哪个结果
        title = (
            driver.title.split("_")[0].strip()
            if driver.title
            else f"untitled_{bvid}"
        )

        if hooked_json and isinstance(hooked_json, dict):
            body = _parse_subtitle_payload(hooked_json)
            if body:
                emit(f"✓ Network 拦截成功，共 {len(body)} 条字幕")
                return title, body, "ai"

        # 12b) 兜底：从 window.__INITIAL_STATE__ 抓
        emit("尝试从 window.__INITIAL_STATE__ 提取字幕...")
        try:
            initial_state = driver.execute_script(
                "return window.__INITIAL_STATE__ || null"
            )
            if initial_state:
                t2, body2, method2 = _find_subtitle_in_state(initial_state)
                if body2:
                    emit(f"✓ __INITIAL_STATE__ 拿到 {len(body2)} 条字幕 (method={method2})")
                    return (t2 or title), body2, method2 or "ai"
        except Exception as e:
            emit(f"__INITIAL_STATE__ 提取失败: {e}")

        # 12c) 终极兜底：DOM 抓取（拖进度条）
        emit("AI 字幕未就绪，尝试 DOM 拖进度条抓取（前 60 秒）...")
        dom_body = _scrape_subtitle_from_dom(driver, max_seconds=60)
        if dom_body:
            return title, dom_body, "dom"

        raise RuntimeError(
            "Selenium 三种抓取方式均失败：\n"
            "  1. Network 拦截未抓到 ai_subtitle JSON\n"
            "  2. window.__INITIAL_STATE__ 无字幕数据\n"
            "  3. DOM 抓取为空（可能视频无字幕）"
        )

    finally:
        # 关闭浏览器（Selenium 每次都新建实例，不像 Playwright 可以复用）
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass


def _scrape_subtitle_from_dom(driver, max_seconds: int = 60) -> list:
    """
    Selenium DOM 抓取的兜底方案：拖动进度条，每秒抓一次字幕文本。
    - 仅对短视频（< 60s）有效，长视频太慢不实用
    - 用 seen set 去重
    - 返回标准 body 格式：[{"from": ..., "to": ..., "content": ...}, ...]
    """
    import time
    collected = []
    seen = set()

    try:
        video = driver.find_element(By.TAG_NAME, "video")
        duration = driver.execute_script("return arguments[0].duration", video) or max_seconds
        # 限制最大秒数（避免长视频卡死）
        duration = min(float(duration), float(max_seconds))

        for sec in range(int(duration) + 1):
            driver.execute_script(f"arguments[0].currentTime = {sec}", video)
            time.sleep(SELENIUM_DOM_SCRAPE_INTERVAL)
            try:
                subs = driver.find_elements(
                    By.CSS_SELECTOR, ".bili-subtitle-x-subtitle-panel-text"
                )
                for s in subs:
                    text = (s.text or "").strip()
                    if text and text not in seen:
                        seen.add(text)
                        collected.append({
                            "from": float(sec),
                            "to": float(sec + 1),
                            "content": text,
                        })
            except Exception:
                continue

        return collected
    except Exception:
        return []


# ============================================================================
# 6. GUI 部分（tkinter）
# ============================================================================

class SubtitleApp:
    """
    主窗口类。
    - 用 threading 把网络请求放到后台，主线程不卡顿
    - 用 result_queue + after() 把后台结果切回主线程更新 UI
    """

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("B 站字幕获取工具  -  作者: 爱芮")
        self.root.geometry("900x740")
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        # 跨线程通信队列
        self.result_queue = []

        # 自动登录异步标志（防止重复点击）
        self._login_in_progress = False

        # 当前登录状态（dict 或 None）
        self._current_cookies = None

        self._build_ui()
        self.root.after(100, self._poll_queue)

        # 启动时自动加载 cookies 缓存
        self._try_load_cached_cookies()

    # ---------- UI 布局 ----------
    def _build_ui(self):
        """构建界面元素。"""
        # 顶部标题
        tk.Label(
            self.root,
            text="B 站字幕获取工具",
            font=("Microsoft YaHei", 16, "bold"),
            fg="#FB7299",  # B 站粉
        ).pack(pady=(10, 5))

        # URL 输入区
        url_frame = tk.Frame(self.root)
        url_frame.pack(fill="x", padx=15, pady=5)

        tk.Label(url_frame, text="视频URL:", font=("Microsoft YaHei", 10)).pack(side="left")
        self.url_var = tk.StringVar()
        self.url_entry = tk.Entry(
            url_frame,
            textvariable=self.url_var,
            font=("Consolas", 10),
        )
        self.url_entry.pack(side="left", fill="x", expand=True, padx=5)
        self.url_entry.bind("<Return>", lambda e: self.on_fetch_click())

        self.fetch_btn = tk.Button(
            url_frame,
            text="获取字幕",
            font=("Microsoft YaHei", 10, "bold"),
            bg="#FB7299",
            fg="white",
            activebackground="#FF8FAB",
            activeforeground="white",
            relief="flat",
            padx=15,
            command=self.on_fetch_click,
        )
        self.fetch_btn.pack(side="left")

        # === 登录态（可选） - LabelFrame ===
        # 位置：URL 框下方，状态区上方
        login_frame = tk.LabelFrame(
            self.root,
            text="登录态（可选）",
            font=("Microsoft YaHei", 10),
            fg="#666",
        )
        login_frame.pack(fill="x", padx=15, pady=5)

        # 第一行：SESSDATA 输入框 + 「自动登录」按钮
        sess_row = tk.Frame(login_frame)
        sess_row.pack(fill="x", padx=5, pady=3)

        tk.Label(
            sess_row,
            text="SESSDATA:",
            font=("Microsoft YaHei", 9),
            width=10,
            anchor="w",
        ).pack(side="left")

        self.sess_var = tk.StringVar()
        self.sess_entry = tk.Entry(
            sess_row,
            textvariable=self.sess_var,
            show="*",  # 类似密码框，隐藏输入
            font=("Consolas", 9),
        )
        self.sess_entry.pack(side="left", fill="x", expand=True, padx=5)

        # 「自动登录 B 站」按钮（推荐入口）
        self.login_btn = tk.Button(
            sess_row,
            text="自动登录 B 站",
            font=("Microsoft YaHei", 9, "bold"),
            bg="#00A1D6",  # B 站蓝
            fg="white",
            activebackground="#33BDEF",
            activeforeground="white",
            relief="flat",
            padx=10,
            command=self.on_auto_login_click,
        )
        self.login_btn.pack(side="left", padx=(0, 5))

        # Playwright 未装时灰显
        if not PLAYWRIGHT_AVAILABLE:
            self.login_btn.configure(
                state="disabled",
                text="自动登录 B 站（未安装 playwright）",
                bg="#999",
            )

        # 第二行：登录状态指示
        status_row = tk.Frame(login_frame)
        status_row.pack(fill="x", padx=5, pady=(2, 3))

        tk.Label(
            status_row,
            text="登录状态:",
            font=("Microsoft YaHei", 9),
            width=10,
            anchor="w",
        ).pack(side="left")

        self.login_status_var = tk.StringVar(value="🔴 未登录")
        tk.Label(
            status_row,
            textvariable=self.login_status_var,
            font=("Microsoft YaHei", 9, "bold"),
            fg="#CC0000",
            anchor="w",
        ).pack(side="left", fill="x", expand=True)

        # 说明 Label
        tk.Label(
            login_frame,
            text="💡 推荐点「自动登录 B 站」按钮用 B 站 App 扫码（无需手动复制 cookie）；"
                 "不填也能用，但部分视频字幕会被锁定。",
            font=("Microsoft YaHei", 8),
            fg="#888",
            anchor="w",
            wraplength=850,
            justify="left",
        ).pack(fill="x", padx=5, pady=(0, 3))

        # === 抓取方式 LabelFrame（v3 新增：三种模式三选一） ===
        # 位置：登录态 LabelFrame 下方
        fetch_frame = tk.LabelFrame(
            self.root,
            text="抓取方式",
            font=("Microsoft YaHei", 10),
            fg="#666",
        )
        fetch_frame.pack(fill="x", padx=15, pady=(0, 5))

        # 抓取方式选项：
        #   - "api"        API 优先（默认）：先 API，失败不 fallback（避免不必要的浏览器启动）
        #   - "playwright" Playwright 优先：先 Playwright，失败 fallback 到 API
        #   - "selenium"   Selenium 优先：先 Selenium，失败 fallback 到 Playwright → API
        self.fetch_mode_var = tk.StringVar(value="api")

        radio_row1 = tk.Frame(fetch_frame)
        radio_row1.pack(fill="x", padx=5, pady=3)

        # 第一行：API 优先 + Playwright 优先
        self.api_radio = tk.Radiobutton(
            radio_row1,
            text="API 优先（默认，速度最快）",
            variable=self.fetch_mode_var,
            value="api",
            font=("Microsoft YaHei", 9),
            activebackground="#F0F0F0",
        )
        self.api_radio.pack(side="left", padx=(0, 15))

        self.playwright_radio = tk.Radiobutton(
            radio_row1,
            text="Playwright 优先（拿 AI 字幕）",
            variable=self.fetch_mode_var,
            value="playwright",
            font=("Microsoft YaHei", 9),
            fg="#0066CC",
            activebackground="#F0F0F0",
        )
        self.playwright_radio.pack(side="left", padx=(0, 15))

        # Playwright 不可用时灰显
        if not PLAYWRIGHT_AVAILABLE:
            self.playwright_radio.configure(
                state="disabled",
                text="Playwright 优先（未安装 playwright 库）",
                fg="#999",
            )

        # 第二行：Selenium 优先
        radio_row2 = tk.Frame(fetch_frame)
        radio_row2.pack(fill="x", padx=5, pady=(0, 3))

        self.selenium_radio = tk.Radiobutton(
            radio_row2,
            text="Selenium 优先（本机 Chrome 绕过反检测，Network 拦截 ai_subtitle）",
            variable=self.fetch_mode_var,
            value="selenium",
            font=("Microsoft YaHei", 9),
            fg="#00A1D6",
            activebackground="#F0F0F0",
        )
        self.selenium_radio.pack(side="left")

        # Selenium 不可用时灰显
        if not SELENIUM_AVAILABLE:
            self.selenium_radio.configure(
                state="disabled",
                text="Selenium 优先（未安装 selenium / undetected-chromedriver）",
                fg="#999",
            )

        # 说明 Label
        tk.Label(
            fetch_frame,
            text="💡 Selenium 模式首次需要在 Chrome 登录 B 站（启动会复制 User Data，5-15 秒）",
            font=("Microsoft YaHei", 8),
            fg="#888",
            anchor="w",
            wraplength=850,
            justify="left",
        ).pack(fill="x", padx=5, pady=(0, 3))

        # 兼容旧代码：保留 use_playwright_var 给 _worker 用
        # （_worker 通过 fetch_mode_var 推导 use_pw）
        self.use_playwright_var = tk.BooleanVar(value=False)

        # 状态区
        status_frame = tk.LabelFrame(self.root, text="状态", font=("Microsoft YaHei", 10))
        status_frame.pack(fill="x", padx=15, pady=5)

        self.status_var = tk.StringVar(value="等待输入URL...")
        tk.Label(status_frame, textvariable=self.status_var, anchor="w",
                 font=("Microsoft YaHei", 9)).pack(fill="x", padx=5, pady=2)

        self.title_var = tk.StringVar(value="视频标题: ")
        tk.Label(status_frame, textvariable=self.title_var, anchor="w",
                 font=("Microsoft YaHei", 9), fg="#0066CC").pack(fill="x", padx=5, pady=2)

        self.count_var = tk.StringVar(value="字幕条数: ")
        tk.Label(status_frame, textvariable=self.count_var, anchor="w",
                 font=("Microsoft YaHei", 9), fg="#0066CC").pack(fill="x", padx=5, pady=2)

        # 字幕内容区
        text_frame = tk.LabelFrame(self.root, text="字幕内容", font=("Microsoft YaHei", 10))
        text_frame.pack(fill="both", expand=True, padx=15, pady=5)

        self.text_widget = scrolledtext.ScrolledText(
            text_frame,
            wrap="word",
            font=("Consolas", 10),
            bg="#FAFAFA",
        )
        self.text_widget.pack(fill="both", expand=True, padx=5, pady=5)
        self.text_widget.configure(state="disabled")

        # 底部按钮
        bottom_frame = tk.Frame(self.root)
        bottom_frame.pack(fill="x", padx=15, pady=(0, 10))

        tk.Button(
            bottom_frame,
            text="打开保存目录",
            font=("Microsoft YaHei", 9),
            command=self.on_open_dir_click,
        ).pack(side="left")

        tk.Label(
            bottom_frame,
            text="作者: 爱芮  ✨",
            font=("Microsoft YaHei", 9, "italic"),
            fg="#888",
        ).pack(side="right")

    # ---------- 事件回调 ----------
    def on_fetch_click(self):
        """点击「获取字幕」按钮：启动后台线程。"""
        url = self.url_var.get().strip()
        if not url:
            messagebox.showwarning("提示", "请先输入 B 站视频 URL 或 BV 号")
            return

        bvid = extract_bvid(url)
        if not bvid:
            messagebox.showerror(
                "错误",
                "无法从输入中识别到 BV 号\n\n示例：\n  https://www.bilibili.com/video/BV1xxxxxx\n  BV1xxxxxx"
            )
            return

        # 锁住按钮
        self.fetch_btn.configure(state="disabled", text="获取中...")
        self.status_var.set(f"正在获取 {bvid} ...")
        self.title_var.set("视频标题: ")
        self.count_var.set("字幕条数: ")
        self._set_text("")

        # 启动后台线程
        threading.Thread(target=self._worker, args=(bvid,), daemon=True).start()

    def on_auto_login_click(self):
        """
        点击「自动登录 B 站」按钮：
            1) 锁住按钮
            2) 启动后台线程
            3) 调 bili_login_with_playwright
            4) 成功 → 保存到 cookies 缓存，自动填入 SESSDATA
        """
        if self._login_in_progress:
            return

        if not PLAYWRIGHT_AVAILABLE:
            messagebox.showerror(
                "Playwright 未安装",
                "自动登录需要 Playwright，请运行：\n\n"
                "  pip install playwright\n"
                "  playwright install chromium"
            )
            return

        if not messagebox.askyesno(
            "即将打开浏览器",
            "点击「是」后会自动打开浏览器并跳转到 B 站登录页。\n\n"
            "请在浏览器中用 B 站 App 扫码登录（120 秒超时）。\n\n"
            "登录成功后 cookies 会自动保存，下次使用无需重新登录。\n\n"
            "现在打开浏览器？"
        ):
            return

        self._login_in_progress = True
        self.login_btn.configure(state="disabled", text="登录中...")
        self.login_status_var.set("🟡 正在登录 ...")
        self.status_var.set("正在打开浏览器，请在 B 站 App 扫码登录 ...")

        threading.Thread(target=self._login_worker, daemon=True).start()

    def _login_worker(self):
        """后台线程：实际执行 Playwright 扫码登录流程。"""
        def pw_status(msg: str):
            self.result_queue.append(("login_status_msg", msg))

        try:
            cookies = bili_login_with_playwright(status_callback=pw_status, headless=False)
            if cookies and cookies.get("SESSDATA"):
                # 成功：保存 + 自动填入 SESSDATA
                save_cookies_to_cache(cookies)
                self._current_cookies = cookies
                self.result_queue.append(("login_done", cookies))
            else:
                self.result_queue.append(("login_error", "登录流程未拿到 cookies，请重试"))
        except ImportError as e:
            self.result_queue.append(("login_error", str(e)))
        except Exception as e:
            self.result_queue.append(("login_error", f"登录失败：{type(e).__name__}: {e}"))
        finally:
            self.result_queue.append(("login_finish", None))

    def _try_load_cached_cookies(self):
        """
        启动时调用：尝试从 bili_cookies.json 读 cookies。
        - 有 → 自动填入 SESSDATA 输入框
        - 无 → 状态显示"未登录"
        """
        cookies = load_cookies_from_cache()
        if is_cookies_valid(cookies):
            self._current_cookies = cookies
            sess = cookies.get("SESSDATA", "")
            # 自动填入 SESSDATA（但不显示原值，因为是密码字段）
            self.sess_var.set(sess)
            self._update_login_status(cookies, saved_msg="已从本地缓存自动填入")
        else:
            self._update_login_status(None)

    def _update_login_status(self, cookies: dict = None, saved_msg: str = ""):
        """
        根据 cookies 状态更新 GUI 上的登录状态指示。
        - cookies 为 None → 🔴 未登录
        - cookies 有效 → 🟢 已登录（自动填入 SESSDATA）
        - 显示保存时间提示
        """
        if not is_cookies_valid(cookies):
            self.login_status_var.set("🔴 未登录")
            return

        # 计算 cookie 剩余天数（基于保存时间）
        extra = saved_msg or "已自动填入 SESSDATA 输入框"
        self.login_status_var.set(f"🟢 已登录（{extra}）")

        # 如果有保存时间，显示在 SESSDATA 框下方
        try:
            if os.path.isfile(COOKIES_CACHE_FILE):
                with open(COOKIES_CACHE_FILE, "r", encoding="utf-8") as f:
                    payload = json.load(f)
                saved_at = payload.get("saved_at", "")
                if saved_at:
                    self.status_var.set(f"上次登录保存时间: {saved_at}")
        except Exception:
            pass

    def on_open_dir_click(self):
        """打开 subtitles 保存目录（用 Windows 资源管理器）。"""
        os.makedirs(SUBTITLE_DIR, exist_ok=True)
        try:
            subprocess.Popen(['explorer', SUBTITLE_DIR])
        except Exception as e:
            messagebox.showerror("错误", f"无法打开目录：\n{SUBTITLE_DIR}\n\n{e}")

    def on_close(self):
        """关闭窗口。"""
        self.root.destroy()

    # ---------- 后台工作线程 ----------
    def _worker(self, bvid: str):
        """
        在子线程中执行（v3 重构：支持三种抓取方式优先级）：
            抓取方式 = "api":
                1) 直接调 API + SESSDATA
            抓取方式 = "playwright":
                1) 先 Playwright → 失败 fallback API + SESSDATA
            抓取方式 = "selenium":
                1) 先 Selenium → 失败 fallback Playwright → 还失败 fallback API + SESSDATA
        """
        # 读取抓取方式
        try:
            fetch_mode = (self.fetch_mode_var.get() or "api").lower()
        except Exception:
            fetch_mode = "api"

        # 读取 SESSDATA
        sess_raw = self.sess_var.get().strip()
        # 优先用 GUI 里的 SESSDATA；GUI 为空但有缓存 → 用缓存里的全部 cookies
        if sess_raw:
            cookies = {"SESSDATA": sess_raw}
        elif self._current_cookies:
            cookies = dict(self._current_cookies)
            sess_raw = cookies.get("SESSDATA", "")
        else:
            cookies = None
            sess_raw = ""

        # 计算本次是否需要尝试 Playwright（playwright 或 selenium 模式都需要）
        use_pw = fetch_mode in ("playwright", "selenium")
        # 计算本次是否需要尝试 Selenium
        use_selenium = fetch_mode == "selenium"

        # ============ 第一优先：Selenium（仅 selenium 模式）============
        if use_selenium:
            if not SELENIUM_AVAILABLE:
                self.result_queue.append((
                    "status",
                    "未安装 selenium / undetected-chromedriver，跳过 Selenium → fallback Playwright"
                ))
            else:
                def se_status(msg: str):
                    self.result_queue.append(("status", msg))

                try:
                    title, body, method = fetch_subtitle_via_selenium(
                        bvid, status_callback=se_status
                    )

                    if body:
                        # Selenium 成功：直接保存
                        if not title:
                            title = f"untitled_{bvid}"
                        self.result_queue.append(("title", title))
                        method_label = {
                            "ai": "AI 字幕",
                            "dom": "DOM 抓取字幕",
                            "cc": "CC 字幕",
                        }.get(method, "字幕")
                        self.result_queue.append((
                            "status",
                            f"Selenium 拿到{method_label} ({len(body)} 条)"
                        ))
                        self.result_queue.append(("count", len(body)))

                        text = format_subtitle_text(body)
                        self.result_queue.append(("text", text))

                        file_path = save_subtitle_to_file(text, title)
                        self.result_queue.append(("done", file_path))
                        self.result_queue.append(("enable_btn", None))
                        return

                    self.result_queue.append((
                        "status",
                        "Selenium 未拿到字幕，尝试 fallback 到 Playwright ..."
                    ))
                except ImportError as e:
                    self.result_queue.append(("status", f"Selenium 跳过: {e}"))
                except Exception as e:
                    self.result_queue.append((
                        "status",
                        f"Selenium 失败 ({type(e).__name__}: {e})，fallback 到 Playwright ..."
                    ))

        # ============ 第二优先：Playwright（playwright 或 selenium 模式）============
        if use_pw:
            if not PLAYWRIGHT_AVAILABLE:
                self.result_queue.append((
                    "status",
                    "未安装 Playwright，跳过 → fallback 到 API"
                ))
            else:
                def pw_status(msg: str):
                    self.result_queue.append(("status", msg))

                try:
                    title, body, method = fetch_subtitle_via_playwright(
                        bvid, status_callback=pw_status
                    )

                    if not body:
                        self.result_queue.append((
                            "status",
                            "Playwright 未拿到字幕，尝试 fallback 到 API + SESSDATA ..."
                        ))
                    else:
                        # 成功路径：直接保存
                        if not title:
                            title = f"untitled_{bvid}"
                        self.result_queue.append(("title", title))
                        method_label = "AI 字幕" if method == "ai" else "CC 字幕"
                        self.result_queue.append((
                            "status",
                            f"Playwright 拿到{method_label} ({len(body)} 条)"
                        ))
                        self.result_queue.append(("count", len(body)))

                        text = format_subtitle_text(body)
                        self.result_queue.append(("text", text))

                        file_path = save_subtitle_to_file(text, title)
                        self.result_queue.append(("done", file_path))
                        self.result_queue.append(("enable_btn", None))
                        return  # 拿到字幕就退出，不再走 API

                except ImportError as e:
                    self.result_queue.append(("status", f"Playwright 跳过: {e}"))
                except Exception as e:
                    self.result_queue.append((
                        "status",
                        f"Playwright 失败 ({type(e).__name__})，fallback 到 API 方案 ..."
                    ))

        # ============ 第三优先：API + SESSDATA ============
        try:
            self.result_queue.append(("status", f"正在请求视频元信息 {bvid} ..."))
            info = fetch_video_info(bvid, cookies=cookies)
            self.result_queue.append(("title", info["title"]))
            self.result_queue.append(("status", f"获取到标题: {info['title']}"))

            subtitle_list = info["subtitle_list"]
            if not subtitle_list:
                # 提示用户可能是 SESSDATA 过期
                msg = "该视频没有可用的字幕"
                if not sess_raw:
                    msg += ("\n\n可能原因：\n"
                            "  1. 视频本身没有 CC 字幕也没有 AI 字幕\n"
                            "  2. 字幕被 B 站锁定（需要登录）\n"
                            "  3. 建议点「自动登录 B 站」按钮登录后重试")
                else:
                    msg += ("\n\n可能原因：\n"
                            "  1. 视频本身没有字幕\n"
                            "  2. SESSDATA 可能已过期，请点「自动登录 B 站」按钮重新登录")
                self.result_queue.append(("error", msg))
                return

            # 选字幕
            target = self._pick_best_subtitle(subtitle_list)

            # 检查选中的字幕是否有可用的 url
            # 情况 1: target 为空（理论上前面已经拦了，但保险起见再查一次）
            # 情况 2: url 是空字符串（B 站对未登录用户隐藏字幕 url）
            target_url = (target or {}).get("subtitle_url") or (target or {}).get("subtitleUrl") or ""
            if not target or not target_url:
                lan_label = (target or {}).get("lan_doc", (target or {}).get("lan", "未知语言"))
                if not sess_raw:
                    msg = (
                        f"该视频有字幕列表（{lan_label}），但字幕被 B 站锁定（需要登录）。\n\n"
                        "解决方法：\n"
                        "  1. 点「自动登录 B 站」按钮，用 B 站 App 扫码登录（最推荐）\n"
                        "  2. 或者在「SESSDATA」处粘贴 SESSDATA 后重试"
                    )
                else:
                    msg = (
                        f"该视频有字幕列表（{lan_label}），但 subtitle_url 为空。\n\n"
                        "可能原因：SESSDATA 已过期。\n"
                        "  → 点「自动登录 B 站」按钮重新登录后重试"
                    )
                self.result_queue.append(("error", msg))
                return

            lan_label = target.get('lan_doc', target.get('lan', ''))
            self.result_queue.append(("status", f"选中字幕: {lan_label}"))

            # 拉字幕 JSON
            self.result_queue.append(("status", "正在拉取字幕内容..."))
            body = fetch_subtitle_json(target_url, cookies=cookies)

            if not body:
                self.result_queue.append((
                    "error",
                    "字幕内容为空\n\n"
                    "可能 SESSDATA 已过期，请点「自动登录 B 站」按钮重新登录"
                ))
                return

            # 格式化 + 保存
            self.result_queue.append(("count", len(body)))
            text = format_subtitle_text(body)
            self.result_queue.append(("text", text))

            file_path = save_subtitle_to_file(text, info["title"])
            self.result_queue.append(("done", file_path))

        except requests.exceptions.Timeout:
            self.result_queue.append(("error", "网络请求超时，请检查网络后重试"))
        except requests.exceptions.ConnectionError:
            self.result_queue.append(("error", "网络连接失败，请检查网络"))
        except requests.exceptions.HTTPError as e:
            self.result_queue.append(("error", f"HTTP 错误: {e.response.status_code} {e.response.reason}"))
        except json.JSONDecodeError:
            self.result_queue.append(("error", "B 站返回的数据不是合法 JSON，可能接口被风控"))
        except RuntimeError as e:
            err_msg = str(e)
            # SESSDATA 过期的典型特征：API 返回 code=-101（未登录）/-352（风控）
            if "code=-101" in err_msg or "code=-352" in err_msg:
                err_msg += "\n\nSESSDATA 可能已过期，请点「自动登录 B 站」按钮重新登录"
            self.result_queue.append(("error", err_msg))
        except Exception as e:
            self.result_queue.append(("error", f"未预期错误: {type(e).__name__}: {e}"))
        finally:
            self.result_queue.append(("enable_btn", None))

    def _pick_best_subtitle(self, subtitle_list: list) -> dict:
        """
        从字幕列表中挑一条。
        优先级（先按 url 可用，再按语言）：
            1. subtitle_url 非空  ← 关键：B 站对未登录用户 url 是空的，必须优先跳过
            2. 中文(zh-CN/zh-Hans/zh) > 含 zh > 英文 > 第一条
        返回：选中的字幕 dict；如果整个列表为空则返回 None
        """
        if not subtitle_list:
            return None

        def priority(item):
            # url 为空的字幕优先级降到最低
            url = item.get("subtitle_url") or item.get("subtitleUrl") or ""
            if not url:
                return 99
            lan = (item.get("lan") or "").lower()
            if lan in ("zh-cn", "zh-hans", "zh", "zh-tw", "zh-hant"):
                return 0
            if "zh" in lan:
                return 1
            if lan.startswith("en"):
                return 2
            return 3

        # 先过滤掉没 url 的，但保留至少一个 fallback（万一所有 url 都空也能选到一条）
        valid = [s for s in subtitle_list if s.get("subtitle_url") or s.get("subtitleUrl")]
        candidates = valid if valid else subtitle_list
        sorted_list = sorted(candidates, key=priority)
        return sorted_list[0] if sorted_list else None

    # ---------- 主线程轮询 ----------
    def _poll_queue(self):
        """
        主线程每 100ms 检查一次队列。
        取出所有结果并更新 UI。
        """
        while self.result_queue:
            event, payload = self.result_queue.pop(0)
            if event == "status":
                self.status_var.set(payload)
            elif event == "title":
                self.title_var.set(f"视频标题: {payload}")
            elif event == "count":
                self.count_var.set(f"字幕条数: {payload}")
            elif event == "text":
                self._set_text(payload)
            elif event == "done":
                self.status_var.set(f"已完成 ✓  已保存到: {payload}")
            elif event == "error":
                self.status_var.set(f"[错误] {payload}")
                self._set_text(f"[错误]\n{payload}\n")
                messagebox.showerror("错误", payload)
            elif event == "enable_btn":
                self.fetch_btn.configure(state="normal", text="获取字幕")
            elif event == "login_status_msg":
                # 登录过程中的实时状态
                self.status_var.set(payload)
            elif event == "login_done":
                # 登录成功
                cookies = payload or {}
                self._current_cookies = cookies
                # 自动填入 SESSDATA
                sess = cookies.get("SESSDATA", "")
                if sess:
                    self.sess_var.set(sess)
                self._update_login_status(cookies, saved_msg="已自动填入 SESSDATA 输入框")
                self.login_status_var.set("🟢 已登录")
                self.status_var.set("✓ 登录成功，cookies 已保存到本地")
                messagebox.showinfo("登录成功", "B 站登录成功！\n\ncookies 已保存到本地，下次使用无需重新登录。")
            elif event == "login_error":
                self.login_status_var.set("🔴 未登录")
                self.status_var.set(f"登录失败: {payload}")
                messagebox.showerror("登录失败", payload)
            elif event == "login_finish":
                # 登录流程结束（无论成功失败），恢复按钮
                self._login_in_progress = False
                if PLAYWRIGHT_AVAILABLE:
                    self.login_btn.configure(state="normal", text="自动登录 B 站")
                else:
                    self.login_btn.configure(
                        state="disabled",
                        text="自动登录 B 站（未安装 playwright）",
                    )

        # 继续轮询
        self.root.after(100, self._poll_queue)

    def _set_text(self, content: str):
        """写入字幕文本（解开 disabled 状态）。"""
        self.text_widget.configure(state="normal")
        self.text_widget.delete("1.0", "end")
        self.text_widget.insert("1.0", content)
        self.text_widget.configure(state="disabled")


# ============================================================================
# 6. 入口
# ============================================================================

def main():
    """程序入口。"""
    # Windows 高 DPI 适配
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    root = tk.Tk()
    SubtitleApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
