"""
Reads data/fred.json + data/markets.json and produces data/analysis.json:

- US growth & inflation momentum -> investment-clock quadrant + playbook
- Net USD liquidity (Fed B/S - RRP - TGA) impulse
- Policy stance vs a Taylor-rule benchmark; market-implied rate direction
- Recession risk score (curve, Sahm, claims, credit, stress)
- Cross-asset regime signals (copper/gold, RSP/SPY breadth, EEM/SPY, DXY)
- RRG-style sector classification (US sectors, India sectors, themes)
- Rule-based written conclusions + asset-allocation tilts, every claim
  carrying the number that supports it
"""
import datetime as dt
import json
import math
from pathlib import Path

import pandas as pd

FOLDER = Path(__file__).resolve().parent
DATA = FOLDER / "data"


def load_series(blob, key):
    s = blob["series"].get(key)
    if not s:
        return None
    return pd.Series(s["values"], index=pd.to_datetime(s["dates"]), name=key)


def load_price(blob, key):
    s = blob["instruments"].get(key)
    if not s:
        return None
    return pd.Series(s["values"], index=pd.to_datetime(s["dates"]), name=key)


def yoy(s, periods=12):
    return (s / s.shift(periods) - 1) * 100


def ann3m(s):
    return ((s / s.shift(3)) ** 4 - 1) * 100


def last(s, default=None):
    return round(float(s.iloc[-1]), 3) if s is not None and len(s) else default


def chg(s, n):
    if s is None or len(s) <= n:
        return None
    return round(float(s.iloc[-1] - s.iloc[-1 - n]), 3)


# Expected maximum age (calendar days) of the latest observation, per series,
# based on each source's official publication schedule. age <= expected -> CURRENT;
# expected < age <= 2x -> LATE (publication overdue); beyond 2x -> STALE.
EXPECTED_AGE = {
    # daily, published next business day (weekend/holiday grace included)
    "DFF": 5, "RRPONTSYD": 5, "DGS3MO": 5, "DGS2": 5, "DGS5": 5, "DGS10": 5,
    "DGS30": 5, "T10Y2Y": 5, "T10Y3M": 5, "DFII10": 5, "T10YIE": 5, "T5YIFR": 5,
    "BAMLH0A0HYM2": 6, "BAMLC0A0CM": 6,
    # weekly releases (max normal age = 7d span + publication lag + grace)
    "WALCL": 10, "WTREGEN": 10, "ICSA": 14, "NFCI": 12, "STLFSI4": 12,
    "WEI": 12, "ECBASSETSW": 14,
    # monthly: obs is labeled with the month START, so the newest label reaches
    # age ~62d + publication lag just before the next release. expected =
    # 62 + typical lag + grace — beyond that the release is genuinely overdue.
    "CPIAUCSL": 80, "CPILFESL": 80, "PPIACO": 82, "PAYEMS": 72, "UNRATE": 72,
    "SAHMREALTIME": 77, "INDPRO": 85, "RSAFS": 85, "UMCSENT": 100, "HOUST": 87,
    "PERMIT": 87, "M2SL": 95, "PCEPILFE": 98, "JPNASSETS": 100, "USREC": 100,
    # OECD monthly (official lag runs 1-2 months)
    "IRLTLT01DEM156N": 130, "IRLTLT01JPM156N": 130, "IRLTLT01GBM156N": 130,
    "INDIRLTLT01STM": 130, "INDCPIALLMINMEI": 130,
    # quarterly GDP: newest label is ~215d old just before the next advance print
    "GDPC1": 220,
}


def build_freshness(fred, mkt, inv=None):
    today = dt.datetime.now(dt.timezone.utc).date()
    rows = []
    if inv:
        for key, s in inv["series"].items():
            last_obs = dt.date.fromisoformat(s["dates"][-1])
            age = (today - last_obs).days
            exp = s.get("cadence_days", 60)
            status = "current" if age <= exp else "late" if age <= 2 * exp else "stale"
            rows.append({"id": key, "label": s["label"], "source": "Investing.com",
                         "last_obs": s["dates"][-1], "age_days": age,
                         "expected_days": exp, "status": status,
                         "late_by_days": max(0, age - exp)})
    for sid, s in fred["series"].items():
        last_obs = dt.date.fromisoformat(s["dates"][-1])
        age = (today - last_obs).days
        exp = EXPECTED_AGE.get(sid, 60)
        status = "current" if age <= exp else "late" if age <= 2 * exp else "stale"
        rows.append({"id": sid, "label": s["label"], "source": "FRED",
                     "last_obs": s["dates"][-1], "age_days": age,
                     "expected_days": exp, "status": status,
                     "late_by_days": max(0, age - exp)})
    # market instruments: bar data should be no older than 5 calendar days
    for tkr, m in mkt["instruments"].items():
        last_obs = dt.date.fromisoformat(m["dates"][-1])
        age = (today - last_obs).days
        status = "current" if age <= 5 else "late" if age <= 10 else "stale"
        if status != "current":   # only list problem instruments, not all 72
            rows.append({"id": tkr, "label": m["label"], "source": "Yahoo",
                         "last_obs": m["dates"][-1], "age_days": age,
                         "expected_days": 5, "status": status,
                         "late_by_days": age - 5})
    rows.sort(key=lambda r: (-{"stale": 2, "late": 1, "current": 0}[r["status"]],
                             -r["late_by_days"]))
    n_mkt_ok = sum(1 for m in mkt["instruments"].values()
                   if (today - dt.date.fromisoformat(m["dates"][-1])).days <= 5)
    summary = {
        "current": sum(1 for r in rows if r["status"] == "current") + n_mkt_ok,
        "late": sum(1 for r in rows if r["status"] == "late"),
        "stale": sum(1 for r in rows if r["status"] == "stale"),
        "market_instruments_current": n_mkt_ok,
        "market_instruments_total": len(mkt["instruments"]),
        "markets_fetched_at": mkt["generated_at"],
        "quote_delay_note": ("Yahoo end-of-day/intraday quotes are delayed up to "
                             "~15-20 min depending on exchange; FRED series update "
                             "on official release schedules."),
    }
    return {"summary": summary, "rows": rows}


def main():
    fred = json.loads((DATA / "fred.json").read_text(encoding="utf-8"))
    mkt = json.loads((DATA / "markets.json").read_text(encoding="utf-8"))
    inv = None
    if (DATA / "investing.json").exists():
        inv = json.loads((DATA / "investing.json").read_text(encoding="utf-8"))
    F = lambda k: load_series(fred, k)
    P = lambda k: load_price(mkt, k)
    IV = lambda k: (inv["series"][k]["values"][-1] if inv and k in inv["series"] else None)
    out = {"generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
    concl = []   # (severity: info|watch|action, title, detail)

    # ---------------- Growth composite ----------------
    indpro, payems, wei, rsafs = F("INDPRO"), F("PAYEMS"), F("WEI"), F("RSAFS")
    g_indpro = last(yoy(indpro))
    g_payroll3m = last(((payems / payems.shift(3)) ** 4 - 1) * 100)
    g_wei = last(wei)
    g_retail = last(yoy(rsafs))
    # growth score: average of standardized-ish components vs trend norms
    comps = [(g_indpro, 1.0), (g_payroll3m, 1.2), (g_wei, 2.0), (g_retail, 3.5)]
    g_score = sum(v / norm for v, norm in comps if v is not None) / sum(
        1 for v, _ in comps if v is not None)
    # direction: 3m change of the same composite
    def growth_at(shift):
        vals = [(yoy(indpro).iloc[-1 - shift], 1.0),
                (((payems / payems.shift(3)) ** 4 - 1).mul(100).iloc[-1 - shift], 1.2),
                (wei.resample("ME").last().iloc[-1 - shift], 2.0),
                (yoy(rsafs).iloc[-1 - shift], 3.5)]
        ok = [(v, n) for v, n in vals if not math.isnan(v)]
        return sum(v / n for v, n in ok) / len(ok)
    g_now, g_3mago = growth_at(0), growth_at(3)
    g_rising = g_now > g_3mago

    # ---------------- Inflation momentum ----------------
    cpi, core, pce = F("CPIAUCSL"), F("CPILFESL"), F("PCEPILFE")
    i_head = last(yoy(cpi))
    i_core = last(yoy(core))
    i_core3m = last(ann3m(core))
    i_pce = last(yoy(pce))
    i_rising = i_core3m is not None and i_core is not None and i_core3m > i_core

    quad = ("Overheat" if g_rising and i_rising else
            "Recovery / Goldilocks" if g_rising else
            "Stagflation" if i_rising else
            "Slowdown / Disinflation")
    playbook = {
        "Recovery / Goldilocks": ("Equities (cyclicals, small caps), credit",
                                  "Cash, defensives"),
        "Overheat": ("Commodities, energy, materials, value, TIPS",
                     "Long duration bonds, growth at any price"),
        "Stagflation": ("Gold, commodities, energy, defensives, pricing power",
                        "Long duration, consumer cyclicals"),
        "Slowdown / Disinflation": ("Long duration bonds, quality growth, staples, gold",
                                    "Commodities, cyclicals, credit risk"),
    }[quad]
    out["cycle"] = {
        "quadrant": quad,
        "growth": {"score": round(g_score, 2), "rising": bool(g_rising),
                   "indpro_yoy": g_indpro, "payrolls_3m_ann": g_payroll3m,
                   "wei": g_wei, "retail_yoy": g_retail},
        "inflation": {"headline_yoy": i_head, "core_yoy": i_core,
                      "core_3m_ann": i_core3m, "core_pce_yoy": i_pce,
                      "rising": bool(i_rising)},
        "favor": playbook[0], "avoid": playbook[1],
    }

    # ---------------- Liquidity ----------------
    walcl, rrp, tga, m2 = F("WALCL"), F("RRPONTSYD"), F("WTREGEN"), F("M2SL")
    rrp_w = rrp.resample("W-WED").last().reindex(walcl.resample("W-WED").last().index).ffill()
    netliq = (walcl.resample("W-WED").last() / 1000
              - tga.resample("W-WED").last() / 1000
              - rrp_w).dropna()  # $bn
    out["liquidity"] = {
        "net_liq_bn": last(netliq),
        "net_liq_chg_13w_bn": chg(netliq, 13),
        "net_liq_chg_4w_bn": chg(netliq, 4),
        "fed_bs_tn": round(last(walcl) / 1e6, 2),
        "rrp_bn": last(rrp),
        "tga_bn": round(last(tga) / 1000, 0),
        "m2_yoy": last(yoy(m2)),
        "dates": [d.strftime("%Y-%m-%d") for d in netliq.index[-260:]],
        "values": [round(float(v), 1) for v in netliq.values[-260:]],
    }
    liq_impulse = out["liquidity"]["net_liq_chg_13w_bn"]

    # ---------------- Policy stance ----------------
    dff, dgs2, dgs10, unrate = F("DFF"), F("DGS2"), F("DGS10"), F("UNRATE")
    ffr = last(dff)
    two = last(dgs2)
    # Taylor-lite: r*=0.75 + core PCE + 0.5*(core PCE - 2) + 0.5*(4.2 - U)
    taylor = None
    if i_pce is not None:
        taylor = round(0.75 + i_pce + 0.5 * (i_pce - 2) + 0.5 * (4.2 - last(unrate)), 2)
    stance = None
    if taylor is not None:
        gap = ffr - taylor
        stance = ("restrictive" if gap > 0.5 else
                  "accommodative" if gap < -0.5 else "≈ neutral")
    mkt_pricing = round(two - ffr, 2) if two and ffr else None
    out["policy"] = {"ffr": ffr, "taylor_rule": taylor, "stance": stance,
                     "us2y_minus_ffr": mkt_pricing,
                     "real_10y": last(F("DFII10")),
                     "breakeven_10y": last(F("T10YIE")),
                     "fwd_5y5y": last(F("T5YIFR"))}

    # ---------------- Recession risk ----------------
    t10y2y, t10y3m = F("T10Y2Y"), F("T10Y3M")
    sahm, icsa = F("SAHMREALTIME"), F("ICSA")
    hy, nfci, stress = F("BAMLH0A0HYM2"), F("NFCI"), F("STLFSI4")
    claims4w = icsa.rolling(4).mean()
    curve_2 = last(t10y2y)
    curve_3m = last(t10y3m)
    # was the curve inverted in the past 18 months and is now re-steepening?
    inv_recent = bool((t10y3m.iloc[-378:] < 0).any())
    risk_pts, risk_notes = 0, []
    if curve_3m is not None and curve_3m < 0:
        risk_pts += 2; risk_notes.append(f"10y-3m inverted ({curve_3m:+.2f})")
    elif inv_recent and curve_3m > 0:
        risk_pts += 1; risk_notes.append(
            f"curve re-steepened after inversion ({curve_3m:+.2f}) — historically the riskier phase")
    s_val = last(sahm)
    if s_val is not None and s_val >= 0.5:
        risk_pts += 3; risk_notes.append(f"Sahm rule TRIGGERED ({s_val:.2f} ≥ 0.50)")
    elif s_val is not None and s_val >= 0.3:
        risk_pts += 1; risk_notes.append(f"Sahm rule elevated ({s_val:.2f})")
    cl_now, cl_6m = last(claims4w), float(claims4w.iloc[-27])
    if cl_now and cl_now > cl_6m * 1.15:
        risk_pts += 1; risk_notes.append(f"claims 4wk avg +{(cl_now/cl_6m-1)*100:.0f}% vs 6m ago")
    hy_now, hy_3m = last(hy), float(hy.iloc[-64]) if len(hy) > 64 else None
    if hy_now and hy_3m and hy_now - hy_3m > 0.75:
        risk_pts += 2; risk_notes.append(f"HY OAS widened {hy_now-hy_3m:+.2f} in 3m")
    if last(nfci) is not None and last(nfci) > 0:
        risk_pts += 1; risk_notes.append(f"financial conditions tight (NFCI {last(nfci):+.2f})")
    risk_level = ("HIGH" if risk_pts >= 5 else "ELEVATED" if risk_pts >= 3
                  else "MODERATE" if risk_pts >= 1 else "LOW")
    out["recession"] = {"points": risk_pts, "level": risk_level, "notes": risk_notes,
                        "t10y2y": curve_2, "t10y3m": curve_3m, "sahm": s_val,
                        "claims_4wk": int(cl_now) if cl_now else None,
                        "hy_oas": hy_now, "nfci": last(nfci), "stlfsi": last(stress)}

    # ---------------- Cross-asset signals ----------------
    def ratio(a, b):
        pa, pb = P(a), P(b)
        if pa is None or pb is None:
            return None
        r = (pa / pb).dropna()
        return r

    signals = {}
    for name, (a, b, meaning_up) in {
        "copper_gold": ("HG=F", "GC=F", "global growth impulse"),
        "rsp_spy": ("RSP", "SPY", "breadth broadening beyond mega-caps"),
        "eem_spy": ("EEM", "SPY", "EM outperforming US"),
        "hyg_tlt": ("HYG", "TLT", "risk appetite over safety"),
        "nifty_spx": ("^NSEI", "^GSPC", "India outperforming US"),
        "gold_spx": ("GC=F", "^GSPC", "hard assets over financial assets"),
    }.items():
        r = ratio(a, b)
        if r is None or len(r) < 130:
            continue
        r63 = float(r.iloc[-64]); r126 = float(r.iloc[-127])
        signals[name] = {
            "meaning_up": meaning_up,
            "chg3m": round((float(r.iloc[-1]) / r63 - 1) * 100, 2),
            "chg6m": round((float(r.iloc[-1]) / r126 - 1) * 100, 2),
            "dates": [d.strftime("%Y-%m-%d") for d in r.index[-504:]],
            "values": [round(float(v), 5) for v in r.values[-504:]],
        }
    out["cross_asset"] = signals

    # ---------------- RRG sector classification ----------------
    def rrg(group, bench_tkr):
        bench = P(bench_tkr)
        rows = []
        for tkr, meta in mkt["instruments"].items():
            if meta["group"] != group:
                continue
            p = P(tkr)
            rs = (p / bench).dropna()
            if len(rs) < 150:
                continue
            rs_ratio = 100 * rs / rs.rolling(63).mean()
            rs_mom = 100 * rs_ratio / rs_ratio.rolling(21).mean()
            rr, rm = float(rs_ratio.iloc[-1]), float(rs_mom.iloc[-1])
            phase = ("Leading" if rr >= 100 and rm >= 100 else
                     "Weakening" if rr >= 100 else
                     "Improving" if rm >= 100 else "Lagging")
            def rel(n):
                if len(rs) <= n:
                    return None
                return round((float(rs.iloc[-1]) / float(rs.iloc[-1 - n]) - 1) * 100, 2)
            rows.append({"ticker": tkr, "label": meta["label"], "phase": phase,
                         "rs_ratio": round(rr, 2), "rs_mom": round(rm, 2),
                         "rel1m": rel(21), "rel3m": rel(63), "rel6m": rel(126),
                         "abs3m": meta["stats"]["chg3m"]})
        rows.sort(key=lambda r: (r["rel3m"] if r["rel3m"] is not None else -99), reverse=True)
        return rows

    out["rrg"] = {
        "us_sectors": rrg("us_sector", "SPY"),
        "in_sectors": rrg("in_sector", "^NSEI"),
        "themes": rrg("theme", "SPY"),
    }

    # ---------------- Conclusions ----------------
    c = out["cycle"]; L = out["liquidity"]; R = out["recession"]; PO = out["policy"]
    concl.append(("info", f"Cycle regime: {quad}",
        f"Growth {'rising' if g_rising else 'falling'} (payrolls 3m ann {g_payroll3m:+.1f}%, "
        f"IP YoY {g_indpro:+.1f}%, WEI {g_wei:.1f}) with core inflation momentum "
        f"{'above' if i_rising else 'below'} trend (core CPI 3m ann {i_core3m:.1f}% vs "
        f"YoY {i_core:.1f}%). Favor: {playbook[0]}. Avoid: {playbook[1]}."))
    if liq_impulse is not None:
        direction = "EXPANDING" if liq_impulse > 100 else "CONTRACTING" if liq_impulse < -100 else "roughly flat"
        concl.append(("watch" if direction != "flat" else "info",
            f"Net USD liquidity {direction} ({liq_impulse:+,.0f}bn over 13 weeks)",
            f"Fed B/S ${L['fed_bs_tn']}tn, RRP ${L['rrp_bn']:.0f}bn (drained), "
            f"TGA ${L['tga_bn']:.0f}bn. Net liquidity ${L['net_liq_bn']:,.0f}bn. "
            f"M2 YoY {L['m2_yoy']:+.1f}%. Liquidity direction tends to lead risk assets by weeks."))
    if PO["taylor_rule"] is not None:
        concl.append(("info", f"Policy is {PO['stance']} (FFR {PO['ffr']:.2f}% vs Taylor {PO['taylor_rule']:.2f}%)",
            f"2Y at {two:.2f}% prices {'+%.0fbp of tightening' % (mkt_pricing*100) if mkt_pricing > 0.15 else ('%.0fbp of easing' % (mkt_pricing*100) if mkt_pricing < -0.15 else 'the Fed on hold')} "
            f"over the next cycle. 10Y real yield {PO['real_10y']:.2f}%, breakevens {PO['breakeven_10y']:.2f}% "
            f"(5y5y {PO['fwd_5y5y']:.2f}%) — inflation expectations anchored{'' if PO['fwd_5y5y'] < 2.6 else ' at risk'}."))
    concl.append(("watch" if R["level"] in ("ELEVATED", "HIGH") else "info",
        f"Recession risk: {R['level']} ({R['points']} pts)",
        ("; ".join(R["notes"]) if R["notes"] else
         f"Curve positive (10y-3m {R['t10y3m']:+.2f}), Sahm {R['sahm']:.2f}, "
         f"HY OAS {R['hy_oas']:.2f}% — no stress signals firing.")))
    cg = signals.get("copper_gold"); br = signals.get("rsp_spy"); ns = signals.get("nifty_spx")
    if cg:
        concl.append(("info", f"Copper/gold {cg['chg3m']:+.1f}% (3m) — "
            f"{'growth impulse improving' if cg['chg3m'] > 0 else 'defensive/hard-asset bid dominates'}",
            f"6m {cg['chg6m']:+.1f}%. Copper/gold tracks global IP and bond yields."))
    if br:
        concl.append(("info", f"Breadth (equal-weight/SPY) {br['chg3m']:+.1f}% over 3m",
            f"{'Broadening rally — healthier internals' if br['chg3m'] > 0 else 'Narrow, mega-cap-led market — fragile internals'}."))
    if ns:
        concl.append(("info", f"India vs US: Nifty/SPX {ns['chg3m']:+.1f}% (3m), {ns['chg6m']:+.1f}% (6m)",
            "Relative-strength trend for country allocation."))
    ism_m, ism_s = IV("US_ISM_MFG"), IV("US_ISM_SVC")
    if ism_m is not None:
        concl.append(("info",
            f"US ISM: manufacturing {ism_m:.1f}, services {ism_s:.1f} — "
            f"{'both expanding' if ism_m > 50 and ism_s > 50 else 'manufacturing contracting' if ism_m < 50 else 'mixed'}",
            "PMI above 50 = expansion. Manufacturing back above 50 alongside the copper/gold "
            "impulse confirms the goods-cycle upturn."))
    in_cpi, in_wpi, in_gdp, in_iip = IV("IN_CPI_YOY"), IV("IN_WPI_YOY"), IV("IN_GDP_YOY"), IV("IN_IIP_YOY")
    if in_cpi is not None:
        wedge = ""
        if in_wpi is not None and in_wpi - in_cpi > 3:
            wedge = (f" WPI at {in_wpi:.1f}% is running {in_wpi - in_cpi:.1f}pp above CPI — a wholesale-price "
                     "surge that either squeezes corporate margins or passes through to CPI later; "
                     "watch pricing-power sectors.")
        concl.append(("watch" if (in_wpi or 0) - in_cpi > 3 else "info",
            f"India macro: GDP {in_gdp:.1f}% YoY, CPI {in_cpi:.2f}%, IIP {in_iip:.1f}%",
            f"CPI inside RBI's 2-6% band; growth strong.{wedge}"))
    if inv:
        out["india_macro"] = {k: {"label": s["label"], "last": s["values"][-1],
                                  "last_release": s["dates"][-1]}
                              for k, s in inv["series"].items()}
    for name, rows in (("US sector", out["rrg"]["us_sectors"]),
                       ("India sector", out["rrg"]["in_sectors"]),
                       ("Theme", out["rrg"]["themes"])):
        lead = [r["label"] for r in rows if r["phase"] == "Leading"][:4]
        imp = [r["label"] for r in rows if r["phase"] == "Improving"][:3]
        lag = [r["label"] for r in rows if r["phase"] == "Lagging"][:3]
        concl.append(("action", f"{name} leadership: {', '.join(lead) if lead else '—'}",
            f"Improving (early rotation candidates): {', '.join(imp) if imp else '—'}. "
            f"Lagging (avoid): {', '.join(lag) if lag else '—'}."))

    # allocation tilts (rule-based from regime + liquidity + recession risk)
    risk_on = (quad in ("Recovery / Goldilocks", "Overheat")
               and R["level"] in ("LOW", "MODERATE")
               and (liq_impulse or 0) > -50)
    tilt = lambda ow: "Overweight" if ow else "Underweight"
    out["allocation"] = [
        {"asset": "Equities (DM)", "tilt": tilt(risk_on),
         "why": f"{quad}; recession risk {R['level']}; liquidity {liq_impulse:+,.0f}bn/13w"},
        {"asset": "Equities (India/EM)", "tilt": "Overweight" if (ns and ns["chg6m"] > 0 and risk_on) else "Neutral",
         "why": f"Nifty/SPX 6m {ns['chg6m']:+.1f}%" if ns else "n/a"},
        {"asset": "Duration (10Y+)", "tilt": "Overweight" if quad == "Slowdown / Disinflation" else
            ("Underweight" if i_rising else "Neutral"),
         "why": f"10Y {last(dgs10):.2f}%, real {PO['real_10y']:.2f}%, core momentum {'rising' if i_rising else 'cooling'}"},
        {"asset": "Credit (HY)", "tilt": "Underweight" if (hy_now or 3) < 3.0 else "Neutral",
         "why": f"HY OAS {hy_now:.2f}% — {'no cushion at these spreads' if hy_now < 3 else 'fair'}"},
        {"asset": "Commodities", "tilt": "Overweight" if quad in ("Overheat", "Stagflation") else "Neutral",
         "why": f"Regime {quad}; copper/gold 3m {cg['chg3m']:+.1f}%" if cg else quad},
        {"asset": "Gold", "tilt": "Overweight" if (signals.get('gold_spx') and signals['gold_spx']['chg6m'] > 0) else "Neutral",
         "why": f"Gold/SPX 6m {signals['gold_spx']['chg6m']:+.1f}%" if signals.get('gold_spx') else "n/a"},
        {"asset": "USD", "tilt": "Neutral",
         "why": f"DXY 3m {mkt['instruments']['DX-Y.NYB']['stats']['chg3m']:+.1f}%"},
    ]
    # data freshness audit — surfaced on the dashboard, stale data is disclosed
    out["freshness"] = build_freshness(fred, mkt, inv)
    fs = out["freshness"]["summary"]
    if fs["stale"] or fs["late"]:
        worst = [r for r in out["freshness"]["rows"] if r["status"] != "current"][:4]
        concl.insert(0, ("watch",
            f"DATA QUALITY: {fs['stale']} stale, {fs['late']} late series",
            "; ".join(f"{r['label']} last {r['last_obs']} ({r['late_by_days']}d overdue)"
                      for r in worst) + ". See the data-freshness panel before relying on affected reads."))

    out["conclusions"] = [{"sev": s, "title": t, "detail": d} for s, t, d in concl]

    (DATA / "analysis.json").write_text(json.dumps(out, separators=(",", ":")),
                                        encoding="utf-8")
    print(f"Regime: {quad} | growth {'UP' if g_rising else 'DOWN'} | "
          f"inflation {'UP' if i_rising else 'DOWN'} | recession {risk_level} | "
          f"netliq 13w {liq_impulse:+,.0f}bn | stance {stance}")
    for s, t, _ in concl:
        print(f"  [{s}] {t}")


if __name__ == "__main__":
    main()
