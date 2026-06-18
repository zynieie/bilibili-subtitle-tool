# B 站字幕获取工具 — 使用手册

> 给用户用的小工具 ✨ 一键获取 B 站视频字幕

---

## 1. 这是什么？

一个 Python 小工具，带 GUI 界面，输入 B 站视频 URL 就能拿到字幕，显示在窗口里，同时保存到 `subtitles/` 目录下。

**核心优势**：
- 不需要登录 B 站账号（普通视频）
- 支持**「自动登录 B 站」按钮**（推荐）：一键扫码登录，自动保存 cookies
- 支持 SESSDATA cookie 注入（解除字幕锁定）
- 支持 Playwright 浏览器自动化（拿到 AI 字幕）
- 多种方案 fallback，拿不到字幕会明确提示原因

---

## 2. 安装（一次性的）

### 2.1 确认有 Python
打开 PowerShell 或 CMD，输入：
```bash
python --version
```
看到 `Python 3.7+` 即可。

### 2.2 安装依赖
```bash
cd 项目根目录
pip install -r requirements.txt
```

如果你要用 **Playwright 方案**（可选），还需要装浏览器内核：
```bash
playwright install chromium
```

### 2.3 跑一下试试
```bash
python main.py
```
应该会弹出一个粉色的窗口，标题是「B 站字幕获取工具 - 作者: AI 助手」。

---

## 3. 四种获取方案

| 方案 | 适用场景 | 是否需要登录 |
|------|---------|------------|
| **API 默认** | 大部分有 CC 字幕的公开视频 | 否 |
| **API + 自动登录** | 字幕被 B 站锁定的视频（**最推荐**） | 点按钮扫码一次 |
| **API + SESSDATA** | 字幕被 B 站锁定的视频 | 手动填 SESSDATA |
| **Playwright 浏览器** | 想拿 AI 字幕，或 API 拿不到时 | 首次需手动登录 B 站 |

工具会按 **Playwright → API** 顺序尝试（如果勾选了 Playwright），前者失败自动 fallback。

> 💡 **首选「自动登录 B 站」按钮**：点一下 → 弹浏览器 → 用 B 站 App 扫码 → cookies 自动保存，以后所有 API 调用都自动带 cookie。

---

## 4. 使用方法

### 4.1 启动
在项目目录下双击 `main.py`，或者在命令行里 `python main.py`。

### 4.2 操作流程
1. **（首次强烈推荐）点「自动登录 B 站」按钮**：
   - 弹出浏览器 → 扫码 → 自动保存 cookies
   - 以后所有 API 调用都自动带 cookie，无需再登录
   - 详细步骤见 [第 5.5 节](#55-推荐自动登录-b-站一键扫码)
2. **粘贴 URL** 到输入框（支持三种形式）：
   - 完整 URL：`https://www.bilibili.com/video/<示例视频BV号>?spm_id_from=...`
   - 短 URL：`https://b23.tv/xxxxx`（需要展开后才能拿到 BV 号，所以**建议直接用完整 URL**）
   - 纯 BV 号：`<示例视频BV号>`
3. **（可选）填 SESSDATA**：如果你要拿的视频字幕被锁定，填一下
4. **选择抓取方式**（v3 新增）：
   - **API 优先**（默认，最快，< 1 秒）
   - **Playwright 优先**（拿 AI 字幕，5-10 秒）
   - **Selenium 优先**（用户本机 Chrome，Network 拦截 ai_subtitle，5-15 秒）
5. **点「获取字幕」按钮**（或者按回车）
6. **看状态栏**：
   - 状态会从「正在用 Selenium 打开...」→「Network 拦截成功 ✓」/ 「Playwright 拿到AI 字幕」/「正在请求视频元信息...」→「已完成 ✓ 已保存到: ...」
7. **看字幕内容**：自动显示在下方文本框
8. **看保存文件**：在 `subtitles/` 目录下，每个视频生成一个 `<标题>.txt`

---

## 5. 怎么获取登录态？

工具有两种方式拿到登录态：**「自动登录 B 站」按钮（推荐）** 和 **手动填 SESSDATA**。

---

### 5.5 推荐：自动登录 B 站（一键扫码）

**最推荐的方式**：不用 DevTools 找 cookie，不用手动复制粘贴，工具自动搞定。

#### 5.5.1 操作步骤

1. 启动工具 `python main.py`
2. 在「登录态（可选）」区域点 **「自动登录 B 站」** 按钮
3. 弹出确认对话框 → 点「是」
4. **Chrome 浏览器自动打开**，并跳转到 B 站登录页
5. 工具状态栏会显示「请在浏览器中用 B 站 App 扫码登录（超时 120 秒）」
6. 打开手机上的 B 站 App → 右上角扫码 → 扫浏览器里的二维码
7. 手机上点「确认登录」
8. 浏览器自动跳转到 `https://www.bilibili.com`，工具自动检测到登录成功
9. 浏览器自动关闭
10. 工具弹出「登录成功」提示，登录状态显示 **「🟢 已登录」**
11. 之后**所有 API 调用都自动带 cookie**，无需任何额外操作

#### 5.5.2 cookies 存在哪？

登录成功后 cookies 存到 `项目根目录bili_cookies.json`，内容形如：

```json
{
  "saved_at": "2026-06-17T22:30:15",
  "cookies": {
    "SESSDATA": "xxxxx",
    "buvid3": "yyyyy",
    "bili_jct": "zzzzz",
    "...": "..."
  }
}
```

- 工具**启动时自动加载**这个文件，把 SESSDATA 填入输入框
- 想换账号 → 删除 `bili_cookies.json` 后重新登录
- SESSDATA 默认有效期约 30 天，过期后点「自动登录」按钮重新扫码即可

#### 5.5.3 注意事项

- 工具会自动选择本机已安装的 Chrome；本机没有的话会 fallback 到 playwright 内置的 chromium
- 浏览器**会自动关闭**（和「使用 Playwright 浏览器」模式的"不关闭"不同）
- 登录专用的 profile 存在 `项目根目录bili_login_profile\`，和字幕获取的 `chrome_profile/` 互不干扰

---

### 5.1 步骤（Chrome / Edge 通用）— 手动 SESSDATA 方式

如果「自动登录」按钮用不了（比如 Playwright 没装好），可以手动复制 SESSDATA。


### 5.1 步骤（Chrome / Edge 通用）
1. 打开浏览器，**登录** `https://www.bilibili.com`
2. 按 `F12` 打开 DevTools
3. 切到 **Application** 标签页
4. 左侧找到 **Cookies** → `https://www.bilibili.com`
5. 在右边找到 `SESSDATA` 这一行
6. 双击 Value 列，**复制**那串字符（很长的一串字母数字混合）
7. 粘贴到工具的「SESSDATA」输入框

### 5.2 示意图（文字版）
```
DevTools → Application
  └── Storage
       └── Cookies
            └── https://www.bilibili.com
                 ├── SESSDATA  ← 复制这个 Value
                 ├── buvid3
                 ├── ...
```

### 5.3 注意事项
- SESSDATA **有时效**，大概 1-2 周会过期，过期后重新复制一份
- 工具用 `show="*"` 隐藏输入，**不会被旁观者看到**
- **不要把 SESSDATA 发给任何人**，相当于你的 B 站临时密码

---

## 6. 怎么用 Playwright 拿 AI 字幕？

### 6.1 什么时候用？
- 视频没有人工 CC 字幕，但有 B 站自动生成的 AI 字幕
- 普通 API 拿不到字幕时（Playwright 是终极 fallback）

### 6.2 首次使用步骤
1. 确保已装好 Playwright：
   ```bash
   pip install playwright
   playwright install chromium
   ```
2. 启动工具，**勾选**「使用 Playwright 浏览器」
3. 粘贴 URL，点「获取字幕」
4. 第一次会**自动弹出 Chrome 窗口**
5. 在弹出的 Chrome 里**登录 B 站**（扫码/账号密码都行）
6. 登录完后，**等工具自动继续**（不需要手动操作浏览器）
7. 字幕会显示在工具的文本框里

### 6.3 后续使用
- 登录态保存在 `项目根目录chrome_profile\` 目录
- **下次再勾选 Playwright 时，会自动复用登录态，无需重新登录**
- 想要换账号就删除这个 `chrome_profile` 文件夹

### 6.4 浏览器怎么不关？
- 工具**故意不关闭** Playwright 启动的 Chrome 窗口
- 关闭窗口前会保持打开状态，方便你手动验证登录成功
- 工具主窗口关闭时，浏览器也会自动退出
- 持久化目录里的 cookies 不会丢

---

## 6.5 v3 新增：怎么用 Selenium 模式拿字幕？

Selenium 模式是 v3 新增的第三种抓取方式。**用用户本机的 Chrome（带 User Data）**，能绕过 B 站对自动化浏览器的检测，是拿 AI 字幕的最强方案。

### 6.5.1 什么时候用？
- API 拿不到字幕、Playwright 也失败的视频
- 想直接 Network 拦截 ai_subtitle JSON（最准确的中文 AI 字幕）
- 想用用户日常在用的 Chrome profile（更稳定，登录态天然带）

### 6.5.2 首次使用步骤（要用户先在 Chrome 登录 B 站）

1. **确保已装好 selenium + undetected-chromedriver**：
   ```bash
   pip install selenium undetected-chromedriver
   ```
2. **确认用户 Chrome 路径**：`<你的Chrome路径>/chrome.exe`（已在本工具配置好）
3. **确认用户本机 Chrome 已登录 B 站**：
   - 打开 Chrome → 访问 `https://www.bilibili.com` → 右上角应有用户头像
   - **如果没登录**：先用 Chrome 登录一次（自动登录按钮或手动扫码都行）
4. **启动工具**：`python main.py`
5. **选择「Selenium 优先」**（在「抓取方式」LabelFrame 里）
6. **粘贴 URL**，点「获取字幕」
7. **首次会自动复制 Chrome User Data** 到 `项目根目录chrome_userdata_copy\`（需要 30 秒 ~ 1 分钟）
8. **启动用户的 Chrome**（用 undetected_chromedriver）
9. **打开 B 站视频页** → **Network 拦截 ai_subtitle JSON** → 拿到字幕
10. 字幕会显示在工具的文本框里

### 6.5.3 后续使用
- 第一次复制 User Data 后，**之后秒启**
- Chrome User Data 副本在 `项目根目录chrome_userdata_copy\`，复用用户 Chrome 的登录态
- 如果用户换了 B 站账号，**先在本机 Chrome 重新登录**，然后删除 `chrome_userdata_copy/` 让工具重新复制

### 6.5.4 Selenium 方案抓取策略（三管齐下）

| 抓取方式 | 原理 | 准确度 | 适用视频 |
|---------|------|------|---------|
| **Network 拦截 ai_subtitle** | 监听 Chrome 的网络请求，捕获 `bfs/ai_subtitle/...json` | ★★★★★ | B 站有 AI 字幕的视频（最准） |
| **window.__INITIAL_STATE__** | 从页面 JS 全局变量读取字幕数据 | ★★★★ | B 站有 CC 字幕的视频 |
| **DOM 拖进度条** | 拖动 video 元素 currentTime，每秒抓一次字幕文本 | ★★ | 短视频（< 60s）的兜底 |

优先级：**Network 拦截** → `__INITIAL_STATE__` → **DOM 抓取**

### 6.5.5 注意事项

- **用户的 Chrome 最好先关闭**：如果 Chrome 正在运行，复制 User Data 会失败（某些文件被锁），此时 Selenium 会退化为直接引用本机 User Data，但**Chrome 同时启动会冲突**，用户需要先关 Chrome
- **首次启动慢**：5-15 秒（其中复制 User Data 30s-60s）
- **每次启动都新建 Chrome 实例**：不像 Playwright 可以复用窗口，Selenium 用完就关
- **不要手动改 chrome_userdata_copy**：里面的文件用户可以查看，但删了会让工具重新复制

---

## 7. 测试用的视频

### 7.1 已知有字幕的视频（推荐测试用）
```
# MIT 公开课（英文字幕）
https://www.bilibili.com/video/<示例视频BV号>

# 其它请自行测试
```

### 7.2 目标视频（无字幕，验证错误处理）
```
https://www.bilibili.com/video/<示例视频BV号>
```
> ⚠️ 这个视频本身**没有字幕**，运行会提示「该视频没有可用的字幕」，这是**正常**的，不是工具 bug。
> 用这个视频可以测试工具的错误处理是否友好。

---

## 8. 界面说明

```
┌──────────────────────────────────────────────────┐
│ B 站字幕获取工具                                   │
├──────────────────────────────────────────────────┤
│ 视频URL: [_________________________________] [获取] │
├──────────────────────────────────────────────────┤
│ ┌─登录态（可选）─────────────────────────────┐    │
│ │ SESSDATA: [••••••••••••••••••••] [自动登录B站] │    │
│ │ 登录状态: 🟢 已登录（已自动填入 SESSDATA）     │    │
│ │ 💡 推荐点「自动登录 B 站」按钮用 B 站 App 扫码  │    │
│ └────────────────────────────────────────────┘    │
│ ┌─抓取方式────────────────────────────────────┐   │
│ │ (○) API 优先（默认，最快）                   │    │
│ │ ( ) Playwright 优先（拿 AI 字幕）            │    │
│ │ ( ) Selenium 优先（用户本机 Chrome 绕过检测）│    │
│ │ 💡 Selenium 首次需在用户 Chrome 登录 B 站     │    │
│ └────────────────────────────────────────────┘    │
├──────────────────────────────────────────────────┤
│ 状态: 等待输入URL...                               │
│ 视频标题:                                        │
│ 字幕条数:                                        │
├──────────────────────────────────────────────────┤
│ ┌─字幕内容────────────────────────────────┐    │
│ │                                          │    │
│ │  (滚动文本框,显示字幕)                    │    │
│ │                                          │    │
│ └──────────────────────────────────────────┘    │
│ [打开保存目录]                       作者: AI 助手  │
└──────────────────────────────────────────────────┘
```

---

## 9. 字幕文件格式

保存的 `.txt` 样例：

```
00:00:00.000 --> 00:00:05.200: 你好，欢迎来到B站
00:00:05.200 --> 00:00:10.500: 这里是字幕内容
00:00:10.500 --> 00:00:15.000: 可以直接读懂
```

这种格式是 SRT 风格，大多数播放器（如 PotPlayer、QQ 影音）都能识别。如果想转成纯文本（不要时间戳），可以全局替换正则 `\d{2}:\d{2}:\d{2}\.\d{3} --> \d{2}:\d{2}:\d{2}\.\d{3}: ` 为空。

---

## 10. 常见问题

### Q1: 提示「该视频没有可用的字幕」怎么办？
A: 可能原因：
1. 视频本身没有 CC 字幕也没有 AI 字幕（**最常见**）
2. 字幕被 B 站锁定 → 点「自动登录 B 站」按钮扫码登录
3. SESSDATA 已过期 → 点「自动登录 B 站」按钮重新扫码
4. 都不行 → 选择「Playwright 优先」或「Selenium 优先」试试

> 在 B 站视频页面看右下角，如果有个「字幕」开关 → 说明有 CC 字幕。

### Q1.5: 提示「字幕被锁定（需要登录）」怎么办？
A: 这是 B 站对未登录用户的限制。解决方法：
1. **推荐**：点「自动登录 B 站」按钮用 B 站 App 扫码（最简单）
2. 手动从浏览器 DevTools 复制 SESSDATA 填到「SESSDATA」输入框
3. 选择「Playwright 优先」或「Selenium 优先」（首次会弹出登录窗口）

### Q1.6: 三种抓取方式怎么选？
A: 推荐策略：
- **平时**：API 优先（最快，< 1 秒）
- **拿 AI 字幕**：Playwright 优先（够用、稳定）
- **Playwright 也失败**：Selenium 优先（兜底，最强）

### Q2: 提示「未安装 Playwright」？
A: 运行：
```bash
pip install playwright
playwright install chromium
```

### Q3: Playwright 弹出 Chrome 后没反应？
A: 首次启动需要等 8 秒左右让字幕数据注入。如果一直卡住：
1. 确认 Chrome 窗口已经**完全加载**完 B 站页面
2. 确认你**已登录** B 站（右上角有头像）
3. 删除 `chrome_profile/` 文件夹重试

### Q4: 提示「HTTP 403」或「B 站 API 返回错误 code=-352」？
A: 这是 B 站的风控，可能是：
- **请求太频繁**：等几分钟再试
- **SESSDATA 过期**：重新复制一份
- **本机 IP 被风控**：换网络

### Q5: 提示「无法识别 BV 号」？
A: 检查 URL 是否完整，最好直接用完整 URL。

### Q6: 字幕是英文的？
A: 工具会按优先级自动选择：中文(zh-CN/zh-Hans) > 中英混合 > 英文 > 第一条。如果视频只有英文字幕，那就只能拿英文了。

### Q7: GUI 字体很小/糊？
A: Windows 11 默认会有 DPI 缩放。本工具已经加了高 DPI 适配。如果还是糊，试试在主窗口标题栏右键 → 属性 → 兼容性 → 修改高 DPI 设置。

### Q8: 怎么一次性处理多个视频？
A: 当前版本不支持批量。批量功能可以基于本工具扩展（外层写个 for 循环调核心函数即可）。

### Q9: 选了 Selenium 优先但提示「未安装 selenium」？
A: 运行：
```bash
pip install selenium undetected-chromedriver
```

### Q10: Selenium 启动失败「用户的 Chrome 不存在」？
A: 工具默认用 `<你的Chrome路径>/chrome.exe`。如果用户把 Chrome 装到别的位置，需要改 `main.py` 第 86 行附近的 `CHROME_EXE` 常量。

### Q11: Selenium 启动失败「用户本机 Chrome 正在运行」？
A: undetected_chromedriver 不能和正在运行的 Chrome 共享 User Data。解决：
1. **最简单**：先关用户的 Chrome，再点「获取字幕」
2. **不关**：第一次会复制 User Data 到 `chrome_userdata_copy/`，但如果 Chrome 锁了某些文件，复制会失败，工具会提示「请用户先关闭 Chrome」

### Q12: Selenium 模式启动很慢？
A: 首次启动：
- 复制 Chrome User Data：30 秒 ~ 1 分钟
- 启动 undetected Chrome：5-15 秒
- 总计可能 1-2 分钟

之后启动：5-15 秒（不再复制 User Data）

### Q13: Selenium 拿到的是 DOM 字幕（method=dom）不是 AI 字幕？
A: 说明 Network 拦截和 __INITIAL_STATE__ 都没拿到。可能是：
1. 视频没有 AI 字幕（UP 主没开 AI）
2. 用户 Chrome 的 User Data 没复制完整
3. B 站改了 ai_subtitle 接口路径

解决方案：换视频试试，或改用 Playwright 优先。

### Q14: Selenium 模式下，状态栏显示「字幕按钮 click 失败」怎么办？
A: v5 实测发现 99% 的情况是「**没 hover 视频**」导致控制条没显示，所以 JS click 找不到按钮。v3.5 已自动处理：
- 主动 `video.play()` 2 秒
- hover 到 `<video>` 元素
- 再 hover 到 `#bilibili-player` 容器
- 然后才 JS click 字幕按钮

如果还失败，99% 是视频本身没有 AI 字幕（UP 主没开），用 Playwright 模式试试。

### Q14: Selenium 模式下，状态栏显示「字幕按钮 click 失败」怎么办？
A: v5 实测发现 99% 的情况是「**没 hover 视频**」导致控制条没显示，所以 JS click 找不到按钮。v3.5 已自动处理：
- 主动 `video.play()` 2 秒
- hover 到 `<video>` 元素
- 再 hover 到 `#bilibili-player` 容器
- 然后才 JS click 字幕按钮

如果还失败，99% 是视频本身没有 AI 字幕（UP 主没开），用 Playwright 模式试试。

---

## 11. 文件位置

- **项目根目录**：`项目根目录`
- **主程序**：`项目根目录main.py`
- **字幕保存目录**：`项目根目录subtitles\`
- **自动登录 cookies 缓存**：`项目根目录bili_cookies.json`
- **自动登录浏览器 profile**：`项目根目录bili_login_profile\`
- **Playwright 浏览器配置**（拿 AI 字幕用）：`项目根目录chrome_profile\`
- **点击「打开保存目录」**按钮 = 用 Windows 资源管理器打开 subtitles 文件夹

---

## 12. 卸载

直接删除整个 `项目根目录` 文件夹即可，没有任何注册表/系统残留。

---

## 13. 高级：怎么扩展？

如果以后想加功能（比如 AI 字幕、批量下载、字幕翻译），核心逻辑在 `main.py` 顶部的"字幕获取核心逻辑"部分：

- `extract_bvid()` — 提取 BV 号
- `fetch_video_info(bvid, cookies=None)` — 拉视频元信息
- `fetch_subtitle_json(url, cookies=None)` — 拉字幕 JSON
- `fetch_subtitle_via_playwright(bvid, status_callback=None)` — Playwright 备用方案
- `bili_login_with_playwright(status_callback=None, headless=False)` — **自动扫码登录**
- `save_cookies_to_cache(cookies)` / `load_cookies_from_cache()` / `is_cookies_valid(cookies)` — **cookies 缓存**
- `format_subtitle_text()` — 格式化字幕

这几个函数是纯函数，不依赖 GUI，可以直接 import 调用。

---

## 14. 联系作者

遇到 bug 或想加功能，告诉AI 助手~

作者：AI 助手 ✨
