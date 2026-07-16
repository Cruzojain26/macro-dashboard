"""
Pulls macro series from FRED (St. Louis Fed) via the keyless fredgraph.csv
endpoint and writes data/fred.json.

Series cover: policy & liquidity (Fed B/S, RRP, TGA, M2), rates & curve,
inflation, growth & labor, credit & financial conditions, global 10Y yields.
"""
import datetime as dt
import json
import time
from io import StringIO
from pathlib import Path

import pandas as pd
import requests

FOLDER = Path(__file__).resolve().parent
OUT = FOLDER / "data" / "fred.json"

FRED_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"

# sid -> (label, frequency_hint, trim_start or None for full history)
SERIES = {
    # --- Policy & liquidity ---
    "DFF":        ("Effective Fed Funds Rate", "d", "1990-01-01"),
    "WALCL":      ("Fed Balance Sheet (Total Assets, $mn)", "w", None),
    "RRPONTSYD":  ("Overnight Reverse Repo ($bn)", "d", None),
    "WTREGEN":    ("Treasury General Account ($bn)", "w", None),
    "M2SL":       ("M2 Money Stock ($bn)", "m", None),
    "ECBASSETSW": ("ECB Balance Sheet (EUR mn)", "w", None),
    "JPNASSETS":  ("BoJ Total Assets (100mn JPY)", "m", None),
    # --- Rates & curve ---
    "DGS3MO":     ("US 3M Yield", "d", "1985-01-01"),
    "DGS2":       ("US 2Y Yield", "d", "1985-01-01"),
    "DGS5":       ("US 5Y Yield", "d", "1985-01-01"),
    "DGS10":      ("US 10Y Yield", "d", "1985-01-01"),
    "DGS30":      ("US 30Y Yield", "d", "1985-01-01"),
    "T10Y2Y":     ("10Y-2Y Spread", "d", None),
    "T10Y3M":     ("10Y-3M Spread", "d", None),
    "DFII10":     ("US 10Y Real Yield (TIPS)", "d", None),
    "T10YIE":     ("10Y Breakeven Inflation", "d", None),
    "T5YIFR":     ("5Y5Y Forward Inflation Expectation", "d", None),
    # --- Inflation ---
    "CPIAUCSL":   ("CPI (Headline, index)", "m", None),
    "CPILFESL":   ("CPI (Core, index)", "m", None),
    "PCEPILFE":   ("Core PCE (index)", "m", None),
    "PPIACO":     ("PPI All Commodities (index)", "m", None),
    # --- Growth & labor ---
    "PAYEMS":     ("Nonfarm Payrolls (thous)", "m", None),
    "UNRATE":     ("Unemployment Rate", "m", None),
    "SAHMREALTIME": ("Sahm Rule Recession Indicator", "m", None),
    "ICSA":       ("Initial Jobless Claims", "w", "2000-01-01"),
    "INDPRO":     ("Industrial Production (index)", "m", None),
    "RSAFS":      ("Retail Sales ($mn)", "m", None),
    "UMCSENT":    ("U. Michigan Consumer Sentiment", "m", None),
    "HOUST":      ("Housing Starts (thous, SAAR)", "m", None),
    "PERMIT":     ("Building Permits (thous, SAAR)", "m", None),
    "WEI":        ("NY Fed Weekly Economic Index", "w", None),
    "GDPC1":      ("Real GDP ($bn 2017, SAAR)", "q", None),
    "USREC":      ("NBER Recession Indicator", "m", None),
    # --- Credit & financial conditions ---
    "BAMLH0A0HYM2": ("US High Yield OAS", "d", None),
    "BAMLC0A0CM":   ("US IG Corporate OAS", "d", None),
    "NFCI":         ("Chicago Fed Financial Conditions", "w", None),
    "STLFSI4":      ("St. Louis Fed Financial Stress", "w", None),
    # --- Global 10Y (OECD, monthly) ---
    "IRLTLT01DEM156N": ("Germany 10Y", "m", None),
    "IRLTLT01JPM156N": ("Japan 10Y", "m", None),
    "IRLTLT01GBM156N": ("UK 10Y", "m", None),
    "INDIRLTLT01STM": ("India 10Y", "m", None),
    # --- India / EM macro (OECD via FRED) ---
    "INDCPIALLMINMEI": ("India CPI (index)", "m", None),
}


def fetch_series(sid: str) -> pd.Series:
    resp = requests.get(FRED_URL.format(sid=sid), timeout=60)
    resp.raise_for_status()
    df = pd.read_csv(StringIO(resp.text))
    df.columns = ["date", "value"]
    df["date"] = pd.to_datetime(df["date"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df = df.dropna(subset=["value"])
    return df.set_index("date")["value"]


def main():
    out = {"generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
           "series": {}}
    failed = []
    for sid, (label, freq, trim) in SERIES.items():
        for attempt in range(3):
            try:
                s = fetch_series(sid)
                break
            except Exception as e:
                if attempt == 2:
                    print(f"  FAIL {sid}: {e}")
                    failed.append(sid)
                    s = None
                else:
                    time.sleep(2 * (attempt + 1))
        if s is None or s.empty:
            continue
        if trim:
            s = s[s.index >= trim]
        out["series"][sid] = {
            "label": label,
            "freq": freq,
            "dates": [d.strftime("%Y-%m-%d") for d in s.index],
            "values": [round(float(v), 4) for v in s.values],
        }
        print(f"  OK {sid}: {len(s)} obs, last {s.index[-1].date()} = {s.iloc[-1]:.2f}")

    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")
    print(f"Wrote {OUT} ({OUT.stat().st_size/1e6:.1f} MB), {len(out['series'])} series, {len(failed)} failed: {failed}")
    return failed


if __name__ == "__main__":
    main()
