"""Avatar recovery across mobile routes using a temporary server and database.

Run: .\.venv\Scripts\python.exe tests/browser_avatar_recovery.py
No production accounts, database, or images are accessed.
"""
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from urllib.request import urlopen

from playwright.sync_api import expect, sync_playwright
import browser_campus_visual as helpers

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:8770"
helpers.BASE = BASE


def wait_until(page, predicate, timeout=10):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return
        page.wait_for_timeout(50)
    raise AssertionError("Expected intercepted avatar request did not arrive")


def decoded(page, selector, timeout=12000):
    page.wait_for_function(
        "selector => {const img=document.querySelector(selector);"
        "return !!img && img.complete && img.naturalWidth>0 && !img.hidden;}",
        arg=selector, timeout=timeout)
    expect(page.locator(selector).first).to_be_visible(timeout=timeout)


def main():
    artifacts = ROOT / "artifacts"
    artifacts.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="avatar-recovery-") as directory:
        directory = Path(directory)
        images = []
        for index, color in enumerate(("#71ab9c", "#6f8bb7", "#c18b68")):
            image = directory / f"avatar-{index}.png"
            helpers.fixture_image(image, color, str(index))
            images.append(image)
        env = dict(os.environ, DATABASE_URL="sqlite:///" + (directory / "test.db").as_posix(),
                   COOKIE_SECURE="false", AI_API_KEY="", REMINDERS_ENABLED="false")
        with (directory / "server.log").open("w", encoding="utf-8") as log:
            process = subprocess.Popen(
                [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8770"],
                cwd=ROOT, env=env, stdout=log, stderr=log)
            try:
                for _ in range(80):
                    if process.poll() is not None:
                        raise RuntimeError("Temporary avatar recovery server stopped")
                    try:
                        with urlopen(BASE + "/", timeout=1):
                            break
                    except Exception:
                        time.sleep(.2)
                else:
                    raise RuntimeError("Temporary server startup timed out")
                with sync_playwright() as pw:
                    browser = pw.chromium.launch(channel="msedge", headless=True)
                    owner, owner_id = helpers.account(browser, "recovery_host_test")
                    peer, peer_id = helpers.account(browser, "recovery_peer_test")
                    for index, context in enumerate((owner, peer)):
                        helpers.success(context.request.put(BASE + "/api/profile/identity", data={
                            "nickname": ("小林 · 测试", "阿青 · 测试")[index], "bio": "临时测试资料"}))
                        helpers.success(context.request.post(BASE + "/api/profile/avatar", multipart={"file": {
                            "name": images[index].name, "mimeType": "image/png", "buffer": images[index].read_bytes()}}))
                    page = owner.new_page()
                    errors, held = [], []
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    policy, requests = {}, {}

                    def intercept(route):
                        uid = int(re.search(r"/users/(\d+)/avatar", route.request.url)[1])
                        requests[uid] = requests.get(uid, 0) + 1
                        mode = policy.get(uid, "normal")
                        if mode == "fail":
                            route.fulfill(status=503, content_type="text/plain", body="temporary avatar failure")
                        elif mode == "hold":
                            held.append(route)
                        else:
                            route.continue_()

                    page.route("**/api/users/*/avatar*", intercept)
                    page.goto(BASE + "/#profile")
                    page.wait_for_function("campus.profile !== null")
                    when = page.evaluate("new Date(Date.now()+86400000).toISOString()")
                    activity = helpers.create_activity(peer, when, "羽毛球", "测试体育馆")
                    chat = helpers.success(owner.request.post(BASE + f"/api/buddies/{peer_id}/chat"))["id"]
                    helpers.success(peer.request.post(BASE + f"/api/buddy-chats/{chat}/messages", data={"body": "测试邀请，明天一起打球。"}))
                    helpers.success(owner.request.post(BASE + f"/api/buddy-chats/{chat}/messages", data={"body": "好的，明天见。"}))

                    def reload_route(route):
                        page.evaluate("route => location.hash=route", route)
                        page.reload()
                        page.wait_for_function("campus.profile !== null")

                    def recover(name, selectors):
                        policy[peer_id] = "normal"
                        page.evaluate("window.dispatchEvent(new Event('online'))")
                        if name != "activity":
                            # An unchanged successful poll must not leave failed avatars stuck.
                            page.evaluate("loadBuddyChats()")
                        for selector in selectors:
                            decoded(page, selector)
                        page.screenshot(path=str(artifacts / f"avatar-recovery-{name}.png"))

                    # A transient failure must recover without changing the identity signature.
                    policy[peer_id] = "fail"
                    requests[peer_id] = 0
                    reload_route("messages")
                    expect(page.locator("#buddyChats")).to_contain_text("阿青 · 测试")
                    # Exhaust every automatic retry first, then recover an unchanged row.
                    wait_until(page, lambda: requests.get(peer_id, 0) >= 4, timeout=20)
                    page.wait_for_timeout(150)
                    recover("list", [f'#buddyChats [data-buddy-chat="{chat}"] img'])

                    policy[peer_id] = "fail"
                    requests[peer_id] = 0
                    reload_route(f"messages/{chat}")
                    expect(page.locator("#buddyMessages")).to_contain_text("测试邀请")
                    wait_until(page, lambda: requests.get(peer_id, 0) >= 2)
                    page.wait_for_timeout(150)
                    recover("chat", ["#buddyChatAvatar img", "#buddyMessages .buddy-message:not(.mine) img"])

                    policy[peer_id] = "fail"
                    requests[peer_id] = 0
                    reload_route("buddies/discover")
                    card = f'#buddyList [data-activity-card="{activity["id"]}"]'
                    expect(page.locator(card)).to_be_visible()
                    page.locator(card).scroll_into_view_if_needed()
                    wait_until(page, lambda: requests.get(peer_id, 0) >= 1)
                    page.wait_for_timeout(200)
                    recover("activity", [card + " .activity-host img"])

                    # Reopening the app during a download outage also recovers on reconnect.
                    policy[owner_id] = "fail"
                    reload_route("profile")
                    expect(page.locator("#retryProfileAvatar")).to_be_visible()
                    policy[owner_id] = "normal"
                    page.evaluate("window.dispatchEvent(new Event('online'))")
                    decoded(page, "#profileAvatarPreview")
                    expect(page.locator("#retryProfileAvatar")).to_be_hidden()

                    # A newly uploaded self avatar remains the current identity across routes.
                    reload_route("profile")
                    decoded(page, "#profileAvatarPreview")
                    policy[owner_id] = "fail"
                    requests[owner_id] = 0
                    page.locator("#profileAvatarFile").set_input_files(str(images[2]))
                    expect(page.locator("#avatarMsg")).to_contain_text("头像已保存")
                    wait_until(page, lambda: requests.get(owner_id, 0) >= 2)
                    expect(page.locator("#profileAvatarFile")).to_be_enabled(timeout=25000)
                    saved = helpers.success(owner.request.get(BASE + "/api/profile"))["avatar_url"]
                    assert saved
                    policy[owner_id] = "normal"
                    page.evaluate("window.dispatchEvent(new Event('online'))")
                    page.wait_for_function("(()=>{const img=document.querySelector('#profileAvatarPreview');return img.complete && img.naturalWidth===512;})()")
                    verified_gets = requests.get(owner_id, 0)
                    page.evaluate("navigate('messages')")
                    decoded(page, "#messageSelfAvatar img")
                    page.locator(f'[data-buddy-chat="{chat}"]').click()
                    decoded(page, "#buddyMessages .mine img")
                    assert requests.get(owner_id, 0) == verified_gets, "Switching pages should reuse the verified self photo"
                    assert helpers.success(owner.request.get(BASE + "/api/profile"))["avatar_url"] == saved

                    # Revoking access while the old image response is pending must win.
                    policy[peer_id] = "hold"
                    old_peer = peer.request.get(BASE + helpers.success(peer.request.get(BASE + "/api/profile"))["avatar_url"]).body()
                    reload_route(f"messages/{chat}")
                    wait_until(page, lambda: bool(held))
                    helpers.success(owner.request.put(BASE + f"/api/buddy-blocks/{peer_id}"))
                    page.evaluate("loadBuddyChats()")
                    page.wait_for_function("buddy.chats.some(chat => chat.identity_hidden)")
                    for route in held:
                        try:
                            route.fulfill(status=200, content_type="image/jpeg", body=old_peer)
                        except Exception:
                            pass  # A correctly aborted fetch may already be closed.
                    held.clear()
                    page.wait_for_timeout(300)
                    expect(page.locator("#buddyChatAvatar img")).to_have_count(0)
                    expect(page.locator("#buddyMessages .buddy-message:not(.mine) img")).to_have_count(0)

                    # Deleting one's avatar invalidates a late image result and message header.
                    policy[owner_id] = "hold"
                    old_owner = owner.request.get(BASE + saved).body()
                    reload_route("profile")
                    wait_until(page, lambda: bool(held))
                    page.locator("#removeProfileAvatar").click()
                    page.wait_for_function("campus.profile && !campus.profile.avatar_url")
                    for route in held:
                        try:
                            route.fulfill(status=200, content_type="image/jpeg", body=old_owner)
                        except Exception:
                            pass
                    held.clear()
                    page.wait_for_timeout(300)
                    expect(page.locator("#profileAvatarPreview")).to_be_hidden()
                    page.evaluate("navigate('messages')")
                    expect(page.locator("#messageSelfAvatar img")).to_have_count(0)
                    assert not helpers.success(owner.request.get(BASE + "/api/profile"))["avatar_url"]
                    assert not errors, errors
                    print("PASS: unchanged-poll and online avatar recovery in lists, chats and activities; uploaded self identity across routes; blocked/deleted identity wins over delayed media")
                    browser.close()
            except Exception:
                log.flush()
                (artifacts / "avatar-recovery-server.log").write_text(
                    (directory / "server.log").read_text(encoding="utf-8", errors="replace"), encoding="utf-8")
                if "page" in locals():
                    try:
                        page.screenshot(path=str(artifacts / "avatar-recovery-failure.png"), full_page=True)
                    except Exception:
                        pass
                raise
            finally:
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True)
                process.wait(timeout=15)


if __name__ == "__main__":
    main()
