"""
Intraday live-quote feeder. Runs every 5 min via Task Scheduler; exits
immediately when no covered market is open.

- Indian indices: NSE official allIndices API (real-time, keyless; works from
  Indian IPs).
- Global (US indices, DXY, gold/silver/copper/crude, BTC, INR): Yahoo fast
  quotes (delayed up to ~20 min at source).

Pushes a tiny live.json to the repo's `live` branch via the GitHub contents
API (gh CLI auth). The dashboard polls the raw URL every 60s. The `live`
branch is used so pushes do NOT trigger a GitHub Pages rebuild each tick.
"""
import base64
import datetime as dt
import json
import subprocess
import sys

REPO = "Cruzojain26/macro-dashboard"
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))

YAHOO = [  # (ticker, label)
    ("^GSPC", "S&P 500"), ("^IXIC", "Nasdaq"), ("^RUT", "Russell 2k"),
    ("DX-Y.NYB", "DXY"), ("GC=F", "Gold"), ("SI=F", "Silver"),
    ("HG=F", "Copper"), ("CL=F", "WTI"), ("BTC-USD", "Bitcoin"),
    ("INR=X", "USD/INR"), ("EURUSD=X", "EUR/USD"), ("TLT", "TLT (20Y+)"),
]
NSE_LABELS = {"NIFTY 50": "Nifty 50", "NIFTY BANK": "Bank Nifty",
              "NIFTY IT": "Nifty IT", "NIFTY MIDCAP 100": "Midcap 100",
              "INDIA VIX": "India VIX"}


def us_open(now_utc):
    # EDT Mar-Nov approximation (exact DST edges don't matter for a ticker)
    et = now_utc.astimezone(dt.timezone(dt.timedelta(hours=-4 if 3 <= now_utc.month <= 11 else -5)))
    return et.weekday() < 5 and (9, 30) <= (et.hour, et.minute) <= (16, 10)


def nse_open(now_utc):
    ist = now_utc.astimezone(IST)
    return ist.weekday() < 5 and (9, 10) <= (ist.hour, ist.minute) <= (15, 45)


def nse_quotes():
    import requests
    sess = requests.Session()
    sess.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                         "Accept-Language": "en-US,en;q=0.9"})
    sess.get("https://www.nseindia.com", timeout=15)
    data = sess.get("https://www.nseindia.com/api/allIndices", timeout=15).json()
    out = []
    for row in data.get("data", []):
        lbl = NSE_LABELS.get(row.get("index", "").upper())
        if lbl:
            out.append({"sym": row["index"], "label": lbl,
                        "last": round(float(row["last"]), 2),
                        "chg": round(float(row.get("percentChange") or 0), 2)})
    order = list(NSE_LABELS.values())
    out.sort(key=lambda q: order.index(q["label"]))
    return out


def yahoo_quotes():
    import yfinance as yf
    out = []
    for tkr, lbl in YAHOO:
        try:
            fi = yf.Ticker(tkr).fast_info
            last, prev = fi.last_price, fi.previous_close
            if last and prev:
                out.append({"sym": tkr, "label": lbl, "last": round(float(last), 2),
                            "chg": round((float(last) / float(prev) - 1) * 100, 2)})
        except Exception:
            pass
    return out


def push(payload: dict):
    content = base64.b64encode(json.dumps(payload, separators=(",", ":"))
                               .encode()).decode()
    sha = None
    r = subprocess.run(["gh", "api", f"repos/{REPO}/contents/live.json?ref=live",
                        "--jq", ".sha"], capture_output=True, text=True)
    if r.returncode == 0:
        sha = r.stdout.strip()
    args = ["gh", "api", "-X", "PUT", f"repos/{REPO}/contents/live.json",
            "-f", "branch=live", "-f", "message=live tick",
            "-f", f"content={content}"]
    if sha:
        args += ["-f", f"sha={sha}"]
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode != 0:
        print("push failed:", r.stderr[:400])
        sys.exit(1)


def main():
    now = dt.datetime.now(dt.timezone.utc)
    n_open, u_open = nse_open(now), us_open(now)
    force = "--force" in sys.argv
    if not (n_open or u_open or force):
        print("no covered market open; exiting")
        return
    quotes = []
    if n_open or force:
        try:
            quotes += nse_quotes()
        except Exception as e:
            print(f"NSE quotes failed ({type(e).__name__}) — Yahoo only")
    quotes += yahoo_quotes()
    payload = {"ts": now.isoformat(timespec="seconds"),
               "nse_open": n_open, "us_open": u_open, "quotes": quotes}
    push(payload)
    print(f"pushed {len(quotes)} quotes at {now.astimezone(IST):%H:%M IST} "
          f"(NSE {'open' if n_open else 'closed'}, US {'open' if u_open else 'closed'})")


if __name__ == "__main__":
    main()
