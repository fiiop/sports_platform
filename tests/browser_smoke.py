"""Real-browser smoke test; temporary database, no access to sports.db.
Run from repository root: python tests/browser_smoke.py
Requires Playwright and locally installed Microsoft Edge.
"""
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.request import urlopen
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"
ARTIFACTS.mkdir(exist_ok=True)
with tempfile.TemporaryDirectory(prefix="campus-move-test-") as directory:
    env = dict(os.environ, DATABASE_URL="sqlite:///" + (Path(directory) / "test.db").as_posix(), COOKIE_SECURE="false", AI_API_KEY="")
    with open(Path(directory) / "server.log", "w") as log:
        process = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8766"], cwd=ROOT, env=env, stdout=log, stderr=log)
        try:
            for _ in range(60):
                if process.poll() is not None:
                    raise RuntimeError("Test server failed to start")
                try:
                    with urlopen("http://127.0.0.1:8766/", timeout=1):
                        break
                except Exception:
                    time.sleep(0.2)
            else:
                raise RuntimeError("Test server startup timed out")
            with sync_playwright() as p:
                browser = p.chromium.launch(channel="msedge", headless=True)
                context = browser.new_context(viewport={"width":390,"height":844}, device_scale_factor=1, is_mobile=True, has_touch=True)
                # Deterministic map test: the phone cannot reach the external tile host.
                tile_failure = {"enabled": False}
                tile_image = (ROOT / "app/static/icon-192.png").read_bytes()
                def mock_tile(route):
                    if tile_failure["enabled"]:
                        route.fulfill(status=502, body="unavailable")
                    else:
                        route.fulfill(content_type="image/png", body=tile_image)
                context.route("https://tile.openstreetmap.org/**", lambda route: route.abort())
                context.route("**/api/map-tiles/**", mock_tile)
                page = context.new_page()
                errors=[]
                page.on("pageerror", lambda error: errors.append(str(error)))
                stale_script_requests = []
                def stale_navigation(route):
                    stale_script_requests.append(route.request.url)
                    route.fulfill(content_type="application/javascript", body="window.staleNavigation = true;")
                context.route("http://127.0.0.1:8766/static/app.js", stale_navigation)
                page.goto("http://127.0.0.1:8766/")
                page.screenshot(path=str(ARTIFACTS / "mobile-login.png"), full_page=True, animations="disabled")
                page.locator("#username").fill("campus_tester")
                page.locator("#password").fill("test-pass-123")
                page.locator("#registerButton").click()
                expect(page.locator("#authMsg")).to_contain_text("注册成功")
                page.locator("#authForm button[type=submit]").click()
                expect(page.locator("#appPanel")).to_be_visible()
                expect(page.locator("#reflectionMsg")).to_contain_text("当前周")
                page.locator('[data-page="plans"]').click()
                page.locator("#planTitle").fill("四周运动习惯")
                page.locator("#planTarget").fill("每周三次课后运动")
                page.locator("#weeklyMinutes").fill("120")
                page.locator("#planSubmit").click()
                expect(page.locator("#plans")).to_contain_text("四周运动习惯")
                page.locator('[data-page="records"]').click()
                page.locator("#duration").fill("30")
                page.locator("#recordDetails summary").click()
                page.locator("#note").fill('<img src=x onerror="window.attacked=1">')
                page.locator("#recordSubmit").click()
                expect(page.locator("#records")).to_contain_text("30 分钟")
                assert page.locator("#records img").count()==0
                page.locator("[data-edit-record]").click()
                page.locator("#duration").fill("45")
                page.locator("#recordSubmit").click()
                expect(page.locator("#records")).to_contain_text("45 分钟")
                page.locator('[data-page="home"]').click()
                expect(page.locator("#mMinutes")).to_have_text("45")
                page.locator("#reflectionDetails summary").click()
                page.locator("#reflection").fill("这周运动后更有精神。")
                page.locator("#nextAction").fill("下周二和周四课后快走。")
                page.locator("#reflectionForm button[type=submit]").click()
                expect(page.locator("#reflectionMsg")).to_contain_text("已保存")
                page.locator("#adjustPlan").click()
                expect(page.locator("#planFormTitle")).to_contain_text("调整")
                page.locator("#weeklyMinutes").fill("90")
                page.locator("#planSubmit").click()
                expect(page.locator("#planMsg")).to_contain_text("已保存")
                page.locator('[data-page="home"]').click()
                expect(page.locator("#completionLabel")).to_contain_text("50%")
                page.locator("#adviceButton").click()
                expect(page.locator("#adviceSource")).to_have_text("规则建议")
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                page.evaluate("window.scrollTo(0,0)")
                page.locator("#reflectionDetails").evaluate("el => el.open = false")
                page.locator("#adviceDetails").evaluate("el => el.open = false")
                page.evaluate("document.querySelector('#toast').classList.add('hidden')")
                page.screenshot(path=str(ARTIFACTS / "mobile-home.png"), full_page=True, animations="disabled")
                # Mobile list-first discovery, no-map publishing, map fallback and social controls.
                page.locator('[data-page="buddies"] svg').tap()
                expect(page.locator('#page-buddies')).to_be_visible()
                expect(page.locator('#buddyMapHost')).to_be_hidden()
                page.locator('#buddyMapView').click()
                page.wait_for_function("buddy.proxyTiles && document.querySelector('#buddyMap img.leaflet-tile-loaded')")
                tile_failure["enabled"] = True
                page.evaluate('buddy.map.setView([10,20],7);useBuddyTiles(true)')
                expect(page.locator('#buddyMapRetry')).to_be_visible()
                tile_failure["enabled"] = False
                page.locator('#buddyMapRetry').tap()
                expect(page.locator('#buddyMapRetry')).to_be_hidden()
                page.locator('.buddy-tabs [data-buddy-tab="mine"]').click()
                page.locator('#buddyPlace').fill('学校体育馆 2 号羽毛球场')
                page.locator('#buddyTime').fill('2099-10-18T10:00')
                page.locator('#buddyMoreDetails summary').click()
                page.locator('#buddyNote').fill('<img src=x onerror="window.attacked=1">新手友好')
                page.locator('[data-page="home"]').click()
                page.locator('[data-page="buddies"]').click()
                page.locator('.buddy-tabs [data-buddy-tab="mine"]').click()
                expect(page.locator('#buddyPlace')).to_have_value('学校体育馆 2 号羽毛球场')
                page.locator('#buddyPublish').click()
                expect(page.locator('#buddyPreviewDialog')).to_be_visible()
                assert page.locator('#buddyPreview img').count()==0
                page.locator('#buddyConfirmPublish').click()
                expect(page.locator('#buddyFormMsg')).to_contain_text('状态已公开')
                page.locator('.buddy-tabs [data-buddy-tab="discover"]').click()
                expect(page.locator('#buddyList')).to_contain_text('学校体育馆')
                assert page.locator('#buddyList img').count()==0
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                page.locator('[data-filter-sport="篮球"]').click()
                expect(page.locator('#buddyList')).to_contain_text('没有符合条件')
                page.locator('[data-filter-sport="羽毛球"]').click()
                expect(page.locator('#buddyList')).to_contain_text('学校体育馆')
                peer_context = browser.new_context(viewport={"width":390,"height":844})
                peer_context.request.post('http://127.0.0.1:8766/api/register', data={"username":"buddy_peer","password":"test-pass-123"})
                peer_context.request.post('http://127.0.0.1:8766/api/login', data={"username":"buddy_peer","password":"test-pass-123"})
                peer = peer_context.new_page()
                peer.on('pageerror', lambda error: errors.append(str(error)))
                peer.goto('http://127.0.0.1:8766/#buddies')
                expect(peer.locator('#buddyList')).to_contain_text('campus_tester')
                peer.locator('#buddyList [data-buddy-user]').click()
                expect(peer.locator('#buddyConversation')).to_be_visible()
                peer.locator('#buddyMessage').fill('周日上午十点一起打羽毛球吗？')
                peer.locator('#buddyChatBack').click()
                peer.locator('#buddyChats [data-buddy-chat]').click()
                expect(peer.locator('#buddyMessage')).to_have_value('周日上午十点一起打羽毛球吗？')
                peer.locator('#buddySend').click()
                expect(page.locator('#buddyUnread')).to_be_visible(timeout=10000)
                page.locator('.buddy-tabs [data-buddy-tab="messages"]').click()
                page.locator('#buddyChats [data-buddy-chat]').click()
                expect(page.locator('#buddyMessages')).to_contain_text('周日上午十点')
                page.locator('#buddyMessage').fill('可以，体育馆见！')
                page.locator('#buddySend').click()
                expect(peer.locator('#buddyMessages')).to_contain_text('体育馆见', timeout=10000)
                peer.locator('#buddyRate').click()
                expect(peer.locator('#buddySaveRating')).to_be_enabled()
                peer.locator('#buddyScore').select_option('5')
                peer.locator('#buddySaveRating').click()
                expect(peer.locator('#buddyRatingDialog')).to_be_hidden()
                peer.locator('.buddy-tabs [data-buddy-tab="discover"]').click()
                expect(peer.locator('#buddyList')).to_contain_text('5.0')
                peer.locator('#buddyList [data-buddy-user]').click()
                peer.once('dialog', lambda dialog: dialog.accept())
                peer.locator('#buddyBlock').click()
                expect(peer.locator('#buddyChatMsg')).to_contain_text('已加入黑名单')
                peer.locator('.buddy-tabs [data-buddy-tab="discover"]').click()
                expect(peer.locator('#buddyList')).to_contain_text('还没有运动状态')
                peer.locator('[data-page="profile"]').click()
                peer.locator('#loadBlocks').click()
                peer.locator('[data-unblock]').click()
                expect(peer.locator('#buddyBlocks')).to_contain_text('为空')
                peer.locator('[data-page="buddies"]').click()
                expect(peer.locator('#buddyList')).to_contain_text('学校体育馆')
                page.locator('.buddy-tabs [data-buddy-tab="mine"]').click()
                page.locator('#buddyNote').fill('新手友好，自备球拍，一起练习。')
                page.locator('#buddyPublish').click()
                page.locator('#buddyConfirmPublish').click()
                expect(page.locator('#buddyPreviewDialog')).to_be_hidden()
                page.locator('.buddy-tabs [data-buddy-tab="discover"]').click()
                page.locator('#buddyListView').click()
                page.evaluate("document.querySelector('#toast').classList.add('hidden')")
                page.screenshot(path=str(ARTIFACTS / 'mobile-buddies.png'), full_page=True, animations="disabled")
                for width in (360, 390, 430, 1440):
                    page.set_viewport_size({"width":width,"height":844})
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), width
                page.screenshot(path=str(ARTIFACTS / 'desktop-buddies.png'), full_page=True, animations="disabled")
                page.locator('.buddy-tabs [data-buddy-tab="mine"]').click()
                page.once('dialog', lambda dialog: dialog.accept())
                page.locator('#buddyRemove').click()
                expect(page.locator('#buddyFormMsg')).to_contain_text('已撤下')
                peer.reload()
                expect(peer.locator('#buddyList')).to_contain_text('还没有运动状态')
                peer.locator('.buddy-tabs [data-buddy-tab="messages"]').click()
                peer.locator('#buddyChats [data-buddy-chat]').click()
                expect(peer.locator('#buddyMessages')).to_contain_text('体育馆见')
                peer_context.close()
                page.locator('[data-page="home"]').click()
                page.set_viewport_size({"width":1440,"height":1000})
                page.evaluate("window.scrollTo(0,0)")
                page.screenshot(path=str(ARTIFACTS / "desktop-home.png"), full_page=True, animations="disabled")
                page.set_viewport_size({"width":390,"height":844})
                page.locator('[data-page="records"]').click()
                page.locator("#duration").fill("25")
                context.set_offline(True)
                expect(page.locator("#networkBanner")).to_be_visible()
                page.locator("#saveDraft").click()
                expect(page.locator("#recordMsg")).to_contain_text("暂存")
                page.locator("#duration").evaluate("el => el.value = ''")
                page.locator("#restoreDraft").click()
                expect(page.locator("#duration")).to_have_value("25")
                context.set_offline(False)
                page.evaluate("navigator.serviceWorker.ready")
                page.reload()
                expect(page.locator("#appPanel")).to_be_visible()
                expect(page.locator("#reflection")).to_have_value("这周运动后更有精神。")
                context.set_offline(True)
                page.reload()
                expect(page.locator("h1")).to_contain_text("网络回来")
                context.set_offline(False)
                page.goto("http://127.0.0.1:8766/")
                expect(page.locator("#appPanel")).to_be_visible()
                page.locator('[data-page="profile"]').click()
                with page.expect_download() as download:
                    page.locator("#exportButton").click()
                assert download.value.suggested_filename.endswith(".json")
                page.locator("#profileInstall").click()
                expect(page.locator("#installDialog")).to_be_visible()
                page.locator("#closeInstall").click()
                page.locator("#logoutButton").click()
                expect(page.locator("#authPanel")).to_be_visible()
                assert page.evaluate("Object.keys(localStorage).filter(k=>k.startsWith('campus-move-draft:')).length") == 0
                assert not stale_script_requests, stale_script_requests
                assert not errors, errors
                browser.close()
                print("PASS: mobile/desktop layout, registration, record editing, plan adjustment, reflection persistence, XSS, drafts, offline fallback, export, install help, buddy map fallback/retry, two-user private chat and logout")
        finally:
            if os.name == "nt":
                # The Windows venv launcher can own a child Python process.
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True)
            else:
                process.terminate()
            process.wait(timeout=15)
