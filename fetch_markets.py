"""
Pulls market data (global indices, FX, commodities, US & India sector
indices, theme ETFs) via yfinance and writes data/markets.json.

Per instrument: 5y of daily closes + a stats block (last, % changes over
1d/1w/1m/3m/6m/ytd/1y, 52-week high/low distance, 200dma distance).
"""
import datetime as dt
import json
import math
from pathlib import Path

import pandas as pd
import yfinance as yf

FOLDER = Path(__file__).resolve().parent
OUT = FOLDER / "data" / "markets.json"

# ticker -> (label, group)
TICKERS = {
    # --- Global equity indices ---
    "^GSPC":     ("S&P 500", "equity"),
    "^IXIC":     ("Nasdaq Composite", "equity"),
    "^DJI":      ("Dow Jones", "equity"),
    "^RUT":      ("Russell 2000", "equity"),
    "^NSEI":     ("Nifty 50", "equity"),
    "^NSEBANK":  ("Nifty Bank", "equity"),
    "^N225":     ("Nikkei 225", "equity"),
    "^GDAXI":    ("DAX (Germany)", "equity"),
    "^FTSE":     ("FTSE 100 (UK)", "equity"),
    "^STOXX50E": ("Euro Stoxx 50", "equity"),
    "000001.SS": ("Shanghai Composite", "equity"),
    "^HSI":      ("Hang Seng", "equity"),
    "^KS11":     ("KOSPI (Korea)", "equity"),
    "^BVSP":     ("Bovespa (Brazil)", "equity"),
    "EEM":       ("MSCI Emerging Mkts (EEM)", "equity"),
    # --- US style / size / bonds ---
    "SPY":  ("SPY", "us_style"),
    "QQQ":  ("QQQ (Nasdaq-100)", "us_style"),
    "RSP":  ("S&P Equal Weight", "us_style"),
    "IWM":  ("Russell 2000 ETF", "us_style"),
    "TLT":  ("20+Y Treasuries", "us_style"),
    "HYG":  ("High Yield Bonds", "us_style"),
    "LQD":  ("IG Corp Bonds", "us_style"),
    # --- FX ---
    "DX-Y.NYB": ("US Dollar Index (DXY)", "fx"),
    "EURUSD=X": ("EUR/USD", "fx"),
    "USDJPY=X": ("USD/JPY", "fx"),
    "GBPUSD=X": ("GBP/USD", "fx"),
    "INR=X":    ("USD/INR", "fx"),
    "CNY=X":    ("USD/CNY", "fx"),
    # --- Commodities & crypto ---
    "GC=F":    ("Gold", "commodity"),
    "SI=F":    ("Silver", "commodity"),
    "HG=F":    ("Copper", "commodity"),
    "CL=F":    ("WTI Crude", "commodity"),
    "BZ=F":    ("Brent Crude", "commodity"),
    "NG=F":    ("Natural Gas", "commodity"),
    "PL=F":    ("Platinum", "commodity"),
    "BTC-USD": ("Bitcoin", "commodity"),
    # --- US sectors (SPDR) ---
    "XLK":  ("Technology", "us_sector"),
    "XLF":  ("Financials", "us_sector"),
    "XLE":  ("Energy", "us_sector"),
    "XLV":  ("Health Care", "us_sector"),
    "XLI":  ("Industrials", "us_sector"),
    "XLY":  ("Consumer Discretionary", "us_sector"),
    "XLP":  ("Consumer Staples", "us_sector"),
    "XLU":  ("Utilities", "us_sector"),
    "XLB":  ("Materials", "us_sector"),
    "XLRE": ("Real Estate", "us_sector"),
    "XLC":  ("Communication Services", "us_sector"),
    # --- India sectors (NSE) ---
    "^CNXIT":      ("Nifty IT", "in_sector"),
    "^CNXPHARMA":  ("Nifty Pharma", "in_sector"),
    "^CNXFMCG":    ("Nifty FMCG", "in_sector"),
    "^CNXAUTO":    ("Nifty Auto", "in_sector"),
    "^CNXMETAL":   ("Nifty Metal", "in_sector"),
    "^CNXENERGY":  ("Nifty Energy", "in_sector"),
    "^CNXREALTY":  ("Nifty Realty", "in_sector"),
    "^CNXINFRA":   ("Nifty Infra", "in_sector"),
    "^CNXPSE":     ("Nifty PSE", "in_sector"),
    "^CNXPSUBANK": ("Nifty PSU Bank", "in_sector"),
    "^CNXMEDIA":   ("Nifty Media", "in_sector"),
    # --- Theme / industry ETFs (US-listed, global exposure) ---
    "SMH":  ("Semiconductors", "theme"),
    "XBI":  ("Biotech", "theme"),
    "ITA":  ("Aerospace & Defense", "theme"),
    "XHB":  ("Homebuilders", "theme"),
    "KRE":  ("Regional Banks", "theme"),
    "OIH":  ("Oil Services", "theme"),
    "TAN":  ("Solar", "theme"),
    "URA":  ("Uranium / Nuclear", "theme"),
    "COPX": ("Copper Miners", "theme"),
    "GDX":  ("Gold Miners", "theme"),
    "PAVE": ("US Infrastructure", "theme"),
    "SRVR": ("Data Center REITs", "theme"),
    "IGV":  ("Software", "theme"),
    "ARKK": ("Innovation (ARKK)", "theme"),
}

HORIZONS = {"1w": 5, "1m": 21, "3m": 63, "6m": 126, "1y": 252}


def pct(a, b):
    if a is None or b is None or b == 0 or math.isnan(a) or math.isnan(b):
        return None
    return round((a / b - 1) * 100, 2)


def stats_block(s: pd.Series) -> dict:
    last = float(s.iloc[-1])
    out = {"last": round(last, 4), "chg1d": pct(last, float(s.iloc[-2])) if len(s) > 1 else None}
    for name, n in HORIZONS.items():
        out["chg" + name] = pct(last, float(s.iloc[-n - 1])) if len(s) > n else None
    ytd = s[s.index >= f"{s.index[-1].year}-01-01"]
    prior = s[s.index < f"{s.index[-1].year}-01-01"]
    out["chgytd"] = pct(last, float(prior.iloc[-1])) if len(prior) else None
    yr = s.iloc[-252:] if len(s) > 252 else s
    out["from52wHigh"] = pct(last, float(yr.max()))
    out["from52wLow"] = pct(last, float(yr.min()))
    if len(s) >= 200:
        out["vs200dma"] = pct(last, float(s.iloc[-200:].mean()))
    else:
        out["vs200dma"] = None
    return out


# NSE index name (allIndices API) -> our yfinance ticker. Yahoo's ^CNX* feed
# regularly lags NSE by up to a week; when reachable (Indian IPs — GitHub's
# cloud runners are blocked by NSE), the official NSE quote tops up the series.
NSE_INDEX_MAP = {
    "NIFTY 50": "^NSEI", "NIFTY BANK": "^NSEBANK", "NIFTY IT": "^CNXIT",
    "NIFTY PHARMA": "^CNXPHARMA", "NIFTY FMCG": "^CNXFMCG",
    "NIFTY AUTO": "^CNXAUTO", "NIFTY METAL": "^CNXMETAL",
    "NIFTY ENERGY": "^CNXENERGY", "NIFTY REALTY": "^CNXREALTY",
    "NIFTY INFRASTRUCTURE": "^CNXINFRA", "NIFTY PSE": "^CNXPSE",
    "NIFTY PSU BANK": "^CNXPSUBANK", "NIFTY MEDIA": "^CNXMEDIA",
}


def nse_topup(series_by_ticker: dict) -> list:
    """Append the latest official NSE close where Yahoo's series lags. Best-effort."""
    import requests
    topped = []
    try:
        sess = requests.Session()
        sess.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                             "Accept-Language": "en-US,en;q=0.9"})
        sess.get("https://www.nseindia.com", timeout=15)          # seed Akamai cookies
        resp = sess.get("https://www.nseindia.com/api/allIndices", timeout=15)
        resp.raise_for_status()
        payload = resp.json()
        ts = pd.to_datetime(payload["timestamp"], format="%d-%b-%Y %H:%M")
        bar_date = ts.normalize()
        for row in payload.get("data", []):
            tkr = NSE_INDEX_MAP.get(row.get("index", "").upper())
            if not tkr or tkr not in series_by_ticker:
                continue
            close = row.get("last") or row.get("previousClose")
            if not close:
                continue
            s = series_by_ticker[tkr]
            if bar_date > s.index[-1]:
                s.loc[bar_date] = float(close)
                topped.append(tkr)
    except Exception as e:
        print(f"  NSE top-up skipped ({type(e).__name__}: {e})")
    return topped


def main():
    tickers = list(TICKERS.keys())
    print(f"Downloading {len(tickers)} tickers (5y daily)...")
    raw = yf.download(tickers, period="5y", interval="1d", auto_adjust=True,
                      progress=False, threads=4)["Close"]

    out = {"generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
           "instruments": {}}
    failed = []
    series_by_ticker = {}
    for tkr in TICKERS:
        if tkr not in raw.columns:
            failed.append(tkr)
            continue
        s = raw[tkr].dropna()
        if len(s) < 30:
            failed.append(tkr)
            continue
        series_by_ticker[tkr] = s

    topped = nse_topup(series_by_ticker)
    if topped:
        print(f"  NSE top-up applied to {len(topped)}: {topped}")

    for tkr, s in series_by_ticker.items():
        label, group = TICKERS[tkr]
        out["instruments"][tkr] = {
            "label": label,
            "group": group,
            "dates": [d.strftime("%Y-%m-%d") for d in s.index],
            "values": [round(float(v), 4) for v in s.values],
            "stats": stats_block(s),
        }

    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")
    print(f"Wrote {OUT} ({OUT.stat().st_size/1e6:.1f} MB), "
          f"{len(out['instruments'])} instruments, failed: {failed}")
    return failed


if __name__ == "__main__":
    main()
