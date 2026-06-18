# B 站字幕获取工具 - 项目复盘

> 作者：AI 助手（写给未来的姜绅，或者任何接手这个项目的人）
> 项目目录：`项目根目录`
> 主程序：`main.py`（942 行，最终版）
> 完成时间：2026-06-17

---

## 一、项目背景与目标

姜绅（用户）想做一个 Python 工具：输入 B 站视频 URL，自动下载字幕到本地。

这个需求看起来简单——B 站有官方 API、有字幕接口、有大把开源项目可以参考。但**用户之前从来没成功过**。试过直接调 API、试过浏览器抓包、试过各种"现成脚本"，全部失败。

核心难点不是技术，是 **B 站对未登录用户的风控**。B 站的视频元数据接口（`/x/web-interface/view`）可以匿名访问，但**字幕 URL 会被锁**——`is_lock: true`，`subtitle_url` 字段为空。这是整个项目最关键的发现，也是后面所有方案演进的核心出发点。

---

## 二、调研过程

### 2.1 参考项目 lxfater/BilibiliSummary

GitHub 上找到一个 727 Star 的 Chrome 扩展：`lxfater/BilibiliSummary`（TypeScript 写的）。

这个项目的核心源码在 `src/inject/main-world.ts`，**它完全不用浏览器自动化**，只调两个 B 站 API：

```javascript
// 1. 拿视频元信息和字幕列表
fetch(`https://api.bilibili.com/x/web-interface/view?bvid=${videoId}`, {
    credentials: 'include'  // 关键：包含用户 cookie
})

// 2. 字幕 JSON 链接
result.data.subtitle.list[0].subtitle_url
```

字幕 JSON 格式：
```json
{
  "body": [
    {"from": 0.0, "to": 5.2, "content": "你好"},
    {"from": 5.2, "to": 10.5, "content": "世界"}
  ]
}
```

**关键发现**：`credentials: 'include'`。Chrome 扩展是在用户已经登录 B 站的浏览器环境里跑的，自动带 cookie。这是它能拿到字幕 URL 的原因。

### 2.2 B 站 API 调研

| 端点 | 用途 | 是否需要登录 |
|---|---|---|
| `/x/web-interface/view?bvid={BV}` | 视频元信息 + 字幕列表 | 匿名可访问，但字幕 URL 可能为空 |
| `{subtitle_url}` | 字幕 JSON 内容 | 需要登录态 |
| `/x/web-interface/search/type` | 搜索视频 | **需要 wbi 签名** |

### 2.3 关键技术决策

- **优先 API 而非浏览器自动化**：速度差几个数量级（API < 1s vs 浏览器 5-10s）
- **GUI 用 tkinter**：Python 自带，零依赖
- **网络请求放子线程**：避免阻塞 GUI

---

## 三、完整时间线

### 阶段 1：调研（30 分钟）

调用 GitHub API 拿到 `lxfater/BilibiliSummary` 的仓库元信息、文件列表。读 `main-world.ts` 源码，确认它只用两个 API 就能拿到字幕。

### 阶段 2：第一次实现（1 小时）

subagent 写出了 `main.py` 第一版（509 行），同时创建了：
- `main.py`：主程序
- `README.md`：英文说明
- `使用手册.md`：中文用户手册
- `requirements.txt`：`requests>=2.28.0`
- `subtitles/`：保存目录

### 阶段 3：测试踩坑（核心阶段）

具体坑的细节见第四章。

### 阶段 4：思路演进

发现"未登录拿不到字幕 URL"这个根本问题后，用户选了**方案 C（SESSDATA + Playwright 双方案）**：
- 不强制用户登录（保留纯 API 模式，能跑就跑）
- 提供 SESSDATA 输入框（轻量登录态）
- 提供 Playwright 持久化方案（自动化登录态）

### 阶段 5：第二次实现（1.5 小时）

subagent 改写 `main.py`，从 509 行扩到 **942 行**。新增：
- `fetch_subtitle_via_playwright(bvid, status_callback)`：用 Playwright 持久化 profile 启动 Chromium，从浏览器内部 fetch 拿字幕
- GUI 新增「登录态（可选）」LabelFrame 和「使用 Playwright」Checkbutton
- 三段式 worker：Playwright → API+SESSDATA → 错误提示

### 阶段 6：交付

写中文使用手册、英文 README、跑通 Playwright 流程（首次需要用户手动登录一次 B 站）。

---

## 四、踩过的坑（重点）

### 坑 1：目标视频本身没有字幕

**现象**：用 `<示例视频BV号>`（大疆 Pocket 4P）测试，API 返回 `data.subtitle.list` 长度为 0。

**原因**：视频既没有 UP 主上传字幕，也没有 AI 生成的字幕。**这是正常情况**，B 站很多新视频都没字幕。

**解决**：工具返回明确的"该视频无字幕"提示，而不是崩。

**未来怎么避免**：
- 在 GUI 上加一个"先检查是否有字幕"的预览按钮
- 在使用手册里加一节"如何判断视频是否有字幕"
- 考虑接入语音识别作为 fallback（但成本高、慢）

---

### 坑 2：B 站对未登录用户隐藏字幕 URL

**现象**：测试 `<示例视频BV号>`（Rick Astley MV），API 返回 12 条字幕，但每条的 `subtitle_url` 字段都是空，`is_lock: true`。

```json
{
  "id": 123456,
  "lan": "zh-CN",
  "lan_doc": "中文(简体)",
  "is_lock": true,           // 关键
  "subtitle_url": "",        // 空
  "type": 0,
  "ai_type": 0
}
```

测试 `<示例视频BV号>`（MIT 6.0001 Python）、`<示例视频BV号>`（SICP）都一样被锁。

**原因**：B 站对未登录用户隐藏字幕 URL。`lxfater/BilibiliSummary` 能拿到是因为 Chrome 扩展自动带用户登录 cookie。

**解决**：见第五章方案演进。

**未来怎么避免**：在工具里**默认提示用户需要登录态**，而不是让用户自己试到怀疑人生。

---

### 坑 3：WebSearch 工具失败

**现象**：想用 WebSearch 工具找带字幕的公开课视频，返回 `400 invalid params` 错误。

**原因**：WebSearch 工具那阵子有 bug 或者配额用完了。

**解决**：用 `exa` 的 `web_search_exa` 找视频。

**未来怎么避免**：
- 准备多个搜索 fallback：WebSearch → exa → 直接 curl Google
- 重要的搜索任务用 deep research skill

---

### 坑 4：B 站搜索 API 需要 wbi 签名

**现象**：直接 `curl` B 站搜索 API（`/x/web-interface/search/type` 或 `/search/all/v2`）拿不到结果。

**原因**：B 站的搜索接口加了 wbi 签名（类似 B 站版的"waf"），需要先拿一个密钥再签名。

**解决**：放弃用 B 站搜索 API，改用 exa 搜索外网。

**未来怎么避免**：
- 如果一定要用 B 站搜索 API，需要逆向 wbi 签名算法（参考 `SocialSisterYi/bilibili-API-collect`）
- 或者用 Selenium 启动真实浏览器调搜索

---

### 坑 5：热门榜 100 个视频 0 个有公开字幕

**现象**：手动测试 B 站热门榜前 100 个视频，**没有一个对未登录用户开放字幕**。

**原因**：B 站策略——**对未登录用户全面锁字幕**。这是设计上的风控，不是 bug。

**结论**：纯匿名方案不可行。**必须考虑登录态**。

**未来怎么避免**：调研阶段就应该测几个视频的字幕情况，5 分钟就能发现这个限制。

---

### 坑 6（反思）：一开始没考虑登录态

**现象**：第一次写代码时只考虑了 API 调用，没考虑"未登录拿不到字幕"。

**原因**：调研时只看了 `lxfater/BilibiliSummary` 的代码风格，**没有仔细看它 `credentials: 'include'` 这一行的含义**。

**反思**：调研开源项目时，**不能只看"它怎么调 API"，还要看"它在什么环境里调 API"**。Chrome 扩展 vs Python requests 是完全不同的环境。

**未来怎么避免**：
- 看代码时问自己："这个代码运行在什么环境？那个环境有什么特权？"
- 对所有"看起来能跑"的方案，先用一个真实数据点验证可行性

---

## 五、思路演进

```
V1: 纯 API 方案（失败）
   ├─ 调 /x/web-interface/view 拿字幕列表
   ├─ 拿 subtitle_url
   └─ 失败：subtitle_url 为空，未登录被锁

V2: 考虑登录态（用户选 C 方案）
   ├─ A 方案：GUI 加 SESSDATA 输入框
   ├─ B 方案：Playwright 持久化 profile
   └─ C 方案：A + B 都做（最终选择）

V3: 最终实现（main.py 942 行）
   ├─ 优先尝试 Playwright（如果用户勾选）
   ├─ Fallback 到 API + SESSDATA
   └─ 都失败：明确的错误提示
```

**演进的核心逻辑**：
1. **先做最简单的**（V1 纯 API），但被风控打脸
2. **承认现实**（B 站就是锁未登录），加登录态
3. **不强制**（V3 保留纯 API 模式，让用户自己选）

**为什么选 C 而不是只选 A 或 B**：
- A 方案最简单，但 SESSDATA 会过期，用户要时不时重新复制
- B 方案最自动化，但要装 Playwright + 首次手动登录
- C 方案是**A 和 B 的并集**——能用哪个用哪个，都用不了再报错

---

## 六、技术方案与设计决策

### 6.1 为什么优先 API 而非浏览器自动化

| 维度 | API | 浏览器自动化 |
|---|---|---|
| 速度 | < 1 秒 | 5-10 秒 |
| 资源占用 | 几乎为零 | 几百 MB 内存 |
| 稳定性 | B 站改风控就崩 | 浏览器版本敏感 |
| 反爬难度 | 需要 cookie | 自带 cookie |

**结论**：能调 API 就调 API。浏览器自动化只作为 fallback。

### 6.2 跨线程 GUI 设计

tkinter 是单线程的，**所有 UI 操作必须在主线程**。网络请求放子线程。

```python
# 子线程把结果放进队列
result_queue.put(("success", data))

# 主线程用 after() 轮询
def _poll_queue():
    try:
        msg = result_queue.get_nowait()
        # 更新 UI
    except queue.Empty:
        pass
    root.after(100, _poll_queue)

root.after(100, _poll_queue)
```

**为什么用队列 + 轮询，不用回调**：
- 简单，不会因为回调时机不对导致 tkinter 报错
- 调试方便，逻辑是顺序的

### 6.3 Playwright 持久化策略

```python
context = await playwright.chromium.launch_persistent_context(
    user_data_dir="./chrome_profile",  # cookies 落盘到这个目录
    headless=False,  # 首次让用户能看到浏览器
)
```

**首次使用流程**：
1. 启动 Playwright（带持久化 profile）
2. 自动打开 B 站登录页
3. 用户手动登录（输账号密码 / 扫码）
4. 登录成功后 cookies 落盘
5. 之后启动就直接用 cookies，**无需再次登录**

**这个方案的好处**：
- 用户只需要登录一次
- 之后完全自动化
- 即使 SESSDATA 过期也没事（Playwright 自动刷新 cookies）

### 6.4 Windows 环境适配

**编码问题**（Windows Python 默认 GBK）：
```python
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
```

**高 DPI 问题**（4K 屏 tkinter 字体模糊）：
```python
import ctypes
ctypes.windll.shcore.SetProcessDpiAwareness(1)
```

**路径问题**：用户项目目录（自定义），所有路径建议使用绝对路径而不是依赖 `C:\Users\...` 默认位置。

---

## 七、当前状态与已知限制

### 已完成

- GUI 界面（tkinter，含 SESSDATA 输入、Playwright 勾选）
- B 站 API 调用（带 Referer 和 cookie）
- 字幕下载 + TXT 格式化（`HH:MM:SS.mmm --> HH:MM:SS.mmm: 内容`）
- Playwright 持久化登录态
- 三段式 worker（Playwright → API+SESSDATA → 错误提示）
- 中英文双版本文档

### 已知限制

- **B 站对未登录用户锁字幕**（这是 B 站策略，不是工具的锅）
- **目标视频必须本身有字幕**（没字幕的巧妇难为无米之炊）
- **SESSDATA 会过期**（约 1 个月，需要重新复制）
- **Playwright 首次需要手动登录**（这是 B 站反爬的措施）
- **不支持批量下载**（一次一个 URL）
- **不支持 SRT / VTT 格式**（只输出 TXT）

### 测试过的视频

| BV 号 | 标题 | 字幕情况 |
|---|---|---|
| `<示例视频BV号>` | 大疆Pocket 4P | ❌ 无字幕 |
| `<示例视频BV号>` | Rick Astley MV | ⚠️ 12条字幕全被锁（版权） |
| `<示例视频BV号>` | MIT 6.0001 Python | ⚠️ 中英字幕被锁 |
| `<示例视频BV号>` | SICP 公开课 | ⚠️ 字幕被锁 |
| `<示例视频BV号>` | 哈佛 CS50 | ⚠️ 无字幕 |

**结论**：5 个测试视频 0 个能纯匿名下载字幕。**这个项目的存在意义就是解决"登录态"问题**。

---

## 八、未来可以做的优化

### 短期（1-2 周）

- **SRT 格式支持**：SRT 是视频播放器通用的字幕格式，加一个 checkbox 让用户选
- **批量下载**：支持一次粘贴多个 URL（换行分隔）
- **AI 总结集成**：拿到字幕后自动调 LLM 总结（类似 lxfater 的 BilibiliSummary 项目的核心功能）
- **字幕预览**：GUI 上加一个文本框显示字幕内容

### 中期（1-2 月）

- **多语言字幕选择**：很多视频有中英双语字幕，让用户选语言
- **AI 字幕 fallback**：如果只有 AI 字幕（没 UP 主上传），自动用
- **断点续传**：大视频的字幕可能很长，支持断点续传
- **历史记录**：保存下载过的 URL，避免重复下载

### 长期（3 月+）

- **Web 服务化**：FastAPI 包一层，浏览器插件 / 其他工具可以调
- **弹幕获取**：B 站的弹幕也是公开数据，可以一起拿
- **视频信息抓取**：标题、UP 主、播放量、封面图
- **打包成 exe**：PyInstaller 打包，零依赖运行
- **跨平台**：macOS / Linux 支持

---

## 九、经验教训

**1. 调研开源项目时，要看代码运行的环境，而不只是看代码本身。**
Chrome 扩展能拿到字幕，不是因为 API 开放，是因为它在用户已登录的浏览器里跑。

**2. B 站对未登录用户的限制比想象的多。**
不只是字幕，评论、弹幕、推荐 API 都有不同程度的限制。涉及 B 站的项目，**先承认"需要登录态"，再开始写代码**。

**3. 调 B 站 API 时，Referer 和 cookie 是关键。**
`Referer: https://www.bilibili.com` 不带就 403，cookie 不带就拿到锁定的数据。

**4. 选 GUI 库时，tkinter 是最稳的选择。**
PyQt / PySide 打包麻烦，依赖重。tkinter 丑是丑点，但零依赖、跨平台、文档全。

**5. 跨线程通信用队列 + after() 轮询最简单。**
比回调、信号、事件总线都简单，调试也方便。

**6. 子 agent 协作时，任务要切分清楚。**
调研 → 设计 → 实现 → 测试，每个阶段一个 agent，效果最好。一次性让 agent 写完整个项目容易跑偏。

**7. 调研阶段的"快速验证"很重要。**
花 5 分钟调一个真实 API、看一个真实数据点，比看 1 小时文档有用。

**8. 用户体验的边界要考虑清楚。**
是强制登录、还是提供 SESSDATA、还是 Playwright 自动化？**给用户选择权，比替用户做决定更友好**。

---

## 十、附录

### 关键文件路径

```
项目根目录
├── main.py              # 主程序（942 行）
├── 使用手册.md            # 中文用户手册
├── README.md            # 英文说明
├── requirements.txt     # 依赖
└── subtitles/           # 字幕保存目录
```

### 测试 BV 号速查表

| BV 号 | 用途 |
|---|---|
| `<示例视频BV号>` | 测试无字幕情况 |
| `<示例视频BV号>` | 测试字幕被锁情况（版权视频） |
| `<示例视频BV号>` | 测试字幕被锁情况（公开课） |
| `<示例视频BV号>` | 测试字幕被锁情况（SICP） |

### B 站 API 端点速查

| 端点 | 方法 | 说明 |
|---|---|---|
| `/x/web-interface/view?bvid={BV}` | GET | 视频元信息 + 字幕列表 |
| `{subtitle_url}` | GET | 字幕 JSON 内容 |
| `/x/web-interface/search/type` | GET | 搜索（需要 wbi 签名） |
| `/x/web-interface/search/all/v2` | GET | 搜索 v2（需要 wbi 签名） |

### 关键 Headers

```python
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 ...",
    "Referer": "https://www.bilibili.com",  # 必填，否则 403
    "Cookie": "SESSDATA=xxx"  # 可选，有的话能解锁字幕 URL
}
```

### 依赖

```
requests>=2.28.0
playwright>=1.40.0
```

### 启动方式

```bash
# 安装依赖
pip install -r requirements.txt
playwright install chromium

# 启动
python main.py
```

---

## 十一、经验总结 v2：自动登录 + 错误修复（2026-06-17 同日追加）

**坑 7（崩溃 bug）**：`_pick_best_subtitle` 优先选中文，遇到 `is_lock=true` 的字幕时 `subtitle_url=""`，下游 `fetch_subtitle_json` 抛 `ValueError: subtitle_url 为空`，整个工具崩。修复：把"url 为空"的字幕优先级降到 99，并在 worker 里选完后二次校验，区分"没填 SESSDATA"和"SESSDATA 过期"给不同提示。

**坑 8（自动登录方案选择）**：B 站扫码登录有两个方案——纯 requests 调 API 拿二维码 + 轮询 status；或者 Playwright 打开登录页等用户扫。最终选 Playwright：实现简单、依赖已经装好、二维码浏览器自己显示。代价是启动慢 5-10 秒，但对一次性登录流程可接受。

**坑 9（cookies 缓存）**：登录态默认 30 天，每次让用户重登太蠢。落地 `bili_cookies.json` 文件缓存，启动时自动读入 SESSDATA 输入框；profile 目录 `bili_login_profile/` 单独放，避免和字幕获取的 `chrome_profile/` 互相污染。

---

> 写于 2026-06-17，星期三。
> 窗外有风，键盘在响，姜绅在旁边切水果。
> 这是AI 助手的第一个"完整项目复盘"，写得比较啰嗦，但是真心话。
> 下次再有项目，希望这文档能帮上忙。

---

## 十二、v3 追加：Selenium 方案（2026-06-18）

**坑 10（自动化检测）**：用 Playwright 拿 AI 字幕时，B 站偶尔会对 Playwright 内置 chromium 弹"请更换浏览器"。用户本机的 Chrome 120 没这问题（user-agent 是真实 Chrome）。**解决**：新增 Selenium 方案，用 `undetected_chromedriver` 启动用户 `<你的Chrome路径>/chrome.exe` + 复制 User Data，绕过 B 站的自动化检测。

**坑 11（User Data 文件锁）**：用户的 Chrome 经常开着，复制的 User Data 不完整。**解决**：复制前先检查，存在则复用；复制失败 fallback 到直接引用本机 User Data（要求用户先关 Chrome）。

**坑 12（Network 拦截）**：想抓 B 站 `bfs/ai_subtitle/...json` 的请求。**解决**：开 Chrome `--enable-logging --v=1` + `goog:loggingPrefs={'performance': 'ALL'}`，从 performance 日志正则提取 URL。配合 Selenium 内 `fetch()` 或 requests 带 cookie 拿 JSON，比 DOM 抓全字幕快得多。

**v3 总结**：main.py 从 1360 行扩到 ~1900 行。新增 `fetch_subtitle_via_selenium` + GUI 三选一抓取方式（API 优先 / Playwright 优先 / Selenium 优先），实现 Selenium→Playwright→API 三级 fallback。

---

## 十三、v3.5 追加：v5 hover+JS click 完整流程（2026-06-18）

**v3 失败原因**：v3 简单 click 经常 timeout，因为 B 站字幕按钮在 hover 前**不可见**。`WebDriverWait + element_to_be_clickable` 等不到元素。

**用户关键洞察**：「**需要鼠标在视频上悬停，然后才会有按钮，然后点击按钮**」。

**v4 验证**：仅加 hover 不够。`element_to_be_clickable` 在控制条 hover 后依然超时（`element click intercepted` 错误）。

**v5 完整流程（实测完美成功）**：

1. 启动 undetected Chrome + 注入 SESSDATA（先开主页注入更稳）
2. 打开视频 + 主动 `video.play()`（必须，否则 hover 触发不出控制条）
3. **hover 视频**（让控制条显示）：
   - hover `<video>` 元素
   - 再 hover `#bilibili-player` / `.bpx-player-container` 容器
4. **JS 强制 click 字幕按钮**：
   ```js
   const el = document.querySelector('.bpx-player-ctrl-subtitle-result');
   el.click();
   ```
5. **JS 强制 click 中文选项**（`ai-zh` / `zh-CN` / `zh-Hans` 三重兜底 + 含"中文"文本的兜底）
6. 等 AI 字幕生成（**首次 10-30 秒**，给 30 秒保险）
7. Network 拦截 `bfs/ai_subtitle/prod/...` URL
8. `requests` 带 cookies 下载 JSON
9. 解析 body 拿到带时间戳的字幕

**实测视频**（<示例视频BV号>）拿到 29 条字幕，前 5 条：

```
00:00:00.840 --> 00:00:03.960: 壁垒主播吃完麻辣烫不剔牙
00:00:03.960 --> 00:00:05.860: 给我缩成辣子鸡了
00:00:05.860 --> 00:00:06.680: 啊哈哈
00:00:06.680 --> 00:00:07.640: 不好意思啊
00:00:07.640 --> 00:00:08.160: 不好意思啊
```

**坑 13（控制条 hover 后才显示）**：v3 一直失败的根本原因。**解决**：v3.5 先 `play()` 再 hover `<video>`，再 hover 容器，然后才 JS click 按钮。

**坑 14（`element_to_be_clickable` 经常超时）**：即使 hover 后，`element_to_be_clickable` 也可能因 `element click intercepted` 失败。**解决**：直接用 `document.querySelector().click()` 绕过 EC 检查。

**坑 15（字幕按钮选择器多变）**：B 站改过 class 名。**解决**：多选择器兜底（`.bpx-player-ctrl-subtitle-result` / `.bpx-player-ctrl-subtitle` / `[class*="subtitle-result"]` / `[class*="subtitle"][class*="result"]`）。

**坑 16（中文选项选择器）**：通常 `[data-lan="ai-zh"]`，但有时是 `zh-CN` 或 `zh-Hans`。**解决**：三种选择器都试，失败再用含"中文"文本的兜底。

**坑 17（Network 拦截的 JSON body 为空）**：偶尔 URL 拦截到但 `body=[]`（B 站还在生成中）。**解决**：循环 12 次（60 秒）持续抓 logs + 拖动进度条触发 AI 生成。

**坑 18（requests 下载 AI 字幕 JSON）**：用 Selenium 内的 `fetch` 异步返回 None。**解决**：同步 `requests.get` 带 `cookies=cookies_dict` + `Referer` 头。

**v3.5 总结**：main.py 第 1873 行的 `fetch_subtitle_via_selenium` 完全重写。完整 hover + JS click 流程已集成。三级 fallback 保留：Network 拦截 → `__INITIAL_STATE__` → DOM 拖进度条。GUI 状态栏实时显示进度（启动 Chrome / 注入 cookies / hover / click 字幕 / click 中文 / 拦截 URL / 下载 JSON）。

**最终踩坑清单**：
1. 不要用 Playwright 内置 chromium（被 B 站检测）→ 用用户本机 Chrome + undetected_chromedriver
2. 不要直接 `find_element().click()` 字幕按钮（hover 前不可见）→ 先 `play()` + hover 再 JS click
3. 不要用 `element_to_be_clickable`（经常 timeout）→ JS `document.querySelector().click()`
4. 不要忘记 `--window-size=1280,800`（控制条显示异常）→ 加到 options
5. 不要忘记主动 `video.play()`（hover 触发不出控制条）→ muted + play()
6. Network 拦截需要 `goog:loggingPrefs={'performance': 'ALL'}` → set_capability
7. 不要用 Selenium 内的异步 fetch（返回 None）→ `requests.get` 带 cookies
8. 视频没有 AI 字幕时不要无限等待 → 60 秒超时后 fallback DOM 抓取
