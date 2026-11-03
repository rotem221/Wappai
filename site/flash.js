import {firmware} from './release-config.js';
import {verifyFirmware} from './flash-integrity.js';
const status = document.querySelector('#flash-status');
const confirm = document.querySelector('#board-confirm');
const holder = document.querySelector('#installer');
const retry = document.querySelector('#flash-retry');
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
  verified = false; sync(); retry.hidden = true;
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
    await import('./vendor/esp-web-tools/install-button.js');
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
    holder.replaceChildren();
    blobs.splice(0).forEach(url => URL.revokeObjectURL(url));
    status.textContent = 'לא ניתן לאמת או לטעון את הקושחה כרגע. לא נפתח חיבור למכשיר ולא בוצעה צריבה. נסו שוב.';
    retry.hidden = false;
    console.error('Wappai installer preparation failed:', error.message);
  }
}
retry.addEventListener('click', prepare);
window.addEventListener('pagehide', event => {
  // Preserve blob URLs for a restored back/forward-cache page.
  if (!event.persisted) blobs.splice(0).forEach(url => URL.revokeObjectURL(url));
});
prepare();
