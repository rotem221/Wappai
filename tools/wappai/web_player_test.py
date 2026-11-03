"""Regression for old catalogs and custom atlas spiral rendering, without login or AI."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
root=Path(__file__).resolve().parents[2]
catalog=json.loads((root/'server/sim/pixel-motions.json').read_text())
for character in catalog['characters']:character.pop('dizzyEyes',None)
with sync_playwright() as p:
 b=p.chromium.launch(channel='chrome',headless=True);page=b.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 page.route('**/pixel-motions.json',lambda route:route.fulfill(json=catalog))
 page.route('**/v1/pip-assets/qa/atlas.png',lambda route:route.fulfill(path=str(root/'server/sim/pixel-0-0.png'),content_type='image/png'))
 page.goto('http://127.0.0.1:8876')
 result=page.evaluate('''async()=>{
  const {PipPlayer}=await import('/sim/pip-player.js');const checks=[];
  for(let rig=0;rig<4;rig++){
   const canvas=document.createElement('canvas');canvas.width=canvas.height=192;document.body.append(canvas);
   const player=new PipPlayer(canvas,{rig:rig%3,...(rig===3?{asset_id:'qa'}:{})});player.stop();player.motion='dizzy';player.draw(100);
   await new Promise(resolve=>setTimeout(resolve,200));player.draw(100);const a=canvas.toDataURL();player.draw(600);const b=canvas.toDataURL();
   player.reduced=true;player.draw(100);const c=canvas.toDataURL();player.draw(600);const d=canvas.toDataURL();
   checks.push({rig,rotating:a!==b,reduced:c===d});canvas.remove();
  }return checks;
 }''')
 assert not errors,errors
 assert all(x['rotating'] and x['reduced'] for x in result),result
 page.evaluate("async()=>await fetch('/v1/web/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({legacy_token:'isolated-web-qa-device'})})")
 page.reload();expect(page.locator('#workspace')).to_be_visible()
 page.get_by_role('button',name='הגדרות',exact=True).first.click();page.locator('#voice-settings').click();page.locator('#search-voices').click()
 expect(page.locator('#panel > #notice')).to_contain_text('לחבר חשבון');expect(page.locator('#notice')).to_be_visible()
 assert page.evaluate("(()=>{const n=document.querySelector('#notice'),r=n.getBoundingClientRect();return n.contains(document.elementFromPoint(r.x+r.width/2,r.y+r.height/2));})()")
 b.close()
print('Legacy catalog fallback, custom eye detection, three built-in spirals and Reduce Motion passed.')
