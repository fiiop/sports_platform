"""Mobile message list and avatar conversations in a temporary test database."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from urllib.request import urlopen

from playwright.sync_api import expect, sync_playwright
import browser_campus_visual as helpers

ROOT = Path(__file__).resolve().parents[1]
BASE = 'http://127.0.0.1:8769'
helpers.BASE = BASE


def main():
    artifacts = ROOT / 'artifacts'
    artifacts.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='chat-visual-') as directory:
        directory = Path(directory)
        pictures = []
        for index, color in enumerate(('#71ab9c', '#6f8bb7', '#c18b68')):
            image = directory / f'avatar-{index}.png'
            helpers.fixture_image(image, color, str(index))
            pictures.append(image)
        env = dict(os.environ, DATABASE_URL='sqlite:///' + (directory / 'test.db').as_posix(),
                   COOKIE_SECURE='false', AI_API_KEY='', REMINDERS_ENABLED='false')
        with (directory / 'server.log').open('w', encoding='utf-8') as log:
            process = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'app.main:app', '--host',
                                        '127.0.0.1', '--port', '8769'], cwd=ROOT, env=env, stdout=log, stderr=log)
            try:
                for _ in range(80):
                    if process.poll() is not None:
                        raise RuntimeError('Temporary chat server stopped')
                    try:
                        with urlopen(BASE + '/', timeout=1):
                            break
                    except Exception:
                        time.sleep(.2)
                else:
                    raise RuntimeError('Temporary chat server startup timed out')
                with sync_playwright() as pw:
                    browser = pw.chromium.launch(channel='msedge', headless=True)
                    accounts = [helpers.account(browser, name) for name in ('chat_host_test', 'chat_peer_test', 'chat_long_test')]
                    names = ['小林 · 测试', '阿青 · 测试', '周末一起去操场慢慢跑步的同学 · 测试']
                    for index, (context, uid) in enumerate(accounts):
                        helpers.success(context.request.put(BASE + '/api/profile/identity', data={'nickname': names[index], 'bio': '临时测试资料'}))
                        helpers.success(context.request.post(BASE + '/api/profile/avatar', multipart={'file': {
                            'name': pictures[index].name, 'mimeType': 'image/png', 'buffer': pictures[index].read_bytes()}}))
                    owner, owner_id = accounts[0]
                    peer, peer_id = accounts[1]
                    other, other_id = accounts[2]
                    page = owner.new_page()
                    errors = []
                    page.on('pageerror', lambda error: errors.append(str(error)))
                    # A slow deferred script must not let authenticated rendering run early.
                    delayed, initial_requests = [], []
                    page.route('**/static/discovery.js?*', lambda route: delayed.append(route))
                    page.on('request', lambda request: initial_requests.append(request.url)
                            if request.url.endswith('/api/me') else None)
                    page.goto(BASE + '/#messages', wait_until='commit')
                    for _ in range(60):
                        if delayed:
                            break
                        page.wait_for_timeout(50)
                    assert delayed and not initial_requests
                    delayed.pop().continue_()
                    page.unroute('**/static/discovery.js?*')
                    page.wait_for_load_state('domcontentloaded')
                    page.wait_for_function('campus.profile!==null')
                    when = page.evaluate('new Date(Date.now()+86400000).toISOString()')
                    helpers.create_activity(peer, when, '羽毛球', '体育馆 2 号场')
                    helpers.create_activity(other, when, '跑步', '南苑操场')
                    chat = helpers.success(owner.request.post(BASE + f'/api/buddies/{peer_id}/chat'))['id']
                    other_chat = helpers.success(owner.request.post(BASE + f'/api/buddies/{other_id}/chat'))['id']
                    for context, text in ((peer, '周日下午去打羽毛球吗？'), (owner, '好呀！我带球，你带球拍 🏸'),
                                          (peer, '没问题，我们体育馆门口见。')):
                        helpers.success(context.request.post(BASE + f'/api/buddy-chats/{chat}/messages', data={'body': text}))
                    helpers.success(other.request.post(BASE + f'/api/buddy-chats/{other_chat}/messages', data={'body': '晚饭后去操场跑两圈，有空一起呀。'}))
                    group = helpers.create_activity(owner, when, '羽毛球', '体育馆 3 号场', 4)
                    meeting = helpers.success(peer.request.post(BASE + f'/api/activities/{group["id"]}/join', data={}))
                    helpers.success(peer.request.post(BASE + f'/api/meetups/{meeting["id"]}/messages', data={'body': '我会提前十分钟到，大家一起热身。'}))
                    page.reload()
                    expect(page.locator('#buddyChats')).to_contain_text('阿青 · 测试')
                    expect(page.locator('#messageGroupHeading')).to_be_visible()
                    expect(page.locator('#buddyChats .unread-badge').first).to_be_visible()
                    helpers.visible_image(page, '#messageSelfAvatar img')
                    for width in (360, 390, 430):
                        helpers.no_overflow(page, width)
                        assert page.locator('#buddyChats').bounding_box()['y'] < 520
                    page.set_viewport_size({'width': 390, 'height': 844})
                    helpers.snapshot(page, 'messages-v42-list.png')
                    assert page.evaluate("async()=>{const old=document.querySelector('#buddyChats button');await loadBuddyChats();return old===document.querySelector('#buddyChats button');}")
                    assert page.evaluate("async()=>{const old=document.querySelector('#groupChats button');await loadMeetups();return old===document.querySelector('#groupChats button');}")
                    page.locator(f'[data-buddy-chat="{chat}"]').click()
                    expect(page.locator('#buddyChatTitle')).to_have_text('阿青 · 测试')
                    expect(page.locator('#buddyMessages .buddy-message')).to_have_count(3)
                    helpers.visible_image(page, '#buddyChatAvatar img')
                    helpers.visible_image(page, '#buddyMessages .mine img')
                    for width in (360, 390, 430):
                        helpers.no_overflow(page, width)
                        assert page.locator('#buddyMessages').bounding_box()['height'] > 440
                        box = page.locator('#buddySend').bounding_box()
                        assert box['y'] + box['height'] <= 844
                        incoming = page.locator('#buddyMessages .buddy-message:not(.mine)').first
                        outgoing = page.locator('#buddyMessages .mine')
                        assert incoming.locator('.chat-avatar').bounding_box()['x'] < incoming.locator('.message-bubble').bounding_box()['x']
                        assert outgoing.locator('.chat-avatar').bounding_box()['x'] > outgoing.locator('.message-bubble').bounding_box()['x']
                    page.set_viewport_size({'width': 390, 'height': 844})
                    helpers.snapshot(page, 'messages-v42-chat.png')
                    expect(page.locator('#buddyRate')).to_be_hidden()
                    page.locator('#buddyChatMenu > summary').click()
                    expect(page.locator('#buddyRate')).to_be_visible()
                    page.locator('#buddyRate').click()
                    expect(page.locator('#buddyRatingDialog')).to_be_visible()
                    expect(page.locator('#buddyChatMenu')).not_to_have_attribute('open', '')
                    page.locator('#buddyCloseRating').click()
                    for theme in ('night', 'ocean', 'lilac', 'forest'):
                        page.evaluate('theme=>applyTheme(theme)', theme)
                        helpers.no_overflow(page, 360)
                        if theme == 'night':
                            helpers.snapshot(page, 'messages-v42-chat-night.png')
                    page.locator('#buddyMessage').fill('带一瓶水，运动完一起吃饭。')
                    page.locator('#buddyMessage').fill('第一行\n第二行\n第三行\n第四行')
                    assert 70 < page.locator('#buddyMessage').bounding_box()['height'] <= 112
                    page.locator('#buddyChatBack').click()
                    page.locator(f'[data-buddy-chat="{chat}"]').click()
                    expect(page.locator('#buddyMessage')).to_have_value('第一行\n第二行\n第三行\n第四行')
                    assert page.locator('#buddyMessage').bounding_box()['height'] > 70
                    page.locator('#buddyMessage').fill('带一瓶水，运动完一起吃饭。')
                    page.locator('#buddySend').click()
                    expect(page.locator('#buddyMessages')).to_contain_text('运动完一起吃饭')
                    assert page.locator('#buddyMessage').bounding_box()['height'] < 50
                    page.locator('#buddyChatBack').click()
                    expect(page.locator('#messageListTitle')).to_be_visible()
                    page.locator('.message-notification-settings > summary').click()
                    expect(page.locator('#pushToggle')).to_be_visible()
                    page.locator('.message-notification-settings > summary').click()
                    page.locator(f'#groupChats [data-open-meetup="{meeting["id"]}"]').click()
                    expect(page.locator('#groupMessages')).to_contain_text('提前十分钟')
                    helpers.visible_image(page, '#groupMessages .chat-avatar img')
                    helpers.no_overflow(page, 360)
                    assert not errors, errors
                    browser.close()
                    print('PASS: message-list photos/unread/headers, stable polling, chat avatars/bubbles/menu, composer, group avatars and 360/390/430 themes')
            except Exception:
                log.flush()
                (artifacts / 'chat-visual-server.log').write_text((directory / 'server.log').read_text(encoding='utf-8', errors='replace'), encoding='utf-8')
                if 'page' in locals():
                    try:
                        page.screenshot(path=str(artifacts / 'chat-visual-failure.png'), full_page=True)
                    except Exception:
                        pass
                raise
            finally:
                subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True)
                process.wait(timeout=15)


if __name__ == '__main__':
    main()
