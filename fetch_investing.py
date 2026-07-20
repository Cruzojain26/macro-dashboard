"""
Pulls economic-calendar history from Investing.com's public chart endpoint
(sbcharts.investing.com/events_charts/us/<event_id>.json) and writes
data/investing.json.

These series fill gaps the free official APIs can't: LIVE India CPI/GDP/IIP/WPI
(OECD-via-FRED India series are stale) and US ISM PMIs (proprietary, not on FRED).
Timestamps are RELEASE dates (it's a calendar feed), values are the released
actuals. Cloudflare challenges intermittently -> polite retries with backoff.
"""
import datetime as dt
import json
import time
from pathlib import Path

import requests

FOLDER = Path(__file__).resolve().parent
OUT = FOLDER / "data" / "investing.json"

URL = "https://sbcharts.investing.com/events_charts/us/{eid}.json"
# NOTE: keep headers minimal — adding Referer/Origin/full-browser UA triggers
# Cloudflare 403s on this endpoint (verified 2026-07-20); the bare UA passes.
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

# event_id -> (key, label, unit, cadence_days: expected max age of last RELEASE)
EVENTS = {
    973: ("IN_CPI_YOY", "India CPI YoY", "%", 45),
    434: ("IN_GDP_YOY", "India GDP Quarterly YoY", "%", 110),
    435: ("IN_IIP_YOY", "India Industrial Production YoY", "%", 75),
    564: ("IN_WPI_YOY", "India WPI Inflation YoY", "%", 45),
    173: ("US_ISM_MFG", "US ISM Manufacturing PMI", "index", 45),
    176: ("US_ISM_SVC", "US ISM Services PMI", "index", 45),
}


def fetch_event(eid: int):
    # Cloudflare TLS-fingerprints python-requests (403) but passes curl with the
    # same headers (verified 2026-07-20) -> fetch via curl subprocess.
    import subprocess
    for attempt in range(4):
        try:
            r = subprocess.run(
                ["curl", "-s", "--max-time", "30",
                 "-H", f"User-Agent: {HEADERS['User-Agent']}",
                 URL.format(eid=eid)],
                capture_output=True, text=True, timeout=45)
            payload = json.loads(r.stdout)   # challenge pages fail json parse -> retry
            return payload["data"]
        except Exception:
            if attempt == 3:
                raise
            time.sleep(3 * (attempt + 1))


def main():
    # merge-protect: a Cloudflare-blocked run must NEVER wipe previously good
    # series (an empty file broke the dashboard's India section on 2026-07-19).
    prev = {}
    if OUT.exists():
        try:
            prev = json.loads(OUT.read_text(encoding="utf-8")).get("series", {})
        except Exception:
            prev = {}
    out = {"generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
           "source": "Investing.com economic calendar (sbcharts public endpoint)",
           "series": {}}
    failed = []
    for eid, (key, label, unit, cadence) in EVENTS.items():
        try:
            data = fetch_event(eid)
        except Exception as e:
            print(f"  FAIL {key} (event {eid}): {type(e).__name__}: {e}")
            failed.append(key)
            if key in prev:   # keep last good copy; freshness audit will age it honestly
                out["series"][key] = prev[key]
                print(f"       kept previous copy (last {prev[key]['dates'][-1]})")
            continue
        dates, values = [], []
        for ts, val, _ in data:
            if val is None:
                continue
            dates.append(dt.datetime.fromtimestamp(ts / 1000, dt.timezone.utc)
                         .strftime("%Y-%m-%d"))
            values.append(round(float(val), 3))
        out["series"][key] = {"label": label, "unit": unit, "event_id": eid,
                              "cadence_days": cadence, "dates": dates, "values": values}
        print(f"  OK {key}: {len(values)} releases, last {dates[-1]} = {values[-1]}{unit if unit=='%' else ''}")
        time.sleep(2)   # be polite

    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")
    print(f"Wrote {OUT} ({OUT.stat().st_size/1e3:.0f} KB), {len(out['series'])} series, failed: {failed}")
    return failed


if __name__ == "__main__":
    main()
