"""
抓取 FinLab 所有公司豐富資料，輸出 .company_rich.pkl
包含：公司基本、主要業務、月營收 24 個月、財報 8 季、股利 8 筆、董監持股

用法：
  python site/fetch_company_rich.py
"""
from __future__ import annotations
import sys
import pickle
import warnings
from pathlib import Path
from datetime import datetime

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))

import pandas as pd
from finlab import data

OUT = ROOT / ".company_rich.pkl"


def _safe_float(v):
    try:
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def _safe_str(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    return str(v).strip()


def _roc_to_ad(period: str) -> str:
    """'114年' -> '2025年'；'114年上半年' -> '2025上半年'"""
    s = _safe_str(period)
    if not s:
        return ""
    import re
    m = re.match(r"(\d+)年", s)
    if not m:
        return s
    yr = int(m.group(1)) + 1911
    rest = s[m.end():]
    return f"{yr}{rest}" if rest else f"{yr}"


def main():
    out = {
        "basic": {},       # sym -> dict
        "business": {},    # sym -> str (主要業務)
        "revenue": {},     # sym -> list[{ym, rev, yoy_pct}]  近 24 個月
        "financials": {},  # sym -> list[{q, eps, gm, opm, npm, roe, revenue_mn}] 近 8 季
        "dividends": {},   # sym -> list[{period, cash, stock, ex_date}]  近 8 筆
        "director": {},    # sym -> float  董監持股 %
        "generated_at": datetime.now().isoformat(),
    }

    print("[1/6] 公司基本資料...")
    info = data.get("company_basic_info")
    for _, r in info.iterrows():
        sym = _safe_str(r["symbol"])
        if not sym:
            continue
        out["basic"][sym] = {
            "公司簡稱":    _safe_str(r.get("公司簡稱", "")),
            "公司名稱":    _safe_str(r.get("公司名稱", "")),
            "英文簡稱":    _safe_str(r.get("英文簡稱", "")),
            "產業類別":    _safe_str(r.get("產業類別", "")),
            "市場別":      _safe_str(r.get("市場別", "")),
            "成立日期":    _safe_str(r.get("成立日期", "")).split(" ")[0],
            "上市日期":    _safe_str(r.get("上市日期", "")).split(" ")[0],
            "上櫃日期":    _safe_str(r.get("上櫃日期", "")).split(" ")[0],
            "董事長":      _safe_str(r.get("董事長", "")),
            "總經理":      _safe_str(r.get("總經理", "")).replace("總裁: ", ""),
            "發言人":      _safe_str(r.get("發言人", "")),
            "發言人職稱":  _safe_str(r.get("發言人職稱", "")),
            "住址":        _safe_str(r.get("住址", "")),
            "總機電話":    _safe_str(r.get("總機電話", "")),
            "公司網址":    _safe_str(r.get("公司網址", "")),
            "統編":        _safe_str(r.get("營利事業統一編號", "")),
            "實收資本額":  _safe_float(r.get("實收資本額(元)", 0)),
            "已發行股數":  _safe_float(r.get("已發行普通股數或TDR原發行股數", 0)),
        }
    print(f"       ✓ {len(out['basic'])} 檔")

    print("[2/6] 主要業務...")
    biz = data.get("company_main_business")
    for _, r in biz.iterrows():
        sym = _safe_str(r.get("symbol", ""))
        desc = _safe_str(r.get("主要經營業務", ""))
        if sym and desc:
            out["business"][sym] = desc
    print(f"       ✓ {len(out['business'])} 檔")

    print("[3/6] 月營收 24 個月 + YoY...")
    rev = data.get("monthly_revenue:當月營收")
    rev_yoy = data.get("monthly_revenue:去年當月營收")
    for sym in rev.columns:
        s = rev[sym].tail(24)
        if s.dropna().empty:
            continue
        items = []
        for d, v in s.items():
            if pd.isna(v):
                continue
            v_now = float(v)
            yoy = None
            if sym in rev_yoy.columns:
                ly = rev_yoy.at[d, sym]
                if pd.notna(ly) and float(ly) > 0:
                    yoy = (v_now - float(ly)) / float(ly) * 100
            items.append({
                "ym":  d.strftime("%Y-%m") if hasattr(d, "strftime") else str(d),
                "rev": round(v_now / 1000, 0),  # 千元 → 單位：千元
                "yoy": round(yoy, 2) if yoy is not None else None,
            })
        if items:
            out["revenue"][sym] = items
    print(f"       ✓ {len(out['revenue'])} 檔")

    print("[4/6] 財報指標（EPS / 毛利率 / 營益率 / 淨利率 / ROE）近 8 季...")
    eps = data.get("financial_statement:每股盈餘")
    gm = data.get("fundamental_features:營業毛利率")
    opm = data.get("fundamental_features:營業利益率")
    npm = data.get("fundamental_features:稅後淨利率")
    roe = data.get("fundamental_features:ROE稅後")
    rev_q = data.get("financial_statement:營業收入淨額")
    quarters = eps.index[-8:]
    all_syms = set(eps.columns) | set(gm.columns)
    for sym in all_syms:
        rows = []
        for q in quarters:
            def g(df):
                if sym in df.columns and q in df.index:
                    v = df.at[q, sym]
                    return float(v) if pd.notna(v) else None
                return None
            revm = g(rev_q)
            rows.append({
                "q":       str(q),
                "eps":     g(eps),
                "gm":      g(gm),
                "opm":     g(opm),
                "npm":     g(npm),
                "roe":     g(roe),
                "rev_mn":  round(revm / 1000, 0) if revm else None,  # 千元 → 百萬
            })
        # 至少要有一季有資料才保留
        if any(r["eps"] is not None or r["rev_mn"] is not None for r in rows):
            out["financials"][sym] = rows
    print(f"       ✓ {len(out['financials'])} 檔")

    print("[5/6] 股利公告近 20 筆...")
    da = data.get("dividend_announcement")
    da_sorted = da.sort_values("除息交易日")
    for sym, g in da_sorted.groupby("symbol"):
        sym = _safe_str(sym)
        if not sym:
            continue
        tail = g.tail(20)
        rows = []
        for _, r in tail.iterrows():
            cash = _safe_float(r.get("盈餘分配之股東現金股利(元/股)", 0)) or 0
            stock = _safe_float(r.get("盈餘轉增資配股(元/股)", 0)) or 0
            if cash == 0 and stock == 0:
                continue
            ex = _safe_str(r.get("除息交易日", "")).split(" ")[0]
            rows.append({
                "period": _roc_to_ad(r.get("股利所屬期間", "")),
                "cash":   round(cash, 3),
                "stock":  round(stock, 3),
                "ex_date": ex if ex != "NaT" else "",
            })
        if rows:
            out["dividends"][sym] = rows
    print(f"       ✓ {len(out['dividends'])} 檔")

    print("[6/6] 董監持股比例（%）...")
    dh = data.get("internal_equity_changes:董監持有股數占比")
    # 每檔取最後一筆非 NaN
    for sym in dh.columns:
        sym = _safe_str(sym)
        if not sym:
            continue
        s = dh[sym].dropna()
        if s.empty:
            continue
        v = float(s.iloc[-1])
        # 合理範圍檢查：0-100%；若超過 100 可能資料有誤，跳過
        if 0 <= v <= 100:
            out["director"][sym] = round(v, 2)
    print(f"       ✓ {len(out['director'])} 檔")

    with open(OUT, "wb") as f:
        pickle.dump(out, f)
    size_mb = OUT.stat().st_size / 1024 / 1024
    print(f"\n✓ 已輸出 {OUT.name}（{size_mb:.1f} MB）")


if __name__ == "__main__":
    main()
