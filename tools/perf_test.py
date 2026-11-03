"""UI performance: 'ui:' lines while idle, then while talking with a subtitle. Usage: perf_test.py PORT TOKEN"""
import sys, time, json, urllib.request, serial
port, token = sys.argv[1], sys.argv[2]
s = serial.Serial(port, 115200, timeout=0.2)
def read(sec):
    t0 = time.time(); out = []
    while time.time() - t0 < sec:
        l = s.readline().decode(errors="replace").rstrip()
        if l.startswith("ui:"): out.append(l)
    return out
s.write(b"wake\n")
print("== idle"); print("\n".join(read(22)))
req = urllib.request.Request(f"http://192.168.1.10:8770/api/say?token={token}",
    data=json.dumps({"text": "זה משפט ארוך לבדיקת מהירות האנימציה בזמן דיבור עם כתוביות על המסך, כדי לראות כמה פריימים בשנייה אנחנו מקבלים.", "emotion": "happy"}).encode(),
    headers={"content-type": "application/json"}, method="POST")
urllib.request.urlopen(req, timeout=10).read()
print("== talking"); print("\n".join(read(14)))
