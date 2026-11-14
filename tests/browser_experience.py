"""4.3 mobile flows and visual regression, using only temporary test accounts/data."""
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time
from urllib.request import urlopen

from playwright.sync_api import expect, sync_playwright
import browser_campus_visual as helpers

ROOT = Path(__file__).resolve().parents[1]
BASE = 'http://127.0.0.1:8771'
helpers.BASE = BASE


def main():
    artifacts = ROOT / 'artifacts'
    artifacts.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='experience-v43-') as directory:
        directory = Path(directory)
        database = directory / 'test.db'
        photo, cover = directory / 'avatar.png', directory / 'cover.png'
        helpers.fixture_image(photo, '#589988', 'STUDENT')
        helpers.fixture_image(cover, '#498677', 'COURT', cover=True)
        env = dict(os.environ, DATABASE_URL='sqlite:///' + database.as_posix(), COOKIE_SECURE='false',
                   AI_API_KEY='', REMINDERS_ENABLED='false')
        with (directory / 'server.log').open('w', encoding='utf-8') as log:
            process = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'app.main:app', '--host',
                                        '127.0.0.1', '--port', '8771'], cwd=ROOT, env=env, stdout=log, stderr=log)
            try:
                for _ in range(80):
                    if process.poll() is not None:
                        raise RuntimeError('Temporary server stopped: ' + (directory / 'server.log').read_text(encoding='utf-8'))
                    try:
                        with urlopen(BASE+'/', timeout=1):
                            break
                    except Exception:
                        time.sleep(.2)
                else:
                    raise RuntimeError('Temporary server startup timed out')
                with sync_playwright() as pw:
                    browser = pw.chromium.launch(channel='msedge', headless=True)
                    owner, owner_id = helpers.account(browser, 'experience_owner')
                    peer, peer_id = helpers.account(browser, 'experience_peer')
                    extra, _ = helpers.account(browser, 'experience_extra')
                    for context, name in ((owner, '小林 · 测试'), (peer, '阿青 · 测试')):
                        helpers.success(context.request.put(BASE+'/api/profile/identity', data={'nickname':name, 'bio':'课后一起运动，测试资料'}))
                        helpers.success(context.request.post(BASE+'/api/profile/avatar', multipart={'file': {
                            'name':'avatar.png', 'mimeType':'image/png', 'buffer':photo.read_bytes()}}))
                    page = owner.new_page()
                    errors, repeat_posts = [], []
                    helpers.attach_errors(page, errors)
                    page.on('request', lambda r: repeat_posts.append(r.url) if r.method=='POST' and r.url.endswith('/repeat') else None)

                    def route(value):
                        page.evaluate('value => navigate(value)', value)

                    def shot(name):
                        helpers.snapshot(page, 'experience-v43-'+name+'.png')

                    def close_profile_dialogs():
                        page.evaluate("document.querySelectorAll('dialog[open]').forEach(d=>d.close())")

                    def profile_dialog(name):
                        route('profile')
                        button = page.locator(f'[data-profile-open="{name}"]:visible').first
                        if button.count()==0:
                            page.locator('[data-profile-open="profileSettingsDialog"]:visible').first.click()
                            button = page.locator(f'[data-profile-open="{name}"]:visible').first
                        button.click()
                        expect(page.locator('#'+name)).to_be_visible()

                    page.goto(BASE+'/#home')
                    page.wait_for_function('campus.profile !== null')
                    expect(page.locator('#homeActivityList .campus-empty')).to_be_visible()
                    expect(page.locator('#homeActivityList [data-activity-card]')).to_have_count(0)
                    when = datetime.now(timezone.utc)+timedelta(days=1)
                    group = helpers.create_activity(peer, when.isoformat(), '羽毛球', '体育馆 2 号场 · 测试', 4)
                    pair = helpers.create_activity(peer, (when+timedelta(hours=2)).isoformat(), '跑步', '南苑操场 · 测试')
                    helpers.create_activity(peer, (when+timedelta(hours=4)).isoformat(), '篮球', '东区篮球场 · 测试')
                    helpers.create_activity(extra, (when+timedelta(hours=6)).isoformat(), '乒乓球', '活动中心 · 测试')
                    helpers.success(peer.request.post(BASE+f'/api/activities/{group["id"]}/cover', multipart={'file': {
                        'name':'cover.png','mimeType':'image/png','buffer':cover.read_bytes()}}))
                    # A record six days ago is included even across calendar weeks;
                    # a record eight days ago must not enter the rolling-week total.
                    for days, minutes, sport in ((0,45,'羽毛球'), (1,30,'跑步'), (6,90,'羽毛球'), (8,120,'篮球')):
                        helpers.success(owner.request.post(BASE+'/api/records', data={
                            'exercise_date':(datetime.now()-timedelta(days=days)).date().isoformat(),
                            'exercise_type':sport,'duration':minutes}))
                    page.reload()
                    expect(page.locator('#homeActivityList [data-activity-card]')).to_have_count(3)
                    helpers.visible_image(page, '#homeActivityList .activity-cover img')
                    assert page.locator('#homeActivityList').bounding_box()['y'] < 330
                    expect(page.locator('#homeWeekMinutes')).to_have_text('165')
                    expect(page.locator('#homeWeekDays')).to_have_text('3 个运动日')
                    for width in (360,390,430):
                        helpers.no_overflow(page,width)
                    page.set_viewport_size({'width':390,'height':844})
                    shot('home')

                    route('buddies')
                    expect(page.locator('#buddyList [data-activity-card]')).to_have_count(4)
                    shot('discover')
                    page.locator(f'#buddyList [data-activity-details="{pair["id"]}"]').click()
                    expect(page.locator('#activityDetailTitle')).to_contain_text('跑步')
                    expect(page.locator('#activityDetailContent')).to_contain_text('南苑操场')
                    shot('detail')
                    page.locator('#activityDetailAction').click()
                    expect(page.locator('#buddyConversation')).to_be_visible()
                    expect(page.locator('#buddyChatTitle')).to_have_text('阿青 · 测试')
                    chat_id = page.evaluate('buddy.chatId')
                    assert chat_id
                    route('home')
                    page.locator(f'#homeActivityList [data-activity-details="{group["id"]}"]').click()
                    expect(page.locator('#activityDetailAction')).to_have_text('参加这场运动')
                    page.locator('#activityDetailAction').click()
                    expect(page.locator('#groupChatPanel')).to_be_visible()
                    joined=helpers.success(owner.request.get(BASE+f'/api/activities/{group["id"]}'))
                    assert joined['is_member'] and joined['joined']==2

                    # Publish: preview remains reversible, and reusing a place requires a click.
                    previous=helpers.success(owner.request.post(BASE+'/api/activities', data={
                        'exercise_type':'羽毛球','starts_at':(when+timedelta(days=1)).isoformat(),
                        'location':'上次的场地 · 测试','duration':90,'capacity':2}))
                    route('buddies/mine')
                    page.evaluate('loadOwnBuddy()')
                    page.locator('#buddyNewStatus').click()
                    expect(page.locator('#buddyPlace')).to_have_value('')
                    page.locator('#buddyPlace').fill('我正在写的新地点')
                    page.evaluate('loadOwnBuddy()')
                    expect(page.locator('#buddyPlace')).to_have_value('我正在写的新地点')
                    page.locator('#buddyReusePlace').click()
                    expect(page.locator('#buddyPlace')).to_have_value(previous['location'])
                    expect(page.locator('#buddyDuration')).to_have_value('90')
                    local_future=page.evaluate("(()=>{const d=new Date();d.setDate(d.getDate()+3);return localDate(d)+'T18:00';})()")
                    page.locator('#buddyTime').fill(local_future)
                    page.locator('#buddySport').fill('羽毛球')
                    page.locator('#buddyMoreDetails summary').click()
                    page.locator('#buddyLevel').select_option('新手')
                    page.locator('#buddyNote').fill('测试邀请：请自备球拍，费用当面确认。')
                    page.locator('#buddyCoverFile').set_input_files(str(cover))
                    page.locator('#buddyMoreDetails summary').click()
                    shot('publish')
                    before=len(helpers.success(owner.request.get(BASE+'/api/activities/mine')))
                    page.locator('#buddyPublish').click()
                    expect(page.locator('#buddyPreviewDialog')).to_be_visible()
                    page.locator('#buddyCancelPreview').click()
                    assert len(helpers.success(owner.request.get(BASE+'/api/activities/mine')))==before
                    page.locator('#buddyPublish').click()
                    page.locator('#buddyConfirmPublish').click()
                    expect(page.locator('#buddyPreviewDialog')).to_be_hidden()
                    after=helpers.success(owner.request.get(BASE+'/api/activities/mine'))
                    assert len(after)==before+1 and any(a['cover_url'] for a in after)

                    # Completing the old pair is a temporary-data fixture; the UI must invite anew.
                    meeting=helpers.success(owner.request.post(BASE+'/api/meetups', data={
                        'chat_id':chat_id,'exercise_type':'跑步','starts_at':(when+timedelta(days=5)).isoformat(),
                        'duration':60,'location':'南苑操场 · 测试'}))
                    meeting=helpers.success(peer.request.post(BASE+f'/api/meetups/{meeting["id"]}/decision', data={'action':'accept','revision':meeting['revision']}))
                    with sqlite3.connect(database) as db:
                        db.execute('UPDATE meetups SET starts_at=? WHERE id=?', ((datetime.now(timezone.utc)-timedelta(hours=3)).replace(tzinfo=None).isoformat(' '),meeting['id']))
                    db.close()
                    for context in (owner,peer):
                        meeting=helpers.success(context.request.post(BASE+f'/api/meetups/{meeting["id"]}/decision', data={'action':'attend','revision':meeting['revision']}))
                    assert meeting['state']=='completed'
                    route('buddies/appointments')
                    repeat_button=page.locator(f'#meetupList [data-repeat-meetup="{meeting["id"]}"]')
                    repeat_button.click()
                    expect(page.locator('#repeatPlace')).to_have_value(meeting['location'])
                    expect(page.locator('#repeatSport')).to_have_text('跑步')
                    page.locator('#repeatMeetupDialog [data-close-dialog]').last.click()
                    assert not repeat_posts
                    repeat_button.click()
                    repeat_future=page.evaluate("(()=>{const d=new Date();d.setDate(d.getDate()+7);return localDate(d)+'T18:00';})()")
                    page.locator('#repeatTime').fill(repeat_future)
                    page.locator('#repeatSubmit').click()
                    expect(page.locator('#repeatMeetupDialog')).to_be_hidden()
                    assert len(repeat_posts)==1
                    all_meetings=helpers.success(owner.request.get(BASE+'/api/meetups'))
                    repeated=next(m for m in all_meetings if m['kind']=='pair' and m['id']!=meeting['id'])
                    assert repeated['state']=='pending' and not any(p['attended'] for p in repeated['members'])
                    assert sorted(p['status'] for p in repeated['members'])==['accepted','pending']
                    assert helpers.success(owner.request.get(BASE+f'/api/meetups/{meeting["id"]}'))['state']=='completed'

                    route('profile')
                    page.evaluate('refreshCampusStats()')
                    helpers.visible_image(page, '#profileAvatarPreview')
                    expect(page.locator('#page-profile')).to_contain_text('165')
                    expect(page.locator('#page-profile')).to_contain_text('羽毛球')
                    for width in (360,390,430):
                        helpers.no_overflow(page,width)
                    page.set_viewport_size({'width':390,'height':844})
                    shot('profile')
                    profile_dialog('identityEditDialog')
                    page.locator('#profileNickname').fill('小林的新昵称 · 测试')
                    page.locator('#identitySave').click()
                    expect(page.locator('#identityMsg')).to_contain_text('已保存')
                    close_profile_dialogs()
                    expect(page.locator('#userArea')).to_have_text('小林的新昵称 · 测试')
                    for theme in ('night','ocean','forest'):
                        profile_dialog('profileThemeDialog')
                        page.locator(f'[data-theme-choice="{theme}"]').click()
                        expect(page.locator('#themeMsg')).to_contain_text('已保存')
                        close_profile_dialogs()
                        route('home')
                        for width in (360,390,430):
                            helpers.no_overflow(page,width)
                        if theme=='night':
                            page.set_viewport_size({'width':390,'height':844})
                            shot('night')

                    route('records')
                    page.locator('#recordInsights > summary').click()
                    expect(page.locator('#chart')).to_be_visible()
                    expect(page.locator('#reviewText')).to_contain_text('165')
                    page.locator('#reflectionDetails summary').click()
                    expect(page.locator('#reflectionForm')).to_be_visible()

                    # Leaving the account clears its details and its visible summaries.
                    profile_dialog('profileSettingsDialog')
                    page.locator('#logoutButton').click()
                    expect(page.locator('#authPanel')).to_be_visible()
                    page.locator('#username').fill('experience_extra')
                    page.locator('#password').fill(helpers.PASSWORD)
                    page.locator('#authForm [type=submit]').click()
                    expect(page.locator('#appPanel')).to_be_visible()
                    page.wait_for_function('campus.profile !== null')
                    route('profile')
                    expect(page.locator('#userArea')).to_have_text('experience_extra')
                    expect(page.locator('#profileAvatarPreview')).to_be_hidden()
                    assert '小林的新昵称' not in page.locator('#page-profile').inner_text()
                    route('home')
                    expect(page.locator('#homeWeekMinutes')).to_have_text('0')
                    assert not errors,errors
                    browser.close()
                    print('PASS: 4.3 home/detail/join/publish/reuse/profile/insights/repeat/identity isolation; mobile widths and themes')
            except Exception:
                log.flush()
                (artifacts/'experience-v43-server.log').write_text((directory/'server.log').read_text(encoding='utf-8',errors='replace'),encoding='utf-8')
                if 'page' in locals():
                    try:
                        page.screenshot(path=str(artifacts/'experience-v43-failure.png'),full_page=True)
                    except Exception:
                        pass
                raise
            finally:
                subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True)
                process.wait(timeout=15)


if __name__=='__main__':
    main()
