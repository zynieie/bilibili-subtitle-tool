# -*- coding: utf-8 -*-
"""
示例：用 Playwright 抓取 B 站 AI 字幕。
把 bvid 改成你想测试的视频 BV 号即可。
"""
import sys, io, json, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from playwright.sync_api import sync_playwright

bvid = 'YOUR_VIDEO_BV'  # ← 替换成你想测试的视频 BV 号
url = f'https://www.bilibili.com/video/{bvid}/'

# 存放 hook 到的 AI 字幕 URL
hooked_urls = []
hooked_responses = []

with sync_playwright() as p:
    print('=== 启动 Chromium ===')
    browser = p.chromium.launch(
        headless=False,  # 第一次要可视化，方便用户手动登录
        args=['--disable-blink-features=AutomationControlled']
    )
    context = browser.new_context(
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        viewport={'width': 1280, 'height': 800},
    )
    page = context.new_page()
    
    # 监听所有网络请求，找 AI 字幕
    def on_response(response):
        url_path = response.url
        if 'bfs/ai_subtitle' in url_path or 'aisubtitle' in url_path:
            print(f'  🎯 HOOK: {response.status} {url_path[:120]}')
            hooked_urls.append(url_path)
            try:
                hooked_responses.append({
                    'url': url_path,
                    'status': response.status,
                    'body': response.json() if response.headers.get('content-type', '').startswith('application/json') else None,
                })
            except:
                hooked_responses.append({'url': url_path, 'status': response.status, 'body': None})
    
    page.on('response', on_response)
    
    print(f'=== 打开 {url} ===')
    page.goto(url, wait_until='domcontentloaded', timeout=30000)
    print('  页面加载完成')
    time.sleep(3)  # 等播放器初始化
    
    # 找字幕按钮
    print('=== 找字幕按钮 ===')
    try:
        subtitle_btn = page.locator('.bpx-player-ctrl-subtitle-result')
        if subtitle_btn.count() > 0:
            print(f'  找到 {subtitle_btn.count()} 个字幕按钮')
            print('  文本:', subtitle_btn.first.inner_text())
            print('  点击...')
            subtitle_btn.first.click()
            time.sleep(2)
            
            # 找中文选项
            print('=== 找中文选项 ===')
            zh_option = page.locator('[data-lan="ai-zh"], [data-lan="zh-CN"]')
            print(f'  找到 {zh_option.count()} 个中文选项')
            if zh_option.count() > 0:
                for i in range(zh_option.count()):
                    print(f'  [{i}] text={zh_option.nth(i).inner_text()}, data-lan={zh_option.nth(i).get_attribute("data-lan")}')
                zh_option.first.click()
                print('  已点击中文选项')
                time.sleep(5)  # 等 AI 字幕生成
        else:
            print('  ❌ 找不到字幕按钮')
    except Exception as e:
        print(f'  错误: {e}')
    
    # 检查 hook 结果
    print()
    print(f'=== Hook 到的 AI 字幕 URL 数: {len(hooked_urls)} ===')
    for u in hooked_urls[:5]:
        print(f'  {u[:150]}')
    
    if hooked_responses:
        print()
        print('=== 第一个响应的 body 预览 ===')
        first = hooked_responses[0]
        if first['body']:
            body = first['body']
            print(f'  body keys: {list(body.keys()) if isinstance(body, dict) else type(body).__name__}')
            if isinstance(body, dict) and 'body' in body:
                sub_body = body['body']
                if isinstance(sub_body, list):
                    print(f'  字幕条数: {len(sub_body)}')
                    for item in sub_body[:3]:
                        print(f'    {item.get("from", "?")} --> {item.get("to", "?")}: {item.get("content", "")[:60]}')
            else:
                print(f'  {str(body)[:500]}')
    
    # 检查 DOM 中的字幕
    print()
    print('=== DOM 中的字幕文本 ===')
    try:
        sub_texts = page.locator('.bili-subtitle-x-subtitle-panel-text')
        print(f'  找到 {sub_texts.count()} 个字幕文本元素')
        for i in range(min(sub_texts.count(), 5)):
            print(f'  [{i}] {sub_texts.nth(i).inner_text()[:80]}')
    except Exception as e:
        print(f'  错误: {e}')
    
    print()
    print('=== 截图保存 ===')
    page.screenshot(path='./example_screenshot.png')
    print('  截图: ./example_screenshot.png')

    # 保存 hook 结果
    with open('./example_hooked.json', 'w', encoding='utf-8') as f:
        json.dump({
            'hooked_count': len(hooked_urls),
            'hooked_urls': hooked_urls,
            'first_response': hooked_responses[0] if hooked_responses else None,
        }, f, ensure_ascii=False, indent=2, default=str)
    print('  hook 数据: ./example_hooked.json')
    
    browser.close()
    print()
    print('=== 完成 ===')
