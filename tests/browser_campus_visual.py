"""Campus identity, image uploads and mobile discovery in a temporary database.

Run from the repository root with Playwright, Pillow and Microsoft Edge installed:
    .\.venv\Scripts\python.exe tests/browser_campus_visual.py
All accounts, images and activities created here belong only to the temporary server.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from urllib.request import urlopen

from PIL import Image, ImageDraw
from playwright.sync_api import expect, sync_playwright


ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"
BASE = "http://127.0.0.1:8767"
PASSWORD = "test-pass-123"


def fixture_image(path, color, label, cover=False):
    """Clearly synthetic test artwork, not a photograph of a real student or venue."""
    size = (1200, 720) if cover else (640, 640)
    image = Image.new("RGB", size, color)
    draw = ImageDraw.Draw(image)
    if cover:
        draw.rectangle((130, 90, 1070, 630), outline="white", width=7)
        draw.line((600, 90, 600, 630), fill="white", width=7)
        draw.line((130, 360, 1070, 360), fill="white", width=5)
    else:
        draw.ellipse((190, 100, 450, 360), fill="#f9dbbc")
        draw.rounded_rectangle((120, 360, 520, 650), radius=160, fill="#fff7e8")
    draw.rectangle((20, 20, 235, 65), fill="#20362d")
    draw.text((32, 35), "TEST FIXTURE - " + label, fill="white")
    image.save(path, format="PNG")


def success(response):
    assert response.ok, (response.status, response.text())
    return response.json()


def account(browser, name):
    context = browser.new_context(
        viewport={"width": 390, "height": 844}, device_scale_factor=1,
        is_mobile=True, has_touch=True, locale="zh-CN", timezone_id="Asia/Shanghai")
    credentials = {"username": name, "password": PASSWORD}
    success(context.request.post(BASE + "/api/register", data=credentials))
    success(context.request.post(BASE + "/api/login", data=credentials))
    return context, success(context.request.get(BASE + "/api/me"))["id"]


def attach_errors(page, errors):
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("dialog", lambda dialog: dialog.accept())


def visible_image(page, selector):
    expect(page.locator(selector)).to_be_visible()
    page.wait_for_function(
        "selector => {const image=document.querySelector(selector);return image && image.complete && image.naturalWidth>0;}",
        arg=selector)


def profile(page, context, nickname, bio, image):
    page.goto(BASE + "/#profile")
    expect(page.locator("#appPanel")).to_be_visible()
    page.wait_for_function("campus.profile !== null")
    page.locator("#profileNickname").fill(nickname)
    page.locator("#profileBio").fill(bio)
    page.locator("#identitySave").click()
    expect(page.locator("#identityMsg")).to_contain_text("已")
    page.locator("#profileAvatarFile").set_input_files(str(image))
    page.wait_for_function("campus.profile && !!campus.profile.avatar_url")
    visible_image(page, "#profileAvatarPreview")
    data = success(context.request.get(BASE + "/api/profile"))
    assert data["nickname"] == nickname and data["bio"] == bio
    assert data["avatar_url"]
    assert context.request.get(BASE + data["avatar_url"]).ok
    return data


def create_activity(context, when, sport, place, capacity=2):
    return success(context.request.post(BASE + "/api/activities", data={
        "exercise_type": sport, "starts_at": when, "location": place,
        "duration": 60, "capacity": capacity, "level": "新手",
        "note": "临时数据库中的自动化测试活动。"}))


def open_page(page, section):
    # A new navigation exercises the normal authenticated bootstrap and server data.
    page.goto(BASE + "/#" + section)
    expect(page.locator("#appPanel")).to_be_visible()


def snapshot(page, name, full_page=False):
    page.evaluate("document.querySelector('#toast')?.classList.add('hidden')")
    page.evaluate("document.querySelector('#messageBanner')?.classList.add('hidden')")
    page.evaluate("window.scrollTo(0,0)")
    page.screenshot(path=str(ARTIFACTS / name), full_page=full_page, animations="disabled")


def no_overflow(page, width):
    page.set_viewport_size({"width": width, "height": 844})
    page.evaluate("window.scrollTo(0,0)")
    assert page.evaluate("document.documentElement.scrollWidth<=innerWidth"), width


def main():
    ARTIFACTS.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="campus-visual-test-") as directory:
        directory = Path(directory)
        avatar_a, avatar_b, cover = (directory / name for name in ("avatar-a.png", "avatar-b.png", "court.png"))
        fixture_image(avatar_a, "#71ab9c", "HOST")
        fixture_image(avatar_b, "#6f8bb7", "GUEST")
        fixture_image(cover, "#258a79", "COURT", cover=True)
        env = dict(os.environ, DATABASE_URL="sqlite:///" + (directory / "test.db").as_posix(),
                   COOKIE_SECURE="false", AI_API_KEY="", REMINDERS_ENABLED="false")
        with (directory / "server.log").open("w", encoding="utf-8") as log:
            process = subprocess.Popen(
                [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8767"],
                cwd=ROOT, env=env, stdout=log, stderr=log)
            try:
                for _ in range(80):
                    if process.poll() is not None:
                        raise RuntimeError("Temporary browser-test server failed to start")
                    try:
                        with urlopen(BASE + "/", timeout=1):
                            break
                    except Exception:
                        time.sleep(0.2)
                else:
                    raise RuntimeError("Temporary browser-test server startup timed out")

                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(channel="msedge", headless=True)
                    owner_context, owner_id = account(browser, "visual_host_test")
                    guest_context, guest_id = account(browser, "visual_guest_test")
                    outsider_context, _ = account(browser, "other_school_test")
                    errors = []
                    owner, guest = owner_context.new_page(), guest_context.new_page()
                    attach_errors(owner, errors)
                    attach_errors(guest, errors)
                    host_profile = profile(owner, owner_context, "阿青 · 测试", "羽毛球新手，欢迎课后一起运动。", avatar_a)
                    profile(guest, guest_context, "小林 · 测试", "喜欢跑步，也想认识同校球友。", avatar_b)
                    owner.reload()
                    expect(owner.locator("#profileNickname")).to_have_value("阿青 · 测试")
                    visible_image(owner, "#profileAvatarPreview")
                    snapshot(owner, "campus-v5-profile.png", full_page=True)

                    tomorrow = owner.evaluate("(()=>{const d=new Date();d.setDate(d.getDate()+1);return localDate(d);})()")
                    # Publish the first cover through the actual mobile form.
                    open_page(owner, "buddies/mine")
                    owner.locator("#buddySport").fill("羽毛球")
                    owner.locator("#buddyTime").fill(tomorrow + "T10:00")
                    owner.locator("#buddyPlace").fill("测试体育馆 2 号场")
                    owner.locator("#buddyCapacity").fill("3")
                    owner.locator("#buddyLevel").select_option("新手")
                    owner.locator("#buddyCoverFile").set_input_files(str(cover))
                    visible_image(owner, "#buddyCoverPreview")
                    owner.locator("#buddyPublish").click()
                    owner.locator("#buddyConfirmPublish").click()
                    expect(owner.locator("#buddyPreviewDialog")).to_be_hidden()
                    expect(owner.locator("#buddyFormMsg")).to_contain_text("已公开")
                    activities = success(owner_context.request.get(BASE + "/api/activities/mine"))
                    assert len(activities) == 1
                    group = activities[0]
                    assert group["cover_url"] and group["avatar_url"] == host_profile["avatar_url"]
                    assert owner_context.request.get(BASE + group["cover_url"]).ok
                    pair = create_activity(owner_context, tomorrow + "T18:00:00+08:00", "跑步", "测试操场")
                    success(outsider_context.request.put(BASE + "/api/profile", data={"school": "另一所测试大学", "theme": "forest"}))
                    create_activity(outsider_context, tomorrow + "T12:00:00+08:00", "外校足球测试", "外校测试场地", capacity=4)

                    open_page(guest, "home")
                    expect(guest.locator("#homeActivityList")).to_contain_text("羽毛球")
                    expect(guest.locator("#homeActivityList")).to_contain_text("阿青 · 测试")
                    expect(guest.locator("#homeActivityList")).not_to_contain_text("外校足球测试")
                    group_card = guest.locator("#homeActivityList article").filter(has_text="羽毛球")
                    expect(group_card.locator(f'img[src="{group["cover_url"]}"]')).to_be_visible()
                    expect(group_card.locator(f'img[src="{host_profile["avatar_url"]}"]').first).to_be_visible()
                    visible_image(guest, f'#homeActivityList img[src="{group["cover_url"]}"]')
                    first_box = guest.locator("#homeActivityList article").first.bounding_box()
                    assert first_box and first_box["y"] < 600, first_box
                    snapshot(guest, "campus-v5-home.png")

                    # The homepage's private-chat button must target the card owner.
                    guest.locator(f'#homeActivityList [data-home-chat="{owner_id}"]').click()
                    expect(guest.locator("#buddyConversation")).to_be_visible()
                    guest.locator("#buddyMessage").fill("这是临时校园活动测试消息，一起跑步吧。")
                    guest.locator("#buddySend").click()
                    expect(guest.locator("#buddyMessages")).to_contain_text("临时校园活动测试消息")
                    chats = success(guest_context.request.get(BASE + "/api/buddy-chats"))
                    assert len(chats) == 1 and chats[0]["user_id"] == owner_id

                    # Join a group from the homepage, then verify the confirmed event stays above recommendations.
                    open_page(guest, "home")
                    guest.locator(f'#homeActivityList [data-home-join="{group["id"]}"]').click()
                    expect(guest.locator("#groupChatPanel")).to_be_visible()
                    expect(guest.locator("#meetupDetail")).to_contain_text("2/3")
                    open_page(guest, "home")
                    expect(guest.locator("#nextMeetup")).to_contain_text("羽毛球")
                    expect(guest.locator("#homeActivityList")).to_contain_text("羽毛球")
                    assert guest.locator("#nextMeetupCard").bounding_box()["y"] < guest.locator("#homeActivityList").bounding_box()["y"]

                    # Filters are drafts until Apply; Cancel restores all previous values.
                    open_page(guest, "buddies")
                    expect(guest.locator("#buddyList")).to_contain_text("跑步")
                    guest.locator("#openBuddyFilters").click()
                    expect(guest.locator("#buddyFilterDialog")).to_be_visible()
                    guest.locator(f'[data-filter-date="{tomorrow}"]').click()
                    guest.locator('[data-period="afternoon"]').click()
                    guest.locator("#closeBuddyFilters").click()
                    expect(guest.locator("#buddyFilterDialog")).to_be_hidden()
                    expect(guest.locator("#buddyTimeFilter")).to_have_value("")
                    expect(guest.locator("#buddyPeriodFilter")).to_have_value("")
                    expect(guest.locator("#buddyList")).to_contain_text("跑步")
                    guest.locator("#openBuddyFilters").click()
                    guest.locator(f'[data-filter-date="{tomorrow}"]').click()
                    guest.locator('[data-period="afternoon"]').click()
                    guest.locator("#applyBuddyFilters").click()
                    expect(guest.locator("#buddyList")).to_contain_text("没有符合条件")
                    guest.locator("#openBuddyFilters").click()
                    guest.locator("#resetBuddyFilters").click()
                    guest.locator("#applyBuddyFilters").click()
                    expect(guest.locator("#buddyList")).to_contain_text("羽毛球")
                    guest.locator('[data-filter-sport="羽毛球"]').click()
                    expect(guest.locator("#buddyList")).not_to_contain_text("跑步")
                    expect(guest.locator("#buddyList")).to_contain_text("阿青 · 测试")
                    snapshot(guest, "campus-v5-discovery.png")
                    for width in (360, 390, 430):
                        no_overflow(guest, width)
                        card = guest.locator("#buddyList article").first.bounding_box()
                        assert card and card["y"] < 500, (width, card)

                    guest.set_viewport_size({"width": 390, "height": 844})
                    for theme in ("night", "ocean", "lilac", "forest"):
                        open_page(guest, "profile")
                        guest.locator(f'[data-theme-choice="{theme}"]').click()
                        expect(guest.locator("#themeMsg")).to_contain_text("已保存")
                        open_page(guest, "buddies")
                        expect(guest.locator("html")).to_have_attribute("data-theme", theme)
                        expect(guest.locator("#buddyList")).to_contain_text("羽毛球")
                        assert guest.evaluate("document.documentElement.scrollWidth<=innerWidth")
                        if theme == "night":
                            snapshot(guest, "campus-v5-night.png")

                    # Public identity is text, including HTML-looking input, and long names fit mobile cards.
                    attack = '<img src=x onerror=alert(1)>'
                    success(owner_context.request.put(BASE + '/api/profile/identity', data={
                        'nickname': attack, 'bio': '<svg onload=alert(1)>测试简介</svg>'}))
                    open_page(guest, 'home')
                    expect(guest.locator('#homeActivityList')).to_contain_text(attack)
                    assert guest.locator('#homeActivityList img[src="x"]').count() == 0
                    assert guest.locator('#homeActivityList svg[onload]').count() == 0
                    long_name = '热爱校园运动的同学' * 3
                    success(owner_context.request.put(BASE + '/api/profile/identity', data={
                        'nickname': long_name, 'bio': '期待一起运动' * 25}))
                    open_page(guest, 'buddies')
                    expect(guest.locator('#buddyList')).to_contain_text(long_name)
                    for width in (360, 390, 430):
                        no_overflow(guest, width)
                    success(owner_context.request.put(BASE + '/api/profile/identity', data={
                        'nickname': '阿青 · 测试', 'bio': '羽毛球新手，欢迎课后一起运动。'}))

                    # Removing an image must not remove the underlying identity or activity.
                    open_page(owner, "profile")
                    owner.locator("#removeProfileAvatar").click()
                    owner.wait_for_function("campus.profile && !campus.profile.avatar_url")
                    data = success(owner_context.request.get(BASE + "/api/profile"))
                    assert not data["avatar_url"] and data["nickname"] == "阿青 · 测试"
                    open_page(owner, "buddies/mine")
                    owner.locator(f'[data-edit-activity="{group["id"]}"]').click()
                    visible_image(owner, "#buddyCoverPreview")
                    owner.locator("#buddyCoverRemove").click()
                    expect(owner.locator("#buddyCoverPreview")).to_be_hidden()
                    owner.locator("#buddyPublish").click()
                    owner.locator("#buddyConfirmPublish").click()
                    expect(owner.locator("#buddyPreviewDialog")).to_be_hidden()
                    remaining = success(owner_context.request.get(BASE + "/api/activities/mine"))
                    assert len(remaining) == 2
                    assert not next(row for row in remaining if row["id"] == group["id"])["cover_url"]

                    # A cover upload failure after publication must retry the same activity.
                    failed_once = {"value": False}
                    def fail_first_cover(route):
                        if route.request.method == "POST" and not failed_once["value"]:
                            failed_once["value"] = True
                            route.fulfill(status=503, content_type="application/json", body=json.dumps({"detail": "测试图片上传暂时失败"}))
                        else:
                            route.continue_()
                    owner.route("**/api/activities/*/cover", fail_first_cover)
                    owner.locator("#buddyNewStatus").click()
                    owner.locator("#buddySport").fill("篮球")
                    owner.locator("#buddyTime").fill(tomorrow + "T20:00")
                    owner.locator("#buddyPlace").fill("测试篮球场")
                    owner.locator("#buddyCoverFile").set_input_files(str(cover))
                    owner.locator("#buddyPublish").click()
                    owner.locator("#buddyConfirmPublish").click()
                    expect(owner.locator("#buddyPreviewMsg")).to_contain_text("已发布")
                    assert len(success(owner_context.request.get(BASE + "/api/activities/mine"))) == 3
                    owner.locator("#buddyConfirmPublish").click()
                    expect(owner.locator("#buddyPreviewDialog")).to_be_hidden()
                    final = success(owner_context.request.get(BASE + "/api/activities/mine"))
                    assert len(final) == 3
                    assert next(row for row in final if row["exercise_type"] == "篮球")["cover_url"]
                    assert failed_once["value"]
                    assert not errors, errors
                    browser.close()
                    print("PASS: mobile identity/avatar/cover upload and removal, real school activity feed, homepage chat/join, pinned meeting, draft filters, theme layouts and safe cover retry")
            except Exception:
                # Preserve only this temporary fixture's diagnostics for layout failures.
                log.flush()
                (ARTIFACTS / 'campus-visual-server.log').write_text(
                    (directory / 'server.log').read_text(encoding='utf-8', errors='replace'), encoding='utf-8')
                for label in ('owner', 'guest'):
                    active_page = locals().get(label)
                    if active_page is not None:
                        try:
                            active_page.screenshot(path=str(ARTIFACTS / f'campus-visual-failure-{label}.png'), full_page=True)
                        except Exception:
                            pass
                raise
            finally:
                if os.name == "nt":
                    subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True)
                else:
                    process.terminate()
                process.wait(timeout=15)


if __name__ == "__main__":
    main()
