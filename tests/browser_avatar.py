"""Avatar display regression tests with temporary users, images and database.

Run from the repository root with Playwright, Pillow and Microsoft Edge installed:
    .\.venv\Scripts\python.exe tests/browser_avatar.py
No production accounts or application database are accessed.
"""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from urllib.request import urlopen

from PIL import Image
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:8768"
PASSWORD = "test-avatar-pass-123"


def success(response):
    assert response.ok, (response.status, response.text())
    return response.json()


def image_visible(page, width=512):
    expect(page.locator("#profileAvatarPreview")).to_be_visible()
    page.wait_for_function(
        "width => {const i=document.querySelector('#profileAvatarPreview');"
        "return i.complete && i.naturalWidth===width;}", arg=width)
    expect(page.locator("#profileAvatarFallback")).to_be_hidden()


def main():
    artifacts = ROOT / "artifacts"
    artifacts.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="avatar-browser-test-") as directory:
        directory = Path(directory)
        first, second = directory / "first.png", directory / "second.png"
        Image.new("RGB", (800, 800), "#45816a").save(first)
        Image.new("RGB", (800, 800), "#d59c6b").save(second)
        env = dict(os.environ, DATABASE_URL="sqlite:///" + (directory / "test.db").as_posix(),
                   COOKIE_SECURE="false", AI_API_KEY="", REMINDERS_ENABLED="false")
        with (directory / "server.log").open("w", encoding="utf-8") as log:
            process = subprocess.Popen(
                [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8768"],
                cwd=ROOT, env=env, stdout=log, stderr=log)
            try:
                for _ in range(80):
                    if process.poll() is not None:
                        raise RuntimeError("Temporary avatar server failed to start")
                    try:
                        with urlopen(BASE + "/", timeout=1):
                            break
                    except Exception:
                        time.sleep(.2)
                else:
                    raise RuntimeError("Temporary avatar server startup timed out")

                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(channel="msedge", headless=True)
                    context = browser.new_context(viewport={"width": 390, "height": 844},
                                                  is_mobile=True, has_touch=True,
                                                  locale="zh-CN", timezone_id="Asia/Shanghai")
                    for name in ("avatar_owner", "avatar_next"):
                        success(context.request.post(BASE + "/api/register", data={"username": name, "password": PASSWORD}))
                    success(context.request.post(BASE + "/api/login", data={"username": "avatar_owner", "password": PASSWORD}))
                    page = context.new_page()
                    errors, posts, held = [], [], []
                    mode = {"value": "once", "gets": 0}
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    page.on("request", lambda request: posts.append(request.url)
                            if request.method == "POST" and request.url.endswith("/api/profile/avatar") else None)

                    def avatar_request(route):
                        mode["gets"] += 1
                        if mode["value"] == "hold":
                            held.append(route)
                        elif mode["value"] == "always" or (mode["value"] == "once" and mode["gets"] == 1):
                            route.fulfill(status=503, content_type="text/plain", body="temporary image load failure")
                        else:
                            route.continue_()
                    page.route("**/api/users/*/avatar*", avatar_request)
                    page.goto(BASE + "/#profile")
                    page.wait_for_function("campus.profile!==null")

                    # One failed GET after a successful POST must recover automatically.
                    page.locator("#profileAvatarFile").set_input_files(str(first))
                    image_visible(page)
                    expect(page.locator("#avatarMsg")).to_contain_text("头像已保存")
                    expect(page.locator("#retryProfileAvatar")).to_be_hidden()
                    assert mode["gets"] >= 2 and len(posts) == 1
                    data = success(context.request.get(BASE + "/api/profile"))
                    saved_image = context.request.get(BASE + data["avatar_url"])
                    assert saved_image.ok and saved_image.headers["content-type"].startswith("image/jpeg")

                    # Persistent GET failure keeps the selected picture and offers a GET-only retry.
                    mode.update(value="always", gets=0)
                    page.locator("#profileAvatarFile").set_input_files(str(second))
                    expect(page.locator("#retryProfileAvatar")).to_be_visible()
                    expect(page.locator("#avatarMsg")).to_contain_text("头像已保存，但图片暂时加载失败")
                    image_visible(page, width=800)
                    data = success(context.request.get(BASE + "/api/profile"))
                    assert data["avatar_url"]
                    post_count = len(posts)
                    mode["value"] = "normal"
                    page.locator("#retryProfileAvatar").click()
                    image_visible(page)
                    expect(page.locator("#retryProfileAvatar")).to_be_hidden()
                    assert len(posts) == post_count == 2, "Retrying display must not upload again"
                    assert success(context.request.get(BASE + "/api/profile"))["avatar_url"] == data["avatar_url"]

                    # A fresh document still obtains the same durable image from the database.
                    page.reload()
                    page.wait_for_function("campus.profile!==null")
                    image_visible(page)
                    assert success(context.request.get(BASE + "/api/profile"))["avatar_url"] == data["avatar_url"]

                    # Reload with unreadable image must explain the failure rather than claim success.
                    mode.update(value="always", gets=0)
                    page.reload()
                    page.wait_for_function("campus.profile!==null")
                    expect(page.locator("#retryProfileAvatar")).to_be_visible()
                    expect(page.locator("#avatarMsg")).to_contain_text("加载失败")
                    expect(page.locator("#profileAvatarPreview")).to_be_hidden()
                    mode["value"] = "normal"
                    page.locator("#retryProfileAvatar").click()
                    image_visible(page)
                    assert len(posts) == 2

                    # Removing an avatar while its old GET is delayed must never restore it.
                    old_image = context.request.get(BASE + data["avatar_url"]).body()
                    mode.update(value="hold", gets=0)
                    page.reload()
                    page.wait_for_function("campus.profile && !!campus.profile.avatar_url")
                    expect(page.locator("#removeProfileAvatar")).to_be_visible()
                    page.wait_for_timeout(100)
                    assert held, "The old image response must be delayed for this test"
                    page.locator("#removeProfileAvatar").click()
                    page.wait_for_function("campus.profile && !campus.profile.avatar_url")
                    for route in held:
                        route.fulfill(status=200, content_type="image/jpeg", body=old_image)
                    held.clear()
                    page.wait_for_timeout(250)
                    expect(page.locator("#profileAvatarPreview")).to_be_hidden()
                    expect(page.locator("#profileAvatarFallback")).to_be_visible()
                    assert not success(context.request.get(BASE + "/api/profile"))["avatar_url"]

                    # A response from the old account cannot appear after logout and new login.
                    success(context.request.post(BASE + "/api/profile/avatar", multipart={
                        "file": {"name": "first.png", "mimeType": "image/png", "buffer": first.read_bytes()}}))
                    page.reload()
                    page.wait_for_function("campus.profile && !!campus.profile.avatar_url")
                    page.wait_for_timeout(100)
                    assert held
                    page.locator("#logoutButton").click()
                    expect(page.locator("#authPanel")).to_be_visible()
                    page.locator("#username").fill("avatar_next")
                    page.locator("#password").fill(PASSWORD)
                    page.locator('#authForm button[type="submit"]').click()
                    expect(page.locator("#appPanel")).to_be_visible()
                    page.evaluate("navigate('profile')")
                    page.wait_for_function("campus.profile!==null")
                    for route in held:
                        route.fulfill(status=200, content_type="image/jpeg", body=old_image)
                    held.clear()
                    page.wait_for_timeout(250)
                    expect(page.locator("#userArea")).to_have_text("avatar_next")
                    expect(page.locator("#profileAvatarPreview")).to_be_hidden()
                    expect(page.locator("#profileAvatarFallback")).to_be_visible()
                    expect(page.locator("#retryProfileAvatar")).to_be_hidden()
                    assert not success(context.request.get(BASE + "/api/profile"))["avatar_url"]
                    assert not errors, errors
                    browser.close()
                    print("PASS: avatar transient retry, saved-preview retention, GET-only retry, persistence, explicit load failure, pending removal and login isolation")
            except Exception:
                log.flush()
                (artifacts / "avatar-browser-server.log").write_text(
                    (directory / "server.log").read_text(encoding="utf-8", errors="replace"), encoding="utf-8")
                if "page" in locals():
                    try:
                        page.screenshot(path=str(artifacts / "avatar-browser-failure.png"), full_page=True)
                    except Exception:
                        pass
                raise
            finally:
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True)
                process.wait(timeout=15)


if __name__ == "__main__":
    main()
