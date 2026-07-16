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

## Honest limitations

- Yahoo Finance quotes are delayed; FRED series update on their official release schedule
  (e.g. CPI monthly). This is a *decision-support* dashboard, not an execution terminal.
- Bloomberg/TradingView have no free APIs; this uses the same primary sources they aggregate.
- The conclusions are rule-based and transparent — every claim carries its supporting number —
  but they are inputs to judgment, not investment advice.
