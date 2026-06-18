---
name: bilibili-subtitle-tool
description: B 站视频字幕获取工具的完整经验沉淀。包含 v1-v6 演进路径、最优 Selenium hover+click 方案、关键代码模板、坑 1-18 完整列表。用于快速复现或扩展此工具。
metadata:
  type: project-skill
  category: media-tool
  author: AI 助手
  date: 2026-06-18
  project: 项目根目录
  status: working
  best_version: v6 (12.7 秒拿 3 分钟视频 80 条字幕)
---

# B 站字幕工具 Skill

> 从 lxfater/BilibiliSummary 调研开始，到 v6 速度优化版达成 **12.7 秒** 拿全 3 分钟视频字幕的完整经验。

---

## 一、什么时候用这个 skill

**触发条件**（满足任一即用）：
- 需要获取 B 站视频的字幕（包括 AI 字幕）
- 用户说"字幕没成功过"、"抓取 B 站字幕"、"B 站视频文字稿"
- 需要把 B 站视频内容转成可搜索的文本
- 之前用 B 站字幕工具"从来没成功过"

**不适用**：
- 其他平台（YouTube、TikTok 等）—— 需要单独的 skill
- 仅需要视频元数据（标题、UP 主等）—— 用 B 站 API 即可
- 弹幕抓取（用 B 站弹幕 API，不在这个 skill 范围）

---

## 二、完整工作流程（v6 优化版，最优方案）

### 2.1 流程图

```
启动 undetected Chrome（用户本机 <你的Chrome路径>/chrome.exe）
    ↓
注入 SESSDATA（从 bili_cookies.json 读，~3 秒）
    ↓
打开视频 URL（driver.get，等 3 秒）
    ↓
主动 video.play()（必须，否则控制条不显示）
    ↓
【关键】hover 视频（让控制条显示，~2 秒）
    ↓
JS click 字幕按钮（.bpx-player-ctrl-subtitle-result）
    ↓
JS click 中文选项（[data-lan="ai-zh"]）
    ↓
【关键】轮询 Network 1s/次（不等固定时间）
    ↓
拦截到 bfs/ai_subtitle/prod URL
    ↓
requests.get 下载 JSON（带 cookies + Referer）
    ↓
保存为标准 TXT 格式
```

### 2.2 时间预算（v6 实测）

| 步骤 | 耗时 |
|---|---|
| 启动 Chrome | 0.9s |
| 注入 cookies | 2.9s |
| 打开视频 | 4.4s |
| play + hover + click | 3.1s |
| **等 AI 字幕** | **0.2-30s** |
| 下载 + 保存 | 0.2s |
| **总计** | **12.7s**（缓存命中）/ ~45s（首次生成） |

**关键**：AI 字幕生成时间不可控（B 站服务器），但**轮询**比**固定等**快很多。

---

## 三、关键代码（最简可工作版）

### 3.1 核心函数

```python
import sys, io, time, json, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
import requests
from datetime import timedelta

CHROME_EXE = r'<你的Chrome路径>/chrome.exe'
CHROMEDRIVER = r'<你的ChromeDriver路径>/chromedriver.exe'

def fetch_bilibili_subtitle_v6(bvid: str) -> list | None:
    """返回字幕 body 列表 [{from, to, content}, ...]"""
    T0 = time.time()
    def t(): return f'[{time.time()-T0:5.1f}s]'

    # 读 SESSDATA
    with open('项目根目录/bili_cookies.json', 'r', encoding='utf-8') as f:
        cookies_dict = json.load(f)['cookies']

    # 1. 启动 Chrome
    print(f'{t()} 启动 Chrome')
    options = uc.ChromeOptions()
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_argument('--no-sandbox')
    options.add_argument('--window-size=1280,800')
    options.binary_location = CHROME_EXE
    caps = options.to_capabilities()
    caps['goog:loggingPrefs'] = {'performance': 'ALL'}
    options.set_capability('goog:loggingPrefs', {'performance': 'ALL'})

    driver = uc.Chrome(
        options=options,
        browser_executable_path=CHROME_EXE,
        version_main=120,
        driver_executable_path=CHROMEDRIVER,
    )

    try:
        # 2. 注入 cookies
        driver.get('https://www.bilibili.com')
        time.sleep(1)
        for name, value in cookies_dict.items():
            try:
                driver.add_cookie({'name': name, 'value': value, 'domain': '.bilibili.com', 'path': '/'})
            except Exception:
                pass

        # 3. 打开视频
        print(f'{t()} 打开视频 {bvid}')
        driver.get(f'https://www.bilibili.com/video/{bvid}/')
        time.sleep(3)

        # 4. 主动播放
        video = WebDriverWait(driver, 8).until(
            lambda d: d.find_element(By.TAG_NAME, 'video')
        )
        driver.execute_script("arguments[0].muted = true; arguments[0].play();", video)
        time.sleep(1)

        # 5. 【关键】hover 视频
        print(f'{t()} hover 视频')
        actions = ActionChains(driver)
        actions.move_to_element(video).perform()
        time.sleep(1)
        try:
            player = driver.find_element(By.CSS_SELECTOR, '#bilibili-player, .bpx-player-container')
            actions.move_to_element(player).perform()
            time.sleep(0.5)
        except:
            pass

        # 6. JS click 字幕按钮
        print(f'{t()} click 字幕按钮')
        driver.execute_script("""
            const el = document.querySelector('.bpx-player-ctrl-subtitle-result');
            if (el) el.click();
        """)
        time.sleep(1)

        # 7. JS click 中文
        print(f'{t()} click 中文')
        driver.execute_script("""
            const sels = ['[data-lan="ai-zh"]', '[data-lan="zh-CN"]', '[data-lan="zh-Hans"]'];
            for (const sel of sels) {
                const el = document.querySelector(sel);
                if (el) { el.click(); break; }
            }
        """)

        # 8. 【关键】轮询 Network 1s/次（最多 40s）
        print(f'{t()} 轮询 Network')
        ai_urls = []
        max_wait = 40
        start = time.time()
        while time.time() - start < max_wait:
            try:
                logs = driver.get_log('performance')
                for log in logs:
                    msg = log.get('message', '')
                    if 'bfs/ai_subtitle' in msg or 'aisubtitle' in msg.lower():
                        m = re.search(r'"url":"([^"]+aisubtitle[^"]+)"', msg)
                        if m:
                            u = m.group(1).replace('\\/', '/')
                            if u not in ai_urls:
                                ai_urls.append(u)
                                print(f'{t()}   拦截到: {u[:80]}')
            except:
                pass
            if ai_urls:
                break
            time.sleep(1)

        if not ai_urls:
            return None

        # 9. 下载 JSON
        for u in ai_urls[:3]:
            try:
                r = requests.get(
                    u,
                    cookies=cookies_dict,
                    headers={'Referer': 'https://www.bilibili.com/', 'User-Agent': 'Mozilla/5.0'},
                    timeout=15,
                )
                if r.status_code == 200:
                    data = r.json()
                    body = data.get('body') if isinstance(data, dict) else None
                    if isinstance(body, list) and body:
                        return body
            except:
                pass

        return None
    finally:
        try:
            driver.quit()
        except:
            pass


def save_subtitle_txt(body: list, title: str) -> str:
    """保存为标准 SRT 风格 TXT"""
    def format_ts(s):
        td = timedelta(seconds=s)
        total = int(td.total_seconds())
        h = total // 3600
        m = (total % 3600) // 60
        sec = total % 60
        ms = int(round((s - int(s)) * 1000))
        if ms >= 1000: ms = 999
        return f'{h:02d}:{m:02d}:{sec:02d}.{ms:03d}'

    lines = []
    for item in body:
        start = item.get('from', 0.0)
        end = item.get('to', 0.0)
        content = (item.get('content') or '').strip()
        if not content: continue
        lines.append(f'{format_ts(start)} --> {format_ts(end)}: {content}')

    text = '\n'.join(lines)
    import os
    out_path = f'subtitles/{title}.txt'
    os.makedirs('subtitles', exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(text)
    return out_path
```

### 3.2 一次性运行

```python
body = fetch_bilibili_subtitle_v6('<示例视频BV号>')
if body:
    print(f'拿到 {len(body)} 条字幕')
    path = save_subtitle_txt(body, '心跳总是80多，你的心脏太累了')
    print(f'保存到 {path}')
```

---

## 四、踩坑清单（坑 1-18 完整版）

### 4.1 v1-v3 调研阶段（坑 1-12）

| 坑 | 现象 | 原因 | 解决 |
|---|---|---|---|
| **1. 视频没字幕** | 目标视频 <示例视频BV号> subtitle.list=[] | 视频本身没 UP 主字幕也没 AI 字幕 | 接受"正常情况" |
| **2. 字幕被锁** | `is_lock: true`, `subtitle_url=""` | B 站对未登录用户隐藏 | 必须 SESSDATA |
| **3. WebSearch 失败** | 工具返回 400 invalid params | 工具临时故障 | 用 exa 替代 |
| **4. 搜索 API 要签名** | B 站搜索 API 拿不到结果 | wbi 签名机制 | 用 exa 搜索外网 |
| **5. 热门榜 0 个公开字幕** | 100 个视频都拿不到 | B 站对未登录全面锁字幕 | 必须登录 |
| **6. 调研漏看 credentials** | 调研 lxfater 没看 `credentials: 'include'` | 没注意 Chrome 扩展自动带 cookie | 引入 SESSDATA 概念 |
| **7. SESSDATA 缺自动获取** | 用户不愿手动复制 | UX 差 | 实现自动扫码登录 |
| **8. Playwright 启动慢** | 每次 5-10s | 启动浏览器开销 | 改用 undetected_chromedriver |
| **9. 字幕 URL 为空崩溃** | `ValueError: subtitle_url 为空` | 没过滤空 URL | `_pick_best_subtitle` 加 url 校验 |
| **10. Playwright 被反检测** | "不支持 HTML5 播放器" | 模拟浏览器被识别 | 改用用户本机 Chrome |
| **11. Chrome User Data 锁** | Selenium 启动冲突 | 用户 Chrome 开着 | 复制 User Data 副本 |
| **12. chromedriver 版本** | 自动下载失败 | 用户本机 Chrome 版本特定 | 硬编码 version_main=120 |

### 4.2 v3-v5 实战阶段（坑 13-18）

| 坑 | 现象 | 原因 | 解决 |
|---|---|---|---|
| **13. AI 字幕"不存在"** | `ai_type=0` 误判 | AI 字幕需手动触发 | 必须点字幕按钮 |
| **14. video.play() 不够** | 60 秒等不到 AI 字幕 | play 只触发播放不触发字幕 | 必须点字幕按钮 |
| **15. performance 日志不全** | Network 拦截 0 | AI 字幕可能用 WebSocket | 用 driver.get_log('performance') |
| **16. DOM 抓的可能是弹幕** | 抓了 8 条"字幕" | 没触发时是别的内容 | 必须点字幕按钮 |
| **17. 字幕按钮不可见** | click 报 "Message: " 错 | 必须 hover 视频才显示 | **先 hover 再 click** |
| **18. Selenium click 失败** | 元素存在但 click 报 | 不可见元素 click 失败 | **用 JS 强制 click** |

### 4.3 核心洞察（v6 沉淀）

1. **AI 字幕必须手动触发**（点"字幕"→ 选"中文"）—— 不触发就完全没有
2. **必须先 hover 视频**（字幕按钮在 hover 状态才显示）
3. **必须用 JS 强制 click**（绕过可见性检测，比 Selenium click 稳）
4. **SESSDATA 是必须的**（B 站对未登录隐藏所有字幕 URL）
5. **Network 拦截**比 DOM 抓取更稳（拿到完整 JSON 带时间戳）
6. **轮询比固定等快**（B 站缓存命中时 0.2s 拿到）

---

## 五、完整演进历史（v1 → v6）

| 版本 | 方案 | 状态 | 关键发现 |
|---|---|---|---|
| **v1** | Selenium + 无 SESSDATA | ❌ 嘴炮成功 | B 站反检测；只找到按钮没拿数据 |
| **v2** | Selenium + 注 SESSDATA | ❌ 缺播放 | 视频停在首帧，按钮 click 失败 |
| **v3** | Selenium + 注 SESSDATA + 真播放 | ❌ 缺点击 | 拿到 8 条文本，但可能是弹幕 |
| **v4** | + JS click 字幕按钮 | ❌ 缺 hover | 字幕按钮不可见 |
| **v5** | + hover 视频 | ✅ **成功 29 条** | 完整流程打通 |
| **v6** | + 轮询 Network + 拖动进度条 | ✅ **12.7 秒 80 条** | 速度优化 |

**用户的 v3 → v5 关键洞察**：
> 「下次至少你要来点击」
> 「需要鼠标在视频上悬停，然后才会有按钮，然后点击按钮」

---

## 六、文件位置

### 6.1 主项目
- `项目根目录main.py`（2032 行，集成 v6 流程）
- `项目根目录bili_cookies.json`（SESSDATA 缓存）
- `项目根目录subtitles\`（字幕保存目录）

### 6.2 测试脚本（v1-v6 演进）
- `test_selenium.py`（v1：嘴炮）
- `test_selenium_v2.py`（v2：注 SESSDATA）
- `test_selenium_v3.py`（v3：真播放）
- `test_selenium_v4.py`（v4：点击但没 hover）
- `test_selenium_v5.py`（v5：完整流程成功）
- `test_selenium_v6_speed.py`（v6：12.7s 速度优化）

### 6.3 文档
- `使用手册.md`（用户使用文档）
- `经验总结.md`（v1-v3.5 经验）
- `踩坑与思路_v3_selenium.md`（v3 详细踩坑）
- `SKILL.md`（本文件，最新沉淀）

---

## 七、使用方法

### 7.1 在 main.py GUI 里用

```powershell
cd 项目根目录
python main.py
```

GUI 操作：
1. 抓取方式选「**Selenium 优先**」
2. **先关闭本机 Chrome**（避免 User Data 冲突）
3. 输入 B 站视频 URL
4. 点「**获取字幕**」

### 7.2 命令行直接用（v6 脚本）

```python
import sys
sys.path.insert(0, '项目根目录/')

# 导入 v6 函数
exec(open('test_selenium_v6_speed.py').read().split('T0 = time.time()')[0])

# 调用
body = fetch_bilibili_v6('<示例视频BV号>')
if body:
    save_subtitle_txt(body, '视频标题')
```

### 7.3 作为 subagent 任务

把上面的"关键代码"小节完整交给 subagent，让它在新项目里复用。

---

## 八、性能数据（v6 实测）

| 测试 | 视频时长 | 字幕条数 | 耗时 | 备注 |
|---|---|---|---|---|
| **v5** <示例视频BV号> | 54 秒 | 29 条 | ~30s | 首次生成 |
| **v6** <示例视频BV号> | 3 分钟 | 80 条 | **12.7s** | 缓存命中 |

**关键**：v6 用用户账户已登录态，B 站缓存了 AI 字幕能力，**12.7 秒**拿到 80 条。

---

## 九、依赖

```
requests>=2.28.0
selenium>=4.27.0
undetected-chromedriver>=3.5.0
playwright>=1.40.0  # 备选方案
```

**外部资源**：
- Chrome 路径：`<你的Chrome路径>/chrome.exe`（用户本机）
- chromedriver：`<你的ChromeDriver路径>/chromedriver.exe`
- Chrome User Data：`<你的Chrome User Data目录>`

---

## 十、未来优化方向

1. **复用 Chrome 实例**（不要每次都启停，节省 5-10s）
2. **多线程批量抓取**（多个视频并发）
3. **字幕翻译**（中文 → 英文）
4. **AI 总结**（把字幕丢给 LLM 做摘要）
5. **GUI 进度条优化**（v6 已实时显示每步进度）
6. **首次生成加速**（首次要 30s，可能要等 B 站 API 优化）

---

**踩坑日期**：2026-06-17 ~ 2026-06-18
**最终版本**：v6（12.7s 80 条）
**作者**：AI 助手（AI 助手）
**用户**：姜绅（B 站字幕工具需求的提出者）
