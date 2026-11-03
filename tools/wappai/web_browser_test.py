"""Run against web_qa_server.py only; artifacts go outside the repository."""
from pathlib import Path
import json, os
from playwright.sync_api import sync_playwright, expect
port=int(os.environ.get('QA_PORT','8876'));BASE=f'http://127.0.0.1:{port}'
OUT=Path.home()/('.cache/wappai-build/web-qa-'+os.environ.get('QA_BROWSER','chrome'));OUT.mkdir(exist_ok=True)
with sync_playwright() as pw:
    browser=pw.webkit.launch(headless=True) if os.environ.get('QA_BROWSER')=='webkit' else pw.chromium.launch(channel='chrome',headless=True,args=['--use-fake-device-for-media-stream','--use-fake-ui-for-media-stream'])
    context=browser.new_context(viewport={'width':1440,'height':1000},permissions=[] if os.environ.get('QA_BROWSER')=='webkit' else ['microphone'])
    page=context.new_page();errors=[]
    page.on('pageerror',lambda error:errors.append(str(error)))
    page.goto(BASE)
    expect(page.locator('#login')).to_be_visible()
    page.locator('#pair-code').fill(Path(f'/tmp/wappai-web-qa-code-{port}').read_text())
    page.locator('#login-form button').click();expect(page.locator('#workspace')).to_be_visible()
    expect(page.locator('#chat-title')).to_have_text('היום שלי')
    assert page.evaluate("document.documentElement.dir")=='rtl'
    page.wait_for_timeout(500);page.screenshot(path=str(OUT/'desktop-light.png'))
    # The actual API handles submit and idempotency; no browser fetch mocks.
    text='בדיקת Web <img src=x onerror=alert(1)>'
    page.locator('#draft').fill(text);page.locator('#send').click()
    expect(page.locator('.message.assistant').last).to_contain_text('קיבלתי: '+text)
    assert page.locator('.message img').count()==0
    expect(page.locator('.message.user').filter(has_text=text)).to_have_count(1)
    page.wait_for_timeout(300)
    page.locator('#new-chat').click();expect(page.locator('.welcome')).to_be_visible()
    page.screenshot(path=str(OUT/'welcome.png'))
    page.locator('#chat-search').fill('היום');page.locator('.session').click();expect(page.locator('#chat-title')).to_have_text('היום שלי');page.locator('#chat-search').fill('')
    if os.environ.get('QA_BROWSER')!='webkit':
        box=page.locator('#mic').bounding_box();page.mouse.move(box['x']+20,box['y']+20);page.mouse.down()
        expect(page.locator('#mic')).to_have_class('icon recording')
        page.wait_for_timeout(850);page.mouse.up()
        expect(page.locator('.message.assistant').last).to_contain_text('הקלטת דפדפן לבדיקה')
        capture=page.evaluate("async()=>await (await fetch('/__qa/capture')).json()")
        assert capture['count']==1 and 16000<capture['bytes']<60000,capture
        expect(page.locator('#mic')).not_to_have_class('icon recording')
    # Ephemeral captions cannot become historical chat messages.
    def emit(body):return page.evaluate("async body=>{const r=await fetch('/__qa/event',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});return r.status}",body)
    emit({'type':'transcript.partial','text':'דיבור בזמן אמת'});expect(page.locator('.live-transcript')).to_have_text('דיבור בזמן אמת')
    emit({'type':'transcript.partial','text':''});expect(page.locator('.live-transcript')).to_have_count(0)
    emit({'type':'device.badge','dev':{'name':'חדר משחקים','on':True},'pending':False});expect(page.locator('#device-badge')).to_contain_text('חדר משחקים')
    page.get_by_role('button',name='הגדרות',exact=True).first.click()
    brightness=page.locator('[data-setting=brightness]');assert brightness.get_attribute('max')=='255'
    page.locator('[data-setting=live_transcription]').check();expect(page.locator('[data-setting=live_transcription]')).to_be_enabled()
    page.locator('#theme').select_option('dark');expect(page.locator('body')).to_have_attribute('data-theme','dark')
    page.screenshot(path=str(OUT/'settings-dark.png'))
    page.locator('#voice-settings').click();expect(page.locator('#panel-title')).to_have_text('קולות ודיבור')
    page.locator('#edge-voice').select_option('he-IL-AvriNeural');page.locator('#save-edge').click();expect(page.locator('#notice')).to_have_text('הקול נשמר')
    page.locator('#search-voices').click();expect(page.locator('#notice')).to_contain_text('לחבר חשבון')
    page.locator('#close-panel').click()
    page.locator('[data-panel=pips]').click();expect(page.locator('.pip-tile')).to_have_count(3)
    page.wait_for_timeout(300);page.screenshot(path=str(OUT/'gallery-dark.png'))
    page.locator('[data-pip=pip]').click();expect(page.locator('#delete-pip')).to_have_count(0)
    page.locator('[data-motion=dizzy]').click();page.wait_for_timeout(400);page.screenshot(path=str(OUT/'spirals.png'))
    page.locator('#back-pips').click();page.locator('#create-pip').click()
    page.locator('#pip-name').fill('דמות לבדיקת ממשק');page.locator('#pip-description').fill('שועל קטן ולבנדר עם צעיף ירוק')
    page.locator('#pip-image').set_input_files(str(Path(__file__).resolve().parents[2]/'server/sim/pixel-0-0.png'))
    expect(page.locator('#reference-preview')).to_be_visible()
    page.locator('#pip-form button').click();expect(page.locator('[data-apply]')).to_be_visible()
    page.screenshot(path=str(OUT/'preview-approval.png'))
    page.locator('[data-apply]').click();expect(page.locator('#jobs')).to_contain_text('יוצר את כל ההבעות')
    page.locator('[data-cancel]').click();expect(page.locator('#jobs')).to_contain_text('בוטלה')
    page.locator('#close-panel').click()
    # Real custom CRUD routes with an inexpensive palette Pip; protected built-ins stay immutable.
    pid=page.evaluate("async()=>{const r=await fetch('/v1/pips',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:'Custom QA',rig:1,color:8450765})});return (await r.json()).id}")
    page.locator('[data-panel=pips]').click();page.locator(f'[data-pip="{pid}"]').click()
    page.locator('#rename-pip').fill('Renamed QA');page.locator('#save-name').click();expect(page.locator(f'[data-pip="{pid}"]')).to_contain_text('Renamed QA')
    page.locator(f'[data-pip="{pid}"]').click();page.locator('#delete-pip').click();page.locator('#confirm-delete').click();expect(page.locator(f'[data-pip="{pid}"]')).to_have_count(0)
    page.locator('#close-panel').click()
    # Force an actual event socket close and verify automatic reconnect without duplicates.
    page.evaluate("async()=>await fetch('/__qa/disconnect',{method:'POST'})")
    expect(page.locator('#connection')).to_contain_text('מתחבר מחדש')
    expect(page.locator('#connection')).not_to_contain_text('מתחבר מחדש',timeout=10000)
    emit({'type':'transcript.partial','text':'אחרי התחברות מחדש'});expect(page.locator('.live-transcript')).to_have_text('אחרי התחברות מחדש')
    emit({'type':'transcript.partial','text':''})
    expect(page.locator('.message.user').filter(has_text=text)).to_have_count(1)
    # Refresh preserves shared conversation and appearance.
    page.reload();expect(page.locator('#workspace')).to_be_visible();expect(page.locator('body')).to_have_attribute('data-theme','dark')
    page.screenshot(path=str(OUT/'desktop-dark.png'))
    # Mobile RTL edge swipe, dialog overflow, long press and persisted hide.
    page.set_viewport_size({'width':390,'height':844});page.reload();expect(page.locator('#toggle-drawer')).to_have_attribute('aria-expanded','false')
    page.evaluate("""()=>{const start=new Event('touchstart');Object.defineProperty(start,'touches',{value:[{clientX:388,clientY:300}]});document.dispatchEvent(start);const end=new Event('touchend');Object.defineProperty(end,'changedTouches',{value:[{clientX:210,clientY:305}]});document.dispatchEvent(end);}""")
    expect(page.locator('#toggle-drawer')).to_have_attribute('aria-expanded','true')
    page.screenshot(path=str(OUT/'mobile-drawer.png'))
    page.locator('#close-drawer').click();page.get_by_role('button',name='הגדרות',exact=True).last.click()
    page.locator('#theme').select_option('light');page.screenshot(path=str(OUT/'mobile-settings.png'));page.locator('#close-panel').click()
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    pet=page.locator('#floating-pip');box=pet.bounding_box();page.mouse.move(box['x']+40,box['y']+40);page.mouse.down();page.wait_for_timeout(500);page.mouse.up();expect(page.locator('#pet-menu')).to_be_visible();page.locator('#hide-pet').click();expect(pet).to_be_hidden();page.reload();expect(pet).to_be_hidden()
    page.screenshot(path=str(OUT/'mobile-chat.png'))
    assert not errors,errors
    # Admin styling remains reachable through the existing admin login mechanism.
    page.goto(BASE+'/admin/login?code='+Path(f'/tmp/wappai-web-qa-admin-{port}').read_text());page.wait_for_timeout(500);page.screenshot(path=str(OUT/'admin-mobile.png'))
    assert page.locator('.web-chat-link').count()==1
    context.close();browser.close()
print('Browser QA passed: login, shared history, text/XSS, captions, badge, settings, voice errors, Pip preview approval/cancel, custom CRUD, built-in protection, RTL mobile swipe, theme, floating Pip and admin styling.')
