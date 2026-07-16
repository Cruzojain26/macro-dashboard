# Global Macro Monitor

A live macro & markets dashboard built the way an economist / fund manager tracks the world:
cycle regime, policy & liquidity, growth & inflation, rates & credit, cross-asset regime
signals, and RRG-style sector/theme rotation for the US and India — with rule-based written
conclusions and asset-allocation tilts generated from the data itself.

**Live dashboard:** served from this repo via GitHub Pages (`index.html`).

## How it works

| Piece | File | Source |
|---|---|---|
| Macro series (42) | `fetch_fred.py` → `data/fred.json` | FRED / St. Louis Fed (keyless CSV endpoint): Fed B/S, RRP, TGA, M2, ECB/BoJ B/S, full US curve, real yields, breakevens, CPI/PCE, payrolls, claims, Sahm rule, WEI, NFCI, ICE BofA credit spreads, OECD global + India 10Y |
| Markets (72) | `fetch_markets.py` → `data/markets.json` | Yahoo Finance: global indices, US style/bonds, FX, commodities, crypto, SPDR sectors, NSE sector indices, theme ETFs |
| Analysis | `analyze.py` → `data/analysis.json` | Investment-clock quadrant (growth × inflation momentum), net USD liquidity impulse, Taylor-rule policy stance, recession-risk score, cross-asset ratios, RRG classification, conclusions + allocation tilts |
| Dashboard | `index.html` | Vanilla JS/SVG, no dependencies, light & dark |

## Updating

GitHub Actions (`.github/workflows/update.yml`) re-runs the whole pipeline every 6 hours
and commits refreshed JSONs; Pages redeploys automatically. To run locally:

```
python fetch_fred.py && python fetch_markets.py && python analyze.py
```

## Data freshness policy

Every series is audited against its source's official publication calendar
(`EXPECTED_AGE` in `analyze.py`) on every pipeline run. The dashboard shows a
freshness strip up top and a full audit table at the bottom: **CURRENT** (within
schedule), **LATE** (publication overdue, with days overdue), **STALE** (more than
2x overdue). Late/stale reads are also injected into the desk conclusions so they
can't be missed. An open browser tab re-fetches data every 10 minutes.

Known standing issues, disclosed on the page:
- **India CPI (OECD via FRED) is stale** — the series stopped updating in Mar-2025
  at the source. No free, machine-readable replacement identified yet (MOSPI has no
  stable public API).
- Yahoo's NSE sector-index feed (`^CNX*`) lags up to a week; the pipeline tops it up
  with the official NSE `allIndices` quote when reachable (NSE blocks non-India IPs,
  so the top-up works on local runs, not GitHub's cloud runners).

## Honest limitations

- Yahoo Finance quotes are delayed up to ~15–20 min at source; FRED series update on
  their official release schedule (e.g. CPI monthly). Decision-support, not execution.
- Bloomberg has no free API. TradingView — even on paid plans — has **no public data
  API** (its APIs are for brokers/charting integration); this dashboard uses the same
  primary sources those terminals aggregate.
- The conclusions are rule-based and transparent — every claim carries its supporting number —
  but they are inputs to judgment, not investment advice.
