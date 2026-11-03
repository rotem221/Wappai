// Same authenticated library as native iOS. No recording starts on page load.
export function meetingLibrary({api,panel,esc,notice}) {
  let poll;
  const dialog=document.querySelector('#panel');
  dialog.addEventListener('close',()=>clearInterval(poll),{once:true});
  const stateName=s=>({recording:'מקליט',processing:'מעבד',transcribed:'תומלל',done:'מוכן',audio_only:'הקלטה ללא תמלול',interrupted:'נקטע',summary_unavailable:'הסיכום אינו זמין',processing_failed:'העיבוד נכשל — ההקלטה נשמרה'}[s]||s);
  async function list(){
    clearInterval(poll);
    const data=await api('/v1/meetings'),c=data.capacity;
    panel('פגישות',`<div id="meeting-library"><div class="device-card"><h3>הקלטה ותמלול במכשיר שלך</h3><p>כרטיס זיכרון: ${data.device_storage?.status==="no_slot"?"אין חריץ בדגם הזה":data.device_storage?.sd_present?"זוהה":data.device_storage?.sd_supported?"לא נמצא כרטיס קריא":"המכשיר לא דיווח"}</p><p>זמן זמין משוער: <strong>${Math.floor(Math.min(c.remaining_seconds,c.max_session_seconds)/60)} דקות</strong></p><progress style="width:100%" value="${c.used_bytes}" max="${c.quota_bytes}"></progress><p>${c.cloud_configured?'ארכיון ענן מוגדר; העלאות שנכשלות נשמרות בשרת לניסיון חוזר.':'הקלטות נשמרות בשרת שלך. ארכיון ענן אינו מוגדר.'}</p><p>ללא כרטיס זיכרון, ניתוק רשת מוגבל למאגר זמני של כ־98 שניות. משך ההקלטה תלוי גם בסוללה ובקיבולת השרת.</p></div><div class="actions"><button class="primary" id="meeting-control">${data.recording?'סיום הקלטה':'הקלטת פגישה'}</button><button class="secondary" id="meeting-refresh">רענון</button></div><p id="meeting-progress" role="status"></p><div id="meeting-consent"></div><div>${data.items.length?data.items.map(m=>`<button class="setting-row" style="width:100%;text-align:right" data-meeting="${esc(m.id)}"><span><strong>${esc(m.title)}</strong><br>${esc(m.started.slice(0,16).replace("T"," "))} · ${m.minutes} דקות · ${esc(stateName(m.state))}</span><span>‹</span></button>`).join(''):'<p>פגישות שתקליטו יופיעו כאן.</p>'}</div></div>`);
    poll=setInterval(async()=>{
      if(!dialog.open || !document.querySelector('#meeting-library')){clearInterval(poll);return}
      try{const fresh=await api('/v1/meetings');const active=fresh.items.find(m=>m.state==='recording');
        document.querySelector('#meeting-progress').textContent=active?`מוקלט: ${Math.floor(active.seconds||active.minutes*60)} שניות מתוך ${Math.floor(Math.min(fresh.capacity.max_session_seconds,fresh.capacity.remaining_seconds+(active.seconds||active.minutes*60))/60)} דקות לכל היותר`:'';
        if(fresh.recording!==data.recording && !document.querySelector('#meeting-confirm'))await list();
      }catch{/* Keep existing view while temporarily offline. */}
    },5000);
    document.querySelector('#meeting-refresh').onclick=()=>list().catch(e=>notice(e.message));
    document.querySelector('#meeting-control').onclick=async()=>{
      if(data.recording){try{await api('/v1/meetings/stop',{});notice('בקשת סיום נשלחה למכשיר');await list()}catch(e){notice(e.message)};return}
      document.querySelector('#meeting-consent').innerHTML='<p>המיקרופון במכשיר יקליט. השמע יישמר בשרת ובענן אם הוגדר; התמלול יישלח ל־Claude Code שהוגדר בשרת לצורך סיכום. יש ליידע את המשתתפים ולקבל הסכמה כנדרש.</p><button class="primary" id="meeting-confirm">המשתתפים מודעים — התחלת הקלטה</button>';
      document.querySelector('#meeting-confirm').onclick=async()=>{try{await api('/v1/meetings/start',{consent:true});notice('בקשת הקלטה נשלחה. המתינו לחיווי במכשיר.');await list()}catch(e){notice(e.message)}};
    };
    document.querySelectorAll('[data-meeting]').forEach(button=>button.onclick=()=>detail(button.dataset.meeting).catch(e=>notice(e.message)));
  }
  async function detail(id){
    clearInterval(poll);
    const m=await api('/v1/meetings/'+encodeURIComponent(id));
    panel(m.title||'פגישה',`<button class="secondary" id="meetings-back">חזרה לפגישות</button><p>${esc(stateName(m.state))} · ${Math.round((m.seconds||0)/60)} דקות</p>${m.stop_reason?`<p role="status">ההקלטה נעצרה: ${esc(m.stop_reason)}</p>`:''}${(m.audio_parts||[]).length>1?`<p>איחוד השמע לא הושלם; כל המקטעים זמינים בנפרד.</p>${m.audio_parts.map(part=>`<p>${esc(part)}</p><audio controls preload="none" style="width:100%" src="/v1/meetings/${encodeURIComponent(id)}/audio?part=${encodeURIComponent(part)}"></audio>`).join('')}`:m.has_audio?`<audio controls preload="none" style="width:100%" src="/v1/meetings/${encodeURIComponent(id)}/audio"></audio>`:"<p>אין קובץ שמע זמין לפגישה זו.</p>"}${["audio_only","processing_failed","summary_unavailable","interrupted"].includes(m.state)?'<button class="secondary" id="meeting-retry">ניסיון נוסף לתמלול ולסיכום</button>':''}<h3>סיכום</h3><div style="white-space:pre-wrap;overflow-wrap:anywhere">${esc(m.summary||'הסיכום עדיין אינו זמין')}</div><h3>תמלול</h3><div style="white-space:pre-wrap;overflow-wrap:anywhere">${esc(m.transcript||'התמלול עדיין אינו זמין')}</div>${m.live||['recording','processing'].includes(m.state)?'':'<button class="secondary" id="meeting-delete">מחיקת הפגישה וההקלטה</button>'}`);
    document.querySelector('#meetings-back').onclick=()=>list().catch(e=>notice(e.message));
    const retry=document.querySelector('#meeting-retry');if(retry)retry.onclick=async()=>{try{await api('/v1/meetings/'+encodeURIComponent(id)+'/retry',{});await list()}catch(e){notice(e.message)}};
    const remove=document.querySelector('#meeting-delete');if(remove)remove.onclick=async()=>{if(!confirm('למחוק את הפגישה, התמלול וההקלטה גם מארכיון הענן?'))return;try{await api('/v1/meetings/'+encodeURIComponent(id)+'/delete',{});await list()}catch(e){notice(e.message)}};
  }
  // Explicit refresh avoids replacing focused controls/consent while the user acts.
  return list();
}
