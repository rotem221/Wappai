"""Battery history and runtime estimate.

The AXP2101 has a fuel gauge (percent) but no current sensor, so the battery's real capacity can't be read directly.
Instead every status report (once a minute) is logged, and the discharge rate of the current (or last) unplugged
stretch gives "about N hours left" and "about M hours from full" — which is what actually matters to the owner.
File: DATA_DIR/battery.csv  (epoch, pct, mv, usb, charging)
"""
import csv
import time

from .. import config

FILE = config.DATA_DIR / "battery.csv"
KEEP_S = 30 * 24 * 3600
MIN_SPAN_S = 20 * 60          # need at least 20 minutes ...
MIN_DROP = 2                  # ... and 2 % of discharge before estimating
_last = {"t": 0.0}


def record(b: dict):
    if not b or b.get("pct") is None:
        return
    now = time.time()
    if now - _last["t"] < 50:  # status comes once a minute; ignore duplicates from hello/status bursts
        return
    _last["t"] = now
    new = not FILE.exists()
    with FILE.open("a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["t", "pct", "mv", "usb", "charging"])
        w.writerow([int(now), int(b.get("pct", 0)), int(b.get("mv", 0)), int(bool(b.get("usb"))), int(bool(b.get("charging")))])
    if FILE.stat().st_size > 2_000_000:
        _trim()


def _rows() -> list[tuple]:
    try:
        with FILE.open() as f:
            r = csv.reader(f)
            next(r, None)
            return [(int(a), int(p), int(m), int(u), int(c)) for a, p, m, u, c in r]
    except (OSError, ValueError):
        return []


def _trim():
    cut = time.time() - KEEP_S
    rows = [x for x in _rows() if x[0] >= cut]
    with FILE.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["t", "pct", "mv", "usb", "charging"])
        w.writerows(rows)


def _last_discharge(rows):
    """Rows of the most recent unplugged stretch (gaps over 30 min — e.g. deep sleep — are kept: they are real usage)."""
    seg = []
    for row in reversed(rows):
        if row[3]:            # on USB: stretch boundary
            if seg:
                break
            continue
        seg.append(row)
    return list(reversed(seg))


def estimate() -> dict:
    """{"rate_pct_h", "hours_left", "hours_full", "span_h"} from the latest unplugged stretch, or {} if not enough data."""
    rows = _rows()
    seg = _last_discharge(rows)
    if len(seg) < 3:
        return {}
    span = seg[-1][0] - seg[0][0]
    drop = seg[0][1] - seg[-1][1]
    if span < MIN_SPAN_S or drop < MIN_DROP:
        return {}
    # least squares slope of pct over time
    n = len(seg)
    mt = sum(r[0] for r in seg) / n
    mp = sum(r[1] for r in seg) / n
    num = sum((r[0] - mt) * (r[1] - mp) for r in seg)
    den = sum((r[0] - mt) ** 2 for r in seg) or 1
    rate = -num / den * 3600          # % per hour
    if rate <= 0.05:
        return {}
    cur = rows[-1][1]
    return {"rate_pct_h": round(rate, 2), "hours_left": round(cur / rate, 1), "hours_full": round(100 / rate, 1),
            "span_h": round(span / 3600, 1), "unplugged_now": not rows[-1][3]}


def summary(b: dict | None) -> str:
    if not b or b.get("pct") is None:
        return ""
    s = f"סוללת המכשיר {b.get('pct')}%"
    if b.get("charging"):
        s += " (בטעינה)"
    elif b.get("usb"):
        s += " (מחובר לחשמל)"
    e = estimate()
    if e and not b.get("usb"):
        s += f", מספיקה לעוד כ-{e['hours_left']:.0f} שעות בקצב הנוכחי"
    elif e:
        s += f" (סוללה מלאה מחזיקה כ-{e['hours_full']:.0f} שעות לפי הפריקה האחרונה)"
    return s
