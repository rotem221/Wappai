import os, sys, json, time, asyncio, array, math, struct
os.environ["DATA_DIR"] = "/tmp/claude-0/st/data"; os.environ["CLAUDE_WORKDIR"] = "/tmp/claude-0/st/brain"; os.environ["DEVICE_TOKEN"] = "tok123"
sys.path.insert(0, "/home/claude/companion/server")
from fastapi.testclient import TestClient
from app import main, admin
from app.voice import adpcm
from app.tools import meeting as M, composio
ok = 0; bad = 0
def check(name, cond, extra=""):
    global ok, bad
    print(("PASS " if cond else "FAIL ") + name, extra if not cond else ""); ok += cond; bad += not cond
main._oneshot = None
c = TestClient(main.app)
H = {"Authorization": "Bearer tok123"}
with c:
    # admin
    r = c.get("/admin"); check("admin needs login", r.status_code == 401)
    r = c.get("/admin", headers=H); check("admin page with token", r.status_code == 200 and "פגישות" in r.text)
    code = c.post("/admin/api/pair", headers=H).json()["code"]; check("pair code 6 digits", len(code) == 6 and code.isdigit())
    r = c.get(f"/admin/login?code={code}", follow_redirects=False); check("pair login sets cookie", r.status_code == 303 and "piko_admin" in r.headers.get("set-cookie", ""))
    r = c.get(f"/admin/login?code={code}", follow_redirects=False); check("code is single use", r.status_code == 401)
    for i in range(10): c.get("/admin/login?code=000000")
    r = c.get("/admin/login?code=000001"); check("brute force limited", r.status_code == 429)
    admin._fails.clear()
    st = c.get("/admin/api/status", headers=H).json(); check("status", "device" in st and "composio" in st)
    s = c.post("/admin/api/settings", headers=H, json={"volume": 55}).json(); check("volume setting", s.get("volume") == 55)
    check("ha status no token", c.get("/admin/api/ha/status", headers=H).json()["configured"] is False)
    check("composio status no key", c.get("/admin/api/composio/status", headers=H).json()["key"] is False)
    check("meetings list", isinstance(c.get("/admin/api/meetings", headers=H).json(), list))
    # board websocket: hello -> config; meeting with ADPCM; disconnect + resume
    with c.websocket_connect("/ws?token=tok123") as ws:
        ws.receive_json(); ws.receive_json()
        ws.send_json({"type": "hello", "device_id": "t", "fw_version": "test", "battery": {"pct": 50}})
        got = [ws.receive_json() for _ in range(1)]
        check("config on hello has volume", any(g.get("type") == "config" and g.get("volume") == 55 for g in got), got)
        r = c.post("/api/show?token=tok123", json={"what": "text", "title": "t", "body": "שלום"}).json()
        msgs = []
        for _ in range(6):
            m = ws.receive_json(); msgs.append(m)
            if m.get("type") == "card": break
        check("text card reaches board", any(m.get("type") == "card" and m.get("kind") == "text" for m in msgs), msgs)
        ws.send_json({"type": "ptt_start", "id": "mic", "mode": "meeting", "sample_rate": 16000, "codec": "adpcm"})
        for _ in range(6):
            m = ws.receive_json()
            if m.get("type") == "meeting": break
        mid = m.get("id"); check("meeting id sent", bool(mid), m)
        pcm = array.array("h", [int(6000 * math.sin(i * 0.2)) for i in range(2048)]).tobytes()
        st_ = [0, 0]
        for _ in range(40): ws.send_bytes(adpcm.encode(pcm, st_))
        time.sleep(0.5)
    time.sleep(0.5)
    mt = M.ACTIVE.get(mid)
    check("meeting kept after disconnect", mt is not None and mt.detached_at > 0)
    check("adpcm decoded to 16k pcm", mt is not None and abs(mt.meta["seconds"] - 40 * 2048 / 16000) < 0.01, mt and mt.meta["seconds"])
    with c.websocket_connect("/ws?token=tok123") as ws:
        ws.receive_json(); ws.receive_json()
        ws.send_json({"type": "ptt_start", "id": "mic", "mode": "meeting", "sample_rate": 16000, "codec": "adpcm", "resume": mid})
        for _ in range(6):
            m = ws.receive_json()
            if m.get("type") == "meeting": break
        check("resumed same meeting", m.get("id") == mid, m)
        for _ in range(10): ws.send_bytes(adpcm.encode(pcm, st_))
        ws.send_json({"type": "ptt_end", "id": "mic"})
        time.sleep(3)
    d = c.get(f"/admin/api/meetings/{mid}", headers=H).json()
    check("meeting finished", d["state"] == "done" and abs(d["seconds"] - 50 * 2048 / 16000) < 0.01, d.get("state"))
    a = c.get(f"/admin/api/meetings/{mid}/audio", headers=H); check("meeting audio m4a", a.status_code == 200 and a.headers["content-type"] == "audio/mp4", a.status_code)
    r = c.get(f"/admin/api/meetings/{mid}/audio", headers={**H, "Range": "bytes=0-99"}); check("audio supports range", r.status_code == 206, r.status_code)
    check("delete meeting", c.delete(f"/admin/api/meetings/{mid}", headers=H).status_code == 200)
    check("bad meeting id", c.get("/admin/api/meetings/..%2Fetc", headers=H).status_code in (404, 400))

# composio with a fake backend
calls = []
class R:
    def __init__(s, code, js): s.status_code = code; s._js = js; s.text = json.dumps(js)
    def json(s): return s._js
    def raise_for_status(s):
        if s.status_code >= 400: raise RuntimeError(s.status_code)
async def fake(method, path, k=None, **kw):
    calls.append((method, path, kw.get("params"), kw.get("json")))
    if path == "/auth_configs" and method == "GET": return R(200, {"items": []})
    if path == "/auth_configs" and method == "POST": return R(201, {"auth_config": {"id": "ac_" + kw["json"]["toolkit"]["slug"]}})
    if path == "/connected_accounts/link": return R(201, {"redirect_url": "https://connect.composio.dev/x", "connected_account_id": "ca_1"})
    if path == "/connected_accounts" and method == "GET": return R(200, {"items": [{"id": "ca_1", "status": "ACTIVE", "toolkit": {"slug": "gmail"}}]})
    if path == "/tool_router/session": return R(201, {"session_id": "trs_1", "mcp": {"type": "http", "url": "https://backend.composio.dev/tool_router/trs_1/mcp"}})
    return R(404, {"error": {"message": "nf"}})
composio._req = fake
async def comp():
    r = await composio.set_key("ak_testkey_123456"); check("composio key saved", r["ok"], r)
    r = await composio.connect("gmail"); check("connect link", r.get("url", "").startswith("https://"), r)
    s = await composio.status(); check("gmail active", s["toolkits"]["gmail"]["status"] == "active" and s["mcp"], s)
    e = composio.mcp_entry(); check("mcp entry", e and e["headers"]["x-api-key"] == "ak_testkey_123456" and e["url"].endswith("/mcp"), e)
    from app import integrations
    names = integrations.write_mcp(); check("mcp.json has composio", "composio" in names, names)
    check("mcp.json chmod 600", oct(os.stat(integrations.MCP_FILE).st_mode & 0o777) == "0o600")
asyncio.run(comp())
print(f"== {ok} passed, {bad} failed")
