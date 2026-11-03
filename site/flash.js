import {firmwareForBoard,boardNames} from './release-config.js';
import {verifyFirmware} from './flash-integrity.js';
const status = document.querySelector('#flash-status');
const confirm = document.querySelector('#board-confirm');
const holder = document.querySelector('#installer');
const retry = document.querySelector('#flash-retry');
const boardSelect=document.querySelector('#firmware-board');
const requestedBoard=new URL(location.href).searchParams.get('board') || 'ws-s3-175c';
if(!Object.hasOwn(boardNames,requestedBoard)) {
  const option=new Option('דגם לא מזוהה — ההתקנה חסומה',requestedBoard);boardSelect.add(option);
}
boardSelect.value=requestedBoard;
let attempt=0;
let verified = false;
const blobs = [];
function sync() {
  holder.hidden = !verified || !confirm.checked;
}
confirm.addEventListener('change', sync);
holder.addEventListener('click', e => {
  if (!verified || !confirm.checked) { e.preventDefault(); e.stopImmediatePropagation(); }
}, true);
async function prepare() {
  const currentAttempt=++attempt;
  verified = false; sync(); retry.hidden = true;holder.replaceChildren();confirm.checked=false;
  blobs.splice(0).forEach(url=>URL.revokeObjectURL(url));
  const firmware=firmwareForBoard(boardSelect.value);
  if(!firmware){confirm.disabled=true;status.textContent='אין קושחה מאומתת להפצה עבור הדגם שבחרתם. ההתקנה חסומה — אין לצרוב קושחה של דגם אחר.';return;}
  const policy = document.permissionsPolicy || document.featurePolicy;
  if (!window.isSecureContext || !('serial' in navigator) || (policy && !policy.allowsFeature('serial'))) {
    status.textContent = 'לצריבה, פתחו את העמוד ב־Chrome או Edge במחשב וחברו את המכשיר ב־USB. צריבה אינה זמינה ב־Safari או באייפון. נדרש חיבור HTTPS והרשאת Serial בדפדפן.';
    confirm.disabled = true;
    return;
  }
  confirm.disabled = false;
  status.textContent = 'מכינים ובודקים את הקושחה…';
  try {
    const response = await fetch(firmware.path, {cache: 'no-cache'});
    if (!response.ok) throw new Error(`Firmware HTTP ${response.status}`);
    const bytes = await response.arrayBuffer();
    await verifyFirmware(bytes, firmware);
    if(currentAttempt!==attempt)return;
    await import('./vendor/esp-web-tools/install-button.js');
    if(currentAttempt!==attempt)return;
    // Install exactly the verified bytes, without re-fetching a mutable remote file.
    const binaryURL = URL.createObjectURL(new Blob([bytes], {type:'application/octet-stream'}));
    blobs.push(binaryURL);
    const manifest = {
      name: 'Wappai 1.75C', version: firmware.version,
      new_install_prompt_erase: true, new_install_improv_wait_time: 0,
      builds: [{chipFamily: 'ESP32-S3', parts: [{path: binaryURL, offset: 0}]}],
    };
    const manifestURL = URL.createObjectURL(new Blob([JSON.stringify(manifest)], {type:'application/json'}));
    blobs.push(manifestURL);
    const installer = document.createElement('esp-web-install-button');
    installer.manifest = manifestURL;
    installer.innerHTML = '<button class="primary flash-connect" slot="activate">חיבור המכשיר וצריבה <span aria-hidden="true">↗</span></button>';
    holder.replaceChildren(installer);
    verified = true; sync();
    status.textContent = 'הקושחה אומתה ומוכנה. אשרו את הדגם והגיבוי כדי לחבר את המכשיר.';
  } catch (error) {
    if(currentAttempt!==attempt)return;
    holder.replaceChildren();
    blobs.splice(0).forEach(url => URL.revokeObjectURL(url));
    status.textContent = 'לא ניתן לאמת או לטעון את הקושחה כרגע. לא נפתח חיבור למכשיר ולא בוצעה צריבה. נסו שוב.';
    retry.hidden = false;
    console.error('Wappai installer preparation failed:', error.message);
  }
}
retry.addEventListener('click', prepare);
boardSelect.addEventListener('change',()=>{document.querySelector('#release-status').textContent='';prepare();});
const checkReleases=document.querySelector('#check-releases');
checkReleases.addEventListener('click',async()=>{
 const output=document.querySelector('#release-status'),board=boardSelect.value;checkReleases.disabled=true;output.textContent='בודק את קטלוג הגרסאות ב־GitHub…';
 try {
  const response=await fetch('https://raw.githubusercontent.com/rotem221/Wappai/main/release/firmware-catalog.json',{cache:'no-cache',signal:AbortSignal.timeout(15000)});
  if(!response.ok)throw Error('Catalog unavailable');const catalog=await response.json();
  if(board!==boardSelect.value)return;
  if(catalog.schema_version!==1 || catalog.repository!=='rotem221/Wappai')throw Error('Invalid catalog');
  const target=catalog.boards.find(x=>x.id===board),local=firmwareForBoard(board);
  if(target?.status!=='available'||!target.release){output.textContent='טרם פורסמה קושחה מאומתת לדגם הזה.';return;}
  if(target.release.sha256===local?.sha256){output.textContent='המתקין מציע את הגרסה האחרונה שפורסמה לדגם: '+target.release.package_version;return;}
  output.textContent='פורסמה גרסה אחרת בקטלוג. יש לעיין בפרטי השחרור; לא הוחלף קובץ ההתקנה אוטומטית.';
 } catch {if(board===boardSelect.value)output.textContent='לא ניתן לבדוק עדכונים כרגע. לא שונה קובץ הקושחה.';}
 finally{checkReleases.disabled=false;}
});
window.addEventListener('pagehide', event => {
  // Preserve blob URLs for a restored back/forward-cache page.
  if (!event.persisted) blobs.splice(0).forEach(url => URL.revokeObjectURL(url));
});
prepare();
