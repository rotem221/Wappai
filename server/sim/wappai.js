import {meetingLibrary} from './meetings.js';
import { PipPlayer } from "./pip-player.js";
const $ = (s) => document.querySelector(s),
  esc = (s) =>
    String(s ?? "").replace(
      /[&<>"']/g,
      (c) =>
        ({
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          '"': "&quot;",
          "'": "&#39;",
        })[c],
    );
let state,
  socket,
  reconnect,
  cursor = 0,
  panelPlayers = [],
  jobsTimer,
  sending = false,
  requestKey = null,
  draftText = "",
  petPlayer,
  noticeTimer;
let theme = localStorage.getItem("wappai.theme") || "system";
function applyTheme() {
  document.body.dataset.theme =
    theme === "system"
      ? matchMedia("(prefers-color-scheme: dark)").matches
        ? "dark"
        : "light"
      : theme;
}
applyTheme();
matchMedia("(prefers-color-scheme: dark)").addEventListener(
  "change",
  applyTheme,
);
function notice(text) {
  const node = $("#notice"),
    modal = $("#panel");
  (modal.open ? modal : document.body).append(node);
  node.classList.toggle("dialog-notice", modal.open);
  $("#notice").textContent = text;
  $("#notice").hidden = false;
  clearTimeout(noticeTimer);
  noticeTimer = setTimeout(() => ($("#notice").hidden = true), 6500);
}
async function api(path, data) {
  const r = await fetch(path, {
    credentials: "same-origin",
    ...(data !== undefined
      ? {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(data),
        }
      : {}),
  });
  if (!r.ok) {
    let d;
    try {
      d = await r.json();
    } catch {}
    const e = new Error(
      typeof d?.detail === "string"
        ? d.detail
        : `הפעולה לא הושלמה (${r.status})`,
    );
    e.status = r.status;
    throw e;
  }
  return r.headers.get("content-type")?.includes("json") ? r.json() : r.blob();
}
function action(button, fn) {
  button.addEventListener("click", async () => {
    button.disabled = true;
    try {
      await fn();
    } catch (e) {
      notice(e.message);
    } finally {
      button.disabled = false;
    }
  });
}
function drawer(open) {
  document.body.classList.toggle("drawer-closed", !open);
  $("#toggle-drawer").setAttribute("aria-expanded", String(open));
  $("#drawer-scrim").hidden = !open || innerWidth > 760;
  $("#drawer").inert = !open;
}
drawer(innerWidth > 760);
$("#toggle-drawer").onclick = () =>
  drawer(document.body.classList.contains("drawer-closed"));
$("#close-drawer").onclick = $("#drawer-scrim").onclick = () => drawer(false);
let swipe;
document.addEventListener(
  "touchstart",
  (e) => {
    if ($("#panel").open) return;
    swipe = { x: e.touches[0].clientX, y: e.touches[0].clientY };
  },
  { passive: true },
);
document.addEventListener(
  "touchend",
  (e) => {
    if (!swipe) return;
    const dx = e.changedTouches[0].clientX - swipe.x,
      dy = e.changedTouches[0].clientY - swipe.y;
    if (Math.abs(dy) < 45) {
      if (swipe.x > innerWidth - 35 && dx < -65) drawer(true);
      else if (dx > 75 && e.target.closest("#drawer")) drawer(false);
    }
    swipe = null;
  },
  { passive: true },
);
function renderSessions() {
  const q = $("#chat-search").value.trim().toLowerCase();
  $("#sessions").innerHTML = state.sessions
    .filter((s) => s.title.toLowerCase().includes(q))
    .map(
      (s) =>
        `<div class="session-row"><button class="session ${s.id === state.active_session ? "active" : ""}" data-session="${esc(s.id)}"><span>${esc(s.title)}</span><small>${esc(s.provider)}</small></button><button class="session-delete" data-delete-session="${esc(s.id)}" aria-label="מחיקת השיחה: ${esc(s.title)}"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path d="M3 6h18M9 6V3h6v3M6 6l1 15h10l1-15M10 10v7m4-7v7"/></svg></button></div>`,
    )
    .join("");
  $("#sessions")
    .querySelectorAll("[data-session]")
    .forEach((b) =>
      action(b, async () => {
        await api(`/v1/sessions/${b.dataset.session}/select`, {});
        await refresh();
        if (innerWidth <= 760) drawer(false);
      }),
    );
  $("#sessions").querySelectorAll("[data-delete-session]").forEach((b) =>
    action(b, async () => {
      const session = state.sessions.find((s) => s.id === b.dataset.deleteSession);
      if (!session || !confirm(`למחוק את השיחה ״${session.title}״? ההודעות יימחקו מ־Wappai בכל המכשירים המחוברים. לא ניתן לבטל את המחיקה.`)) return;
      await api(`/v1/sessions/${session.id}/delete`, {});
      await refresh();
    }),
  );
}
$("#chat-search").oninput = () => state && renderSessions();
function renderMessages() {
  const box = $("#messages"),
    atBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 100;
  box.innerHTML = state.messages.length
    ? state.messages
        .map(
          (m) =>
            `<article class="message ${m.role === "user" ? "user" : "assistant"}"><div class="bubble" dir="auto">${esc(m.text)}</div></article>`,
        )
        .join("")
    : `<section class="welcome"><div class="welcome-orbit"><img class="welcome-mark" src="/sim/wappai-mark.png" alt=""></div><p class="eyebrow">YOUR LITTLE COMPANION</p><h2>מה נעשה היום?</h2><p>רעיון קטן, שאלה גדולה, או פשוט לדבר.</p><div class="suggestions"><button>מה אפשר לעשות יחד?</button><button>תעזור לי לתכנן את היום</button></div></section>`;
  box.querySelectorAll(".suggestions button").forEach(
    (b) =>
      (b.onclick = () => {
        $("#draft").value = b.textContent;
        $("#draft").dispatchEvent(new Event("input"));
        $("#draft").focus();
      }),
  );
  if (atBottom || !state.messages.length) box.scrollTop = box.scrollHeight;
}
function deviceText() {
  return state.device.online ? "המכשיר מחובר" : "המכשיר אינו מחובר";
}
function render() {
  const session = state.sessions.find((s) => s.id === state.active_session);
  $("#chat-title").textContent = session?.title || "שיחה חדשה";
  $("#provider-label").textContent =
    session?.provider === "codex" ? "Codex" : "Claude";
  $("#connection span").textContent = deviceText();
  $("#connection").classList.toggle("online", state.device.online);
  $("#drawer-device").textContent =
    `${deviceText()}${state.device.battery?.pct != null ? " · " + state.device.battery.pct + "%" : ""}`;
  renderSessions();
  renderMessages();
  const p =
    state.pips.find((p) => p.id === state.selected_pip) || state.pips[0];
  if (!petPlayer) petPlayer = new PipPlayer($("#floating-pip canvas"), p);
  else petPlayer.pip = p;
  petPlayer.reduced = state.settings.reduced_motion;
  $("#floating-pip").hidden =
    localStorage.getItem("wappai.pet.hidden") === "true";
}
let refreshPromise;
async function refresh() {
  if (refreshPromise) return refreshPromise;
  refreshPromise = (async () => {
    state = await api("/v1/snapshot");
    cursor = Math.max(cursor, state.cursor);
    render();
  })();
  try {
    await refreshPromise;
  } finally {
    refreshPromise = null;
  }
}
function message(e, role) {
  if (e.session_id && e.session_id !== state.active_session) return;
  const id = e.message_id || e.id;
  if (!id) return;
  let m = state.messages.find((m) => m.id === id);
  if (!m) {
    m = { id, role, text: "" };
    state.messages.push(m);
  }
  m.text = e.full_text ?? e.text ?? m.text;
  renderMessages();
  $("#messages").scrollTop = $("#messages").scrollHeight;
}
function event(e) {
  if (e.cursor) {
    if (e.cursor <= cursor) return;
    cursor = e.cursor;
  }
  switch (e.type) {
    case "heard":
      $("#messages .live-transcript")?.remove();
      message(e, "user");
      break;
    case "say":
      message(e, "assistant");
      if (petPlayer) petPlayer.motion = "speaking";
      break;
    case "transcript.partial": {
      let node = $("#messages .live-transcript");
      if (!e.text) {
        node?.remove();
        break;
      }
      if (!node) {
        node = document.createElement("article");
        node.className = "message user live-transcript";
        $("#messages").append(node);
      }
      node.textContent = e.text;
      $("#messages").scrollTop = $("#messages").scrollHeight;
      break;
    }
    case "emotion":
    case "state":
      $("#stop-turn").hidden = !["thinking", "working", "speaking"].includes(
        e.emotion,
      );
      if (petPlayer) petPlayer.motion = e.emotion || e.state || "idle";
      break;
    case "interaction":
      $("#turn-status").textContent = e.text || "";
      $("#turn-status").hidden = !e.text;
      if (e.clear_card) $("#device-badge").hidden = true;
      break;
    case "device.badge":
      $("#device-badge").textContent =
        `${e.dev?.on ? "◉" : "○"} ${e.dev?.name || ""} · ${e.pending ? "מבצע…" : e.dev?.on ? "פועל" : "כבוי"}`;
      $("#device-badge").hidden = false;
      break;
    case "turn.completed":
    case "turn.failed":
    case "stop":
      $("#stop-turn").hidden = true;
      $("#turn-status").hidden = true;
      $("#messages .live-transcript")?.remove();
      if (petPlayer) petPlayer.motion = "idle";
      refresh().catch(() => {});
      break;
    case "pip.job.completed":
      notice(e.status === "preview_ready" ? "התצוגה המקדימה מוכנה לאישור בגלריה" : "ה־Pip והאנימציות שלו מוכנים בגלריה");
      if ($("#jobs")) pips().catch(() => {});
      else refresh().catch(() => {});
      break;
    case "session.deleted":
    case "session.active":
    case "pips.updated":
    case "pip.selected":
    case "device.connection":
      refresh().catch(() => {});
      break;
    case "status":
      state.device = { ...state.device, ...e };
      render();
      break;
  }
}
function connect() {
  clearTimeout(reconnect);
  socket?.close();
  const ws = new WebSocket(
    `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/v1/events?after=${cursor}`,
  );
  socket = ws;
  ws.onmessage = (m) => {
    try {
      event(JSON.parse(m.data));
    } catch (e) {
      console.warn("Event not applied", e);
    }
  };
  ws.onclose = () => {
    if (socket !== ws) return;
    $("#connection span").textContent = "החיבור לשרת נותק — מתחבר מחדש…";
    reconnect = setTimeout(async () => {
      try {
        await refresh();
        connect();
      } catch (e) {
        if (e.status === 401) login();
        else connect();
      }
    }, 2500);
  };
}
function login() {
  stopListening();
  socket?.close();
  socket = null;
  clearTimeout(reconnect);
  $("#workspace").hidden = true;
  $("#login").hidden = false;
}
async function boot() {
  await refresh();
  $("#login").hidden = true;
  $("#workspace").hidden = false;
  connect();
  const panel = new URLSearchParams(location.search).get("panel");
  if (["settings", "voice", "pips"].includes(panel)) openPanel(panel);
}
$("#login-form").onsubmit = async (e) => {
  e.preventDefault();
  const b = e.submitter;
  b.disabled = true;
  try {
    await api("/v1/web/login", { code: $("#pair-code").value });
    $("#pair-code").value = "";
    await boot();
  } catch (e) {
    notice(e.message);
  } finally {
    b.disabled = false;
  }
};
$("#draft").oninput = () => {
  $("#send").disabled = !$("#draft").value.trim() || sending;
  $("#draft").style.height = "auto";
  $("#draft").style.height = Math.min($("#draft").scrollHeight, 130) + "px";
};
$("#draft").onkeydown = (e) => {
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
    e.preventDefault();
    $("#composer").requestSubmit();
  }
};
$("#composer").onsubmit = async (e) => {
  e.preventDefault();
  const text = $("#draft").value.trim();
  if (!text || sending) return;
  sending = true;
  $("#send").disabled = true;
  if (draftText !== text) {
    draftText = text;
    requestKey = crypto.randomUUID();
  }
  try {
    if (!state.active_session) await newChat();
    await api(`/v1/sessions/${state.active_session}/messages`, {
      text,
      idempotency_key: requestKey,
    });
    $("#draft").value = "";
    requestKey = null;
    draftText = "";
    await refresh();
  } catch (e) {
    notice(e.message);
  } finally {
    sending = false;
    $("#draft").dispatchEvent(new Event("input"));
  }
};
async function newChat() {
  const provider =
    (state.providers.some(
      (p) => p.id === localStorage.getItem("wappai.provider") && p.available,
    )
      ? localStorage.getItem("wappai.provider")
      : null) ||
    state.sessions.find((s) => s.id === state.active_session)?.provider ||
    state.providers.find((p) => p.available)?.id ||
    "claude";
  await api("/v1/sessions", { provider });
  await refresh();
  if (innerWidth <= 760) drawer(false);
}
action($("#new-chat"), newChat);
document.addEventListener("keydown", (e) => {
  if ((e.metaKey || e.ctrlKey) && e.key === "n" && !$("#panel").open) {
    e.preventDefault();
    newChat().catch((e) => notice(e.message));
  }
  if (e.key === "Escape") {
    $("#pet-menu").hidden = true;
    if (innerWidth <= 760) drawer(false);
  }
});
function disposePanel() {
  clearInterval(jobsTimer);
  panelPlayers.forEach((p) => p.stop());
  panelPlayers = [];
}
$("#panel").addEventListener("close", () => {
  disposePanel();
  const node = $("#notice");
  document.body.append(node);
  node.classList.remove("dialog-notice");
});
$("#close-panel").onclick = () => $("#panel").close();
function panel(title, html) {
  disposePanel();
  $("#panel-title").textContent = title;
  $("#panel-body").innerHTML = html;
  if (!$("#panel").open) $("#panel").showModal();
}
document
  .querySelectorAll("[data-panel]")
  .forEach((b) => (b.onclick = () => openPanel(b.dataset.panel)));
async function openPanel(type) {
  try {
    if (type === "pips") await pips();
    else if (type === "voice") await voice();
    else if (type === "meetings") await meetingLibrary({api,panel,esc,notice});
    else settings();
  } catch (e) {
    notice(e.message);
  }
}
const field = (label, html) =>
  `<label class="field"><span>${label}</span>${html}</label>`;
function settings() {
  const d = state.device,
    s = state.settings,
    model = d.board || "Wappai";
  const pct = d.battery?.pct;
  panel(
    "הגדרות",
    `<section class="device-summary"><div class="device-mini ${/2\.?16/.test(model) ? "square" : /1\.?8/.test(model) ? "rect" : ""}"><img src="/sim/wappai-screen-mark.png" alt=""><span>Wappai</span></div><div><h3>Wappai</h3><p>${esc(model)}</p><div class="device-metrics"><span class="battery" style="--charge:${Number(pct) || 0}%">${pct == null ? "—" : esc(pct)}</span><span><bdi>${d.rssi == null ? "אין נתוני קליטה" : esc(d.rssi) + " dBm"}</bdi></span></div><p class="hint">${deviceText()} · ${esc(d.fw_version || "")}</p></div></section><h3 class="section-title">המכשיר שלך</h3><div class="setting-block">${[
      ["live_transcription", "הצגת הדיבור בזמן אמת"],
      ["shake_reaction", "תגובה לניעור"],
      ["character_sounds", "צלילי הדמות"],
      ["reduced_motion", "הפחתת תנועה"],
    ]
      .map(
        ([k, l]) =>
          `<label class="setting-row"><span>${l}</span><input class="toggle" type="checkbox" data-setting="${k}" ${s[k] ? "checked" : ""}></label>`,
      )
      .join("")}${[
      ["volume", "עוצמת קול"],
      ["brightness", "בהירות"],
    ]
      .map(
        ([k, l]) =>
          `<label class="setting-row"><span>${l}</span><input aria-label="${l}" type="range" min="${k === "brightness" ? 20 : 0}" max="${k === "brightness" ? 255 : 100}" value="${s[k] ?? 70}" data-setting="${k}"></label>`,
      )
      .join(
        "",
      )}</div><h3 class="section-title">באפליקציה</h3><label class="setting-row"><span>השמעת התשובות בדפדפן</span><input type="checkbox" id="browser-audio" ${listenSocket ? "checked" : ""}></label>${field("מוח לשיחות חדשות", `<select id="brain-provider" class="input">${state.providers.map((p) => `<option value="${esc(p.id)}" ${p.available ? "" : "disabled"}>${p.id === "codex" ? "Codex" : "Claude"}${p.available ? "" : " — לא מחובר"}</option>`).join("")}</select>`)}${field("מראה", `<select class="input" id="theme"><option value="system">לפי המערכת</option><option value="light">בהיר</option><option value="dark">כהה</option></select>`)}<label class="setting-row"><span>הצגת הדמות הצפה</span><input type="checkbox" class="toggle" id="show-pet" ${localStorage.getItem("wappai.pet.hidden") !== "true" ? "checked" : ""}></label><div class="actions"><button class="secondary" id="voice-settings">קולות ודיבור ↗</button><a class="secondary" href="/admin">ניהול מתקדם ↗</a><button class="secondary" id="logout">יציאה</button></div>`,
  );
  $("#browser-audio").onchange = async (e) => {
    try {
      if (e.target.checked) await startListening();
      else stopListening();
    } catch (error) {
      e.target.checked = false;
      notice(error.message);
    }
  };
  $("#brain-provider").value =
    localStorage.getItem("wappai.provider") ||
    state.sessions.find((s) => s.id === state.active_session)?.provider ||
    "claude";
  $("#brain-provider").onchange = (e) =>
    localStorage.setItem("wappai.provider", e.target.value);
  $("#theme").value = theme;
  $("#theme").onchange = (e) => {
    theme = e.target.value;
    localStorage.setItem("wappai.theme", theme);
    applyTheme();
  };
  $("#show-pet").onchange = (e) => {
    localStorage.setItem("wappai.pet.hidden", String(!e.target.checked));
    $("#floating-pip").hidden = !e.target.checked;
  };
  $("#panel-body")
    .querySelectorAll("[data-setting]")
    .forEach(
      (el) =>
        (el.onchange = async () => {
          el.disabled = true;
          try {
            await api("/v1/settings", {
              [el.dataset.setting]:
                el.type === "checkbox" ? el.checked : Number(el.value),
            });
            await refresh();
          } catch (e) {
            notice(e.message);
            el.type === "checkbox"
              ? (el.checked = !!state.settings[el.dataset.setting])
              : (el.value = state.settings[el.dataset.setting]);
          } finally {
            el.disabled = false;
          }
        }),
    );
  $("#voice-settings").onclick = () => openPanel("voice");
  action($("#logout"), async () => {
    await api("/v1/web/logout", {});
    $("#panel").close();
    login();
  });
}
async function voice() {
  const v = await api("/v1/voice");
  panel(
    "קולות ודיבור",
    `${field("סגנון הדיבור", '<select id="voice-style" class="input"><option value="lively">מלא חיים</option><option value="natural">טבעי</option></select>')}${field("ספק הקול", '<select id="voice-provider" class="input"><option value="edge">הקולות המובנים</option><option value="elevenlabs">ElevenLabs</option></select>')}${field("קול מובנה", '<select id="edge-voice" class="input"><option value="he-IL-HilaNeural">הילה</option><option value="he-IL-AvriNeural">אברי</option></select>')}<button id="save-edge" class="primary">שמירת הקול המובנה</button><h3 class="section-title">ElevenLabs</h3><p class="hint">${v.connected ? "החשבון מחובר. אפשר לחפש, להאזין ולבחור קול." : "חבר את החשבון שלך כדי לבחור קול. המפתח נשמר בשרת בלבד."}</p>${field("מפתח API", '<input id="voice-key" type="password" class="input" autocomplete="off" placeholder="sk_…">')}<button class="secondary" id="connect-voice">חיבור חשבון</button>${field("חיפוש קולות", '<input id="voice-search" type="search" class="input" placeholder="שם קול">')}<button class="secondary" id="search-voices">חיפוש</button>${field("מודל דיבור", '<select id="voice-model" class="input"></select>')}<div id="voices"></div><button id="more-voices" class="secondary" hidden>קולות נוספים</button><p class="hint">האזנה לדוגמה משתמשת במכסת ElevenLabs שלך.</p>`,
  );
  $("#voice-style").value = v.style;
  $("#voice-provider").value = v.provider;
  $("#edge-voice").value = v.edge_voice;
  let next = "";
  function listing(r, append = false) {
    $("#voice-model").innerHTML = r.models
      .map((m) => `<option value="${esc(m.id)}">${esc(m.name)}</option>`)
      .join("");
    if (r.models.some((m) => m.id === v.model_id))
      $("#voice-model").value = v.model_id;
    const html = r.voices
      .map(
        (x) =>
          `<div class="voice-row"><div><strong>${esc(x.name)}</strong><p class="hint">${esc(x.description || x.language || "")}</p></div><button class="secondary" data-preview="${esc(x.id)}">האזנה</button><button class="primary" data-voice="${esc(x.id)}">בחירה</button></div>`,
      )
      .join("");
    if (append) $("#voices").insertAdjacentHTML("beforeend", html);
    else $("#voices").innerHTML = html || '<p class="hint">לא נמצאו קולות.</p>';
    next = r.next_cursor || "";
    $("#more-voices").hidden = !next;
    $("#voices")
      .querySelectorAll("button:not([data-bound])")
      .forEach((b) => {
        b.dataset.bound = "1";
        action(b, async () => {
          const body = {
            provider: "elevenlabs",
            voice_id: b.dataset.voice || b.dataset.preview,
            model_id: $("#voice-model").value,
            style: $("#voice-style").value,
          };
          if (b.dataset.preview) {
            const blob = await api("/v1/voice/preview", body),
              url = URL.createObjectURL(blob),
              audio = new Audio(url);
            audio.onended = () => URL.revokeObjectURL(url);
            await audio.play();
          } else {
            await api("/v1/voice", body);
            await refresh();
            notice("הקול נבחר");
            $("#voice-provider").value = "elevenlabs";
          }
        });
      });
  }
  action($("#save-edge"), async () => {
    await api("/v1/voice", {
      provider: "edge",
      edge_voice: $("#edge-voice").value,
      style: $("#voice-style").value,
    });
    await refresh();
    notice("הקול נשמר");
    $("#voice-provider").value = "edge";
  });
  $("#voice-provider").onchange = () => {
    if ($("#voice-provider").value === "elevenlabs") $("#voice-search").focus();
  };
  action($("#connect-voice"), async () => {
    const key = $("#voice-key").value;
    $("#voice-key").value = "";
    listing(await api("/v1/voice/connect", { api_key: key }));
    notice("החשבון חובר");
  });
  action($("#search-voices"), async () =>
    listing(
      await api("/v1/voice/search", { search: $("#voice-search").value }),
    ),
  );
  action($("#more-voices"), async () =>
    listing(
      await api("/v1/voice/search", {
        search: $("#voice-search").value,
        cursor: next,
      }),
      true,
    ),
  );
  if (v.connected) listing(await api("/v1/voice/search", {}));
}
async function pips() {
  await refresh();
  panel(
    "הדמויות שלי",
    `<p class="hint">אותן דמויות, בכל המסכים שלך.</p><div class="pip-grid">${state.pips.map((p) => `<button class="pip-tile ${p.id === state.selected_pip ? "selected" : ""}" data-pip="${esc(p.id)}"><canvas width="192" height="192"></canvas><strong>${esc(p.name)}</strong><small>${p.id === state.selected_pip ? "הדמות הנוכחית" : ["pip", "nori", "orbit"].includes(p.id) ? "דמות מובנית" : "הדמות שלך"}</small></button>`).join("")}<div id="jobs" class="pip-drafts"></div></div><button class="primary" id="create-pip">＋ יצירת דמות חדשה</button>`,
  );
  $("#panel-body")
    .querySelectorAll("[data-pip]")
    .forEach((b) => {
      const p = state.pips.find((p) => p.id === b.dataset.pip);
      panelPlayers.push(new PipPlayer(b.querySelector("canvas"), p));
      b.onclick = () => pipDetail(p).catch((e) => notice(e.message));
    });
  $("#create-pip").onclick = () => createPip();
  await jobs();
  jobsTimer = setInterval(() => {
    if (!document.hidden) jobs().catch(() => {});
  }, 4000);
}
async function jobs() {
  const list = await api("/v1/pip-jobs");
  if (!$("#jobs")) return;
  const seen = new Set();
  const drafts = list.filter(j => !["ready","cancelled","superseded"].includes(j.status) && !seen.has(j.pip_id) && seen.add(j.pip_id));
  $("#jobs").innerHTML =
    drafts
      .map(
        (j) =>
          `<div class="pip-tile job"><strong>${esc(j.name)}</strong><p>${esc({ preview_generating: "מכין תצוגה מקדימה", preview_ready: "תצוגה מקדימה", building: "יוצר את כל ההבעות והתנועות", applying: "מעביר למכשיר", ready: "הדמות מוכנה", failed: "היצירה נעצרה", cancelled: "היצירה בוטלה" }[j.status] || j.status)} · ${j.progress || 0}%</p>${j.error ? `<p class="hint">${esc(j.error)}</p>` : ""}${j.preview_sha ? `<img class="pip-preview" src="/v1/pip-jobs/${esc(j.id)}/preview.png" alt="תצוגה מקדימה של ${esc(j.name)}">` : ""}<div class="actions">${["preview_ready","failed"].includes(j.status) ? `<button class="secondary" data-edit-job="${esc(j.id)}">עריכת העיצוב</button>` : ""}${j.preview_sha && ["preview_ready", "failed"].includes(j.status) ? `<button class="primary" data-apply="${esc(j.id)}">אישור ויצירה מלאה</button>` : ""}${["preview_generating", "preview_ready", "building", "failed"].includes(j.status) ? `<button class="secondary" data-cancel="${esc(j.id)}">ביטול</button>` : ""}</div></div>`,
      )
      .join("");
  $("#jobs").querySelectorAll("[data-edit-job]").forEach(b => action(b, async () => {
    const job=list.find(j=>j.id===b.dataset.editJob);
    await createPip(state.pips.find(p=>p.id===job.target),job);
  }));
  $("#jobs")
    .querySelectorAll("[data-apply]")
    .forEach((b) =>
      action(b, async () => {
        const j = list.find((j) => j.id === b.dataset.apply);
        await api(`/v1/pip-jobs/${j.id}/apply`, { preview_sha: j.preview_sha });
        await jobs();
      }),
    );
  $("#jobs")
    .querySelectorAll("[data-cancel]")
    .forEach((b) =>
      action(b, async () => {
        await api(`/v1/pip-jobs/${b.dataset.cancel}/cancel`, {});
        await jobs();
      }),
    );
}
async function createPip(target, draft=null) {
  panel(
    target ? "עיצוב מחדש" : "יצירת דמות חדשה",
    `<p class="hint">תאר את הדמות או צרף תמונה. קודם נציג תצוגה מקדימה; רק לאחר אישורך ניצור את כל ההבעות והתנועות.</p><form id="pip-form">${field("שם הדמות", `<input id="pip-name" class="input" maxlength="30" required value="${esc(draft?.name ?? target?.name ?? "")}">`)}<div id="pip-description-field">${field("איך הדמות נראית?", `<textarea id="pip-description" class="input" maxlength="1200" rows="4" placeholder="למשל: שועל קטן בצבע לבנדר, עם צעיף ירוק ועיניים סקרניות">${esc(draft?.description ?? target?.description ?? "")}</textarea>`)}</div>${field("תמונת השראה (אפשרות)", '<input id="pip-image" class="input" type="file" accept="image/png,image/jpeg,image/webp">')}<img id="reference-preview" class="pip-preview" hidden alt="התמונה שבחרת"><button type="button" id="remove-reference" class="secondary" hidden>הסרת התמונה</button><button type="submit" class="primary">יצירת תצוגה מקדימה</button></form>`,
  );
  let reference, loadingImage = false, discardReference=false;
  const imageMode = () => {
    $("#pip-description-field").hidden = false;
    $("#remove-reference").hidden = !reference;
    $("#pip-description").placeholder = reference ? "תיאור או הנחיות לתמונה (אפשרות)" : "תיאור הדמות, הצבעים והאופי";
    $("#pip-name").required = !reference;
    $("#pip-name").closest("label").hidden = !!reference;
    $("#pip-form .primary").textContent = reference ? "אישור התמונה ויצירת תצוגה מקדימה" : "יצירת תצוגה מקדימה";
  };
  $("#remove-reference").onclick=()=>{reference=null;discardReference=true;$("#reference-preview").hidden=true;$("#pip-image").value="";imageMode();};
  $("#pip-image").onchange = async (e) => {
    reference = null;
    $("#reference-preview").hidden = true;
    const file = e.target.files[0];
    imageMode();
    if (!file) return;
    loadingImage = true;
    $("#pip-image").disabled = true;
    $("#pip-form .primary").disabled = true;
    try {
      if (file.size > 12 * 1024 * 1024) throw Error("בחר תמונה קטנה מ־12MB");
      const bitmap = await createImageBitmap(file),
        c = document.createElement("canvas"),
        scale = Math.min(1, 1024 / Math.max(bitmap.width, bitmap.height));
      if (Math.min(bitmap.width, bitmap.height) < 32) {bitmap.close(); throw Error("בחרו תמונה בגודל 32×32 פיקסלים לפחות");}
      c.width = Math.round(bitmap.width * scale);
      c.height = Math.round(bitmap.height * scale);
      c.getContext("2d").drawImage(bitmap, 0, 0, c.width, c.height);
      bitmap.close();
      const data = c.toDataURL("image/png");
      reference = data.split(",")[1];discardReference=false;
      $("#reference-preview").src = data;
      $("#reference-preview").hidden = false;
    } catch (e) {
      notice("לא ניתן להשתמש בתמונה. " + e.message);
    } finally {
      loadingImage = false;
      $("#pip-image").disabled = false;
      $("#pip-form .primary").disabled = false;
      imageMode();
    }
  };
  $("#pip-form").onsubmit = async (e) => {
    e.preventDefault();
    if (loadingImage) return;
    const b = e.submitter;
    b.disabled = true;
    try {
      const description = $("#pip-description").value.trim();
      if (!reference && description.length < 3) throw Error("יש להוסיף תיאור או תמונה");
      await api("/v1/pip-jobs", {
        name: $("#pip-name").value.trim(),
        description,
        reference,
        target: draft?.target ?? target?.id,
        replaces_job: draft?.id,
        discard_reference: discardReference,
      });
      await pips();
    } catch (e) {
      notice(e.message);
    } finally {
      b.disabled = false;
    }
  };
  const source=draft?.has_reference ? `/v1/pip-jobs/${draft.id}/reference.png` : !draft && target?.asset_id ? `/v1/pips/${target.id}/reference.png` : null;
  if (source) {
    loadingImage=true;$("#pip-form .primary").disabled=true;
    try {
      const blob=await api(source);
      const data=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=reject;reader.readAsDataURL(blob);});
      reference=data.split(",")[1];$("#reference-preview").src=data;$("#reference-preview").hidden=false;imageMode();
      $("#pip-form .primary").disabled=false;
    }catch{notice("לא ניתן לטעון את תמונת המקור. פתחו שוב את העריכה או בחרו תמונה חדשה.");}
    finally{loadingImage=false;}
  }

}
async function pipDetail(p) {
  const built = ["pip", "nori", "orbit"].includes(p.id);
  panel(
    p.name,
    `<div class="expression-stage"><canvas width="288" height="288"></canvas></div><div class="actions"><button class="primary" id="activate-pip">${state.selected_pip === p.id ? "הדמות הנוכחית" : "בחירת הדמות"}</button><button class="secondary" id="back-pips">כל הדמויות</button></div><h3 class="section-title">הבעות ותנועה</h3><div class="expression-list">${[
      ["idle", "רגוע"],
      ["happy", "שמח"],
      ["thinking", "חושב"],
      ["listening", "מקשיב"],
      ["speaking", "מדבר"],
      ["dizzy", "מסוחרר"],
      ["wave", "שלום"],
      ["sleeping", "ישן"],
    ]
      .map(
        ([m, n]) =>
          `<button class="secondary" data-motion="${m}">${n}</button>`,
      )
      .join(
        "",
      )}</div>${field("הבעה חדשה לפי תיאור", '<textarea id="expression-prompt" class="input" rows="2" placeholder="למשל: מתרגש ומנופף לשלום"></textarea>')}<button class="secondary" id="preview-expression">יצירת תצוגה מקדימה</button><div id="expression-result"></div><div id="saved-expressions"></div>${built ? '<p class="hint">דמות מובנית — אפשר להוסיף הבעות, אך לא למחוק או להחליף אותה.</p>' : `<h3 class="section-title">ניהול הדמות</h3>${field("שם", `<input id="rename-pip" class="input" maxlength="30" value="${esc(p.name)}">`)}<div class="actions"><button class="secondary" id="save-name">שמירת שם</button><button class="secondary" id="redesign-pip">עיצוב מחדש</button><button class="danger" id="delete-pip">מחיקת הדמות</button></div><div id="delete-confirm" hidden><p>למחוק את הדמות וההבעות שלה? לא ניתן לבטל פעולה זו.</p><button class="danger" id="confirm-delete">כן, למחוק</button></div>`}`,
  );
  const player = new PipPlayer($(".expression-stage canvas"), p);
  panelPlayers.push(player);
  $("#activate-pip").disabled = state.selected_pip === p.id;
  action($("#activate-pip"), async () => {
    await api(`/v1/pips/${p.id}/activate`, {});
    await refresh();
    notice("הדמות נבחרה");
    await pips();
  });
  $("#back-pips").onclick = () => openPanel("pips");
  document
    .querySelectorAll("[data-motion]")
    .forEach((b) => (b.onclick = () => (player.motion = b.dataset.motion)));
  action($("#preview-expression"), async () => {
    const expression = await api(`/v1/pips/${p.id}/expressions/preview`, {
      description: $("#expression-prompt").value,
    });
    player.motion = expression.motion;
    $("#expression-result").innerHTML =
      `<p>${esc(expression.name)} · ${esc(expression.motion)}</p><p class="hint">תצוגת התנועה בדפדפן; ההבעה המלאה והצליל זמינים בהפעלה במכשיר.</p><div class="actions"><button class="primary" id="save-expression">שמירה</button><button class="secondary" id="play-expression">הפעלה במכשיר</button></div>`;
    action($("#save-expression"), async () => {
      await api(`/v1/pips/${p.id}/expressions`, expression);
      notice("ההבעה נשמרה");
      await saved();
    });
    action($("#play-expression"), () =>
      api(`/v1/pips/${p.id}/expressions/play`, expression),
    );
  });
  async function saved() {
    const list = await api(`/v1/pips/${p.id}/expressions`);
    if (!$("#saved-expressions")) return;
    $("#saved-expressions").innerHTML = list.length
      ? '<h3 class="section-title">הבעות שמורות</h3>' +
        list
          .map(
            (x) =>
              `<div class="setting-row"><span>${esc(x.name)}</span><button class="secondary" data-play="${esc(x.id)}">הפעלה</button><button class="secondary" data-remove="${esc(x.id)}">מחיקה</button></div>`,
          )
          .join("")
      : "";
    $("#saved-expressions")
      .querySelectorAll("[data-play]")
      .forEach((b) =>
        action(b, () =>
          api(
            `/v1/pips/${p.id}/expressions/play`,
            list.find((x) => x.id === b.dataset.play),
          ),
        ),
      );
    $("#saved-expressions")
      .querySelectorAll("[data-remove]")
      .forEach((b) =>
        action(b, async () => {
          await api(
            `/v1/pips/${p.id}/expressions/${b.dataset.remove}/delete`,
            {},
          );
          await saved();
        }),
      );
  }
  await saved();
  if (!built) {
    action($("#save-name"), async () => {
      await api(`/v1/pips/${p.id}/edit`, { name: $("#rename-pip").value });
      await pips();
    });
    $("#redesign-pip").onclick = () => createPip(p);
    $("#delete-pip").onclick = () => ($("#delete-confirm").hidden = false);
    action($("#confirm-delete"), async () => {
      await api(`/v1/pips/${p.id}/delete`, {});
      await pips();
    });
  }
}
function showPetMenu() {
  const r = $("#floating-pip").getBoundingClientRect(),
    m = $("#pet-menu");
  m.hidden = false;
  m.style.left = Math.max(10, Math.min(innerWidth - 220, r.left)) + "px";
  m.style.top = Math.max(10, r.top - 145) + "px";
}
const pet = $("#floating-pip");
let drag,
  longPress,
  dragging = false;
const position = JSON.parse(
  localStorage.getItem("wappai.pet.position") || "null",
);
function place(x, y) {
  pet.classList.add("positioned");
  pet.style.left =
    Math.max(0, Math.min(innerWidth - pet.offsetWidth, x)) + "px";
  pet.style.top =
    Math.max(0, Math.min(innerHeight - pet.offsetHeight, y)) + "px";
  pet.style.right = "auto";
  pet.style.bottom = "auto";
}
if (position) place(position.x, position.y);
pet.onpointerdown = (e) => {
  drag = { x: e.clientX, y: e.clientY, rect: pet.getBoundingClientRect() };
  dragging = false;
  pet.setPointerCapture(e.pointerId);
  longPress = setTimeout(() => {
    dragging = true;
    showPetMenu();
  }, 450);
};
pet.onpointermove = (e) => {
  if (!drag) return;
  if (dragging) {
    $("#pet-menu").hidden = true;
    place(
      drag.rect.left + e.clientX - drag.x,
      drag.rect.top + e.clientY - drag.y,
    );
  } else if (Math.hypot(e.clientX - drag.x, e.clientY - drag.y) > 12)
    clearTimeout(longPress);
};
pet.onpointerup = (e) => {
  clearTimeout(longPress);
  if (dragging) {
    localStorage.setItem(
      "wappai.pet.position",
      JSON.stringify({ x: pet.offsetLeft, y: pet.offsetTop }),
    );
  } else if (drag && Math.hypot(e.clientX - drag.x, e.clientY - drag.y) < 12)
    openPanel("pips");
  drag = null;
};
pet.onpointercancel = () => {
  clearTimeout(longPress);
  drag = null;
};
pet.onkeydown = (e) => {
  if (["Enter", " "].includes(e.key)) {
    e.preventDefault();
    openPanel("pips");
  }
};
pet.oncontextmenu = (e) => {
  e.preventDefault();
  showPetMenu();
};
$("#hide-pet").onclick = () => {
  localStorage.setItem("wappai.pet.hidden", "true");
  pet.hidden = true;
  $("#pet-menu").hidden = true;
};
$("#reset-pet").onclick = () => {
  localStorage.removeItem("wappai.pet.position");
  pet.removeAttribute("style");
  pet.classList.remove("positioned");
  $("#pet-menu").hidden = true;
};
window.addEventListener("resize", () => {
  if (pet.style.left) place(pet.offsetLeft, pet.offsetTop);
  $("#drawer-scrim").hidden =
    innerWidth > 760 || document.body.classList.contains("drawer-closed");
});
// Hold-to-talk: permission only on a deliberate press; PCM work happens off the UI thread.
let recording = false,
  held = false,
  micGeneration = 0,
  audioContext,
  mediaStream,
  audioSocket,
  worklet;
const mic = $("#mic");
async function stopMic() {
  held = false;
  micGeneration++;
  const closing = audioSocket,
    context = audioContext;
  if (recording && closing?.readyState === 1)
    closing.send(JSON.stringify({ type: "ptt_end" }));
  recording = false;
  audioSocket = null;
  audioContext = null;
  mic.classList.remove("recording");
  mediaStream?.getTracks().forEach((t) => t.stop());
  mediaStream = null;
  worklet?.disconnect();
  worklet = null;
  setTimeout(() => closing?.close(), 500);
  if (context && context.state !== "closed") await context.close();
}
async function startMic() {
  if (held) return;
  clearPlayback();
  held = true;
  const generation = ++micGeneration;
  let stream, context, ws;
  const cancelled = () => !held || generation !== micGeneration;
  try {
    if (!navigator.mediaDevices?.getUserMedia)
      throw Error("הקלטה זמינה בחיבור HTTPS ובדפדפן התומך במיקרופון");
    stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true },
      video: false,
    });
    if (cancelled()) {
      stream.getTracks().forEach((t) => t.stop());
      return;
    }
    mediaStream = stream;
    context = new AudioContext({ sampleRate: 16000 });
    audioContext = context;
    await context.audioWorklet.addModule("/sim/pcm-worklet.js");
    if (cancelled()) return;
    ws = new WebSocket(
      `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws?kind=web`,
    );
    audioSocket = ws;
    await new Promise((resolve, reject) => {
      const timer = setTimeout(
        () => reject(Error("לא ניתן לפתוח ערוץ הקלטה")),
        8000,
      );
      ws.onopen = () => {
        clearTimeout(timer);
        resolve();
      };
      ws.onerror = ws.onclose = () => {
        clearTimeout(timer);
        reject(Error("החיבור להקלטה נכשל"));
      };
    });
    if (cancelled()) {
      ws.close();
      return;
    }
    ws.send(JSON.stringify({ type: "ptt_start" }));
    recording = true;
    mic.classList.add("recording");
    worklet = new AudioWorkletNode(context, "wappai-pcm");
    worklet.port.onmessage = (e) => {
      if (!cancelled() && recording && ws.readyState === 1) ws.send(e.data);
    };
    context.createMediaStreamSource(stream).connect(worklet);
    worklet.connect(context.destination);
    await context.resume();
    ws.onclose = () => {
      if (!cancelled()) {
        stopMic();
        notice("ערוץ ההקלטה נותק");
      }
    };
  } catch (e) {
    stream?.getTracks().forEach((t) => t.stop());
    ws?.close();
    if (!cancelled()) {
      await stopMic();
      notice(
        e.name === "NotAllowedError"
          ? "יש לאפשר גישה למיקרופון כדי להקליט"
          : e.message,
      );
    }
  }
}
mic.onpointerdown = (e) => {
  e.preventDefault();
  mic.setPointerCapture(e.pointerId);
  startMic();
};
mic.onpointerup = mic.onpointercancel = () => stopMic();
mic.onkeydown = (e) => {
  if ([" ", "Enter"].includes(e.key)) {
    e.preventDefault();
    if (!e.repeat) startMic();
  }
};
mic.onkeyup = (e) => {
  if ([" ", "Enter"].includes(e.key)) {
    e.preventDefault();
    stopMic();
  }
};
document.addEventListener("visibilitychange", () => {
  if (document.hidden) stopMic();
});
window.addEventListener("blur", () => stopMic());
action($("#stop-turn"), () => api("/v1/stop", {}));
let listenSocket = null,
  playbackContext = null,
  playbackTime = 0,
  playbackSources = new Set();
function clearPlayback() {
  for (const source of playbackSources) {
    try {
      source.stop();
    } catch {}
  }
  playbackSources.clear();
  playbackTime = 0;
}
function stopListening() {
  listenSocket?.close();
  listenSocket = null;
  clearPlayback();
  playbackContext?.close();
  playbackContext = null;
}
async function startListening() {
  stopListening();
  playbackContext = new AudioContext({ sampleRate: 16000 });
  await playbackContext.resume();
  const ws = new WebSocket(
    `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws?kind=web`,
  );
  listenSocket = ws;
  ws.binaryType = "arraybuffer";
  ws.onmessage = (e) => {
    if (typeof e.data === "string") {
      const message = JSON.parse(e.data);
      if (message.type === "stop") clearPlayback();
      return;
    }
    if (!playbackContext || recording) return;
    const pcm = new Int16Array(e.data),
      buffer = playbackContext.createBuffer(1, pcm.length, 16000),
      out = buffer.getChannelData(0);
    for (let i = 0; i < pcm.length; i++) out[i] = pcm[i] / 32768;
    const source = playbackContext.createBufferSource();
    source.buffer = buffer;
    source.connect(playbackContext.destination);
    playbackSources.add(source);
    source.onended = () => playbackSources.delete(source);
    playbackTime = Math.max(playbackContext.currentTime + 0.025, playbackTime);
    source.start(playbackTime);
    playbackTime += buffer.duration;
  };
  ws.onerror = () => notice("ערוץ השמע נותק. אפשר להפעיל אותו מחדש בהגדרות.");
}
try {
  const params = new URLSearchParams(location.search),
    token = params.get("token");
  if (token) {
    history.replaceState(null, "", location.pathname);
    await api("/v1/web/login", { legacy_token: token });
  }
  await boot();
} catch (e) {
  login();
  if (e.status !== 401) notice(e.message);
}
