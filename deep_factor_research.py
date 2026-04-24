"""
深度因子研究 - 從全市場1800檔找飆股族群
新增因子：外資/投信連買天數、營收連續成長、價格位階、量價同步、融資變化
"""
import warnings
warnings.filterwarnings("ignore")
import sys, os
import numpy as np
import pandas as pd
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from finlab import data
from concept_groups import CONCEPT_GROUPS


def main():
    close = data.get('price:收盤價')
    amount = data.get('price:成交金額')
    foreign = data.get('institutional_investors_trading_summary:外陸資買賣超股數(不含外資自營商)')
    trust = data.get('institutional_investors_trading_summary:投信買賣超股數')
    rev_yoy = data.get('monthly_revenue:去年同月增減(%)')
    name_map = data.get('company_basic_info').set_index('symbol')['公司簡稱'].to_dict()

    s2g = {}
    for g, members in CONCEPT_GROUPS.items():
        for s in members:
            s2g.setdefault(s, []).append(g)

    # ── 基礎因子 ──
    mom20 = close.pct_change(20)
    mom10 = close.pct_change(10)
    mom5 = close.pct_change(5)
    vol_ratio = amount.rolling(10).mean() / amount.shift(10).rolling(10).mean()
    foreign_amt = (foreign * close).rolling(20).sum()
    foreign_amt10 = (foreign * close).rolling(10).sum()
    trust_amt = (trust * close).rolling(10).sum()
    rev_daily = rev_yoy.reindex(close.index, method='ffill')
    liquidity = amount.rolling(20).mean()
    high_252 = close.rolling(252).max()
    near_high = close / high_252

    # ── 新因子 ──
    foreign_buy_streak = (foreign > 0).rolling(20).sum()
    trust_buy_streak = (trust > 0).rolling(20).sum()

    rev_positive = (rev_yoy > 0).astype(int)
    rev_streak = rev_positive.copy()
    for i in range(1, len(rev_streak)):
        rev_streak.iloc[i] = rev_streak.iloc[i] * (rev_streak.iloc[i-1] + rev_streak.iloc[i])
    rev_streak_daily = rev_streak.reindex(close.index, method='ffill')

    low_252 = close.rolling(252).min()
    price_position = (close - low_252) / (high_252 - low_252)

    vol_price_sync = close.pct_change(10) * amount.pct_change(10)

    try:
        margin = data.get('margin_transactions:融資使用率')
        margin_chg = margin - margin.shift(20)
        margin_daily = margin_chg
        print('融資使用率 OK')
    except:
        margin_daily = None
        print('融資使用率 不可用')

    try:
        foreign_hold = data.get('foreign_investors_shareholding:全體外資及陸資持股比率')
        foreign_hold_chg = foreign_hold - foreign_hold.shift(20)
        foreign_hold_daily = foreign_hold_chg.reindex(close.index, method='ffill')
        print('外資持股比例 OK')
    except:
        foreign_hold_daily = None
        print('外資持股比例 不可用')

    print('因子計算完成\n')

    all_factors_map = {
        'mom20': mom20, 'mom10': mom10, 'mom5': mom5,
        'vol': vol_ratio, 'for20': foreign_amt, 'for10': foreign_amt10,
        'trust': trust_amt, 'rev': rev_daily, 'high': near_high,
        'for_stk': foreign_buy_streak, 'tru_stk': trust_buy_streak,
        'rev_stk': rev_streak_daily, 'pos': price_position,
        'vp': vol_price_sync,
    }
    if foreign_hold_daily is not None:
        all_factors_map['for_hold'] = foreign_hold_daily
    if margin_daily is not None:
        all_factors_map['margin'] = margin_daily

    # ── 單因子測試 ──
    def test_single(factor, top_n=7, hold=10, min_amt=5e7):
        start_idx = close.index.get_loc(close.loc['2020-01-01':].index[0])
        sample_dates = close.index[start_idx::hold]
        prets, cls = [], []

        for dt in sample_dates:
            liq = liquidity.loc[dt].dropna()
            uni = liq[liq >= min_amt].index.tolist()
            if len(uni) < 50 or dt not in factor.index:
                continue
            vals = factor.loc[dt].reindex(uni).dropna()
            if len(vals) < 20:
                continue
            sel = vals.sort_values(ascending=False).head(top_n).index.tolist()
            cls.append(sum(1 for s in sel if s in s2g) / top_n)

            dt_i = close.index.get_loc(dt)
            si = min(dt_i + hold, len(close) - 1)
            rs = []
            for s in sel:
                try:
                    bp, sp = close.iloc[dt_i+1][s], close.iloc[si][s]
                    if pd.notna(bp) and pd.notna(sp) and bp > 0:
                        rs.append((sp-bp)/bp)
                except:
                    pass
            if rs:
                prets.append(np.mean(rs))
        if not prets:
            return None
        sharpe = np.mean(prets) / np.std(prets) * np.sqrt(252/hold) if np.std(prets) > 0 else 0
        return np.mean(prets)*100, sharpe, np.mean(cls)*100, sum(1 for r in prets if r > 0)/len(prets)*100

    print(f"{'='*70}")
    print(f"  單因子排行（雙週頻，7檔，流動性>5000萬）")
    print(f"{'='*70}")
    print(f"{'因子':<20} {'期均報酬':>8} {'Sharpe':>7} {'命中族群':>7} {'正報酬':>7}")
    print('-'*55)

    for fname, f in all_factors_map.items():
        r = test_single(f)
        if r:
            ar, sh, cl, win = r
            tag = ' ★' if sh > 0.5 and cl > 35 else (' ▲' if sh > 0.5 else '')
            print(f"{fname:<20} {ar:>+7.2f}% {sh:>6.2f} {cl:>6.1f}% {win:>6.1f}%{tag}")

    # ── 組合因子測試 ──
    def test_combo(weights, name, top_n=7, hold=10, min_amt=5e7):
        start_idx = close.index.get_loc(close.loc['2020-01-01':].index[0])
        sample_dates = close.index[start_idx::hold]
        prets, cls, yr_map = [], [], {}

        for dt in sample_dates:
            liq = liquidity.loc[dt].dropna()
            uni = liq[liq >= min_amt].index.tolist()
            if len(uni) < 50:
                continue
            score = pd.Series(0.0, index=uni)
            for fn, w in weights.items():
                if w == 0 or fn not in all_factors_map:
                    continue
                f = all_factors_map[fn]
                if dt not in f.index:
                    continue
                vals = f.loc[dt].reindex(uni).dropna()
                if len(vals) > 10:
                    score[vals.rank(pct=True).index] += vals.rank(pct=True) * w
            score = score.dropna().sort_values(ascending=False)
            sel = score.head(top_n).index.tolist()
            cls.append(sum(1 for s in sel if s in s2g) / top_n)

            dt_i = close.index.get_loc(dt)
            si = min(dt_i + hold, len(close) - 1)
            rs = []
            for s in sel:
                try:
                    bp, sp = close.iloc[dt_i+1][s], close.iloc[si][s]
                    if pd.notna(bp) and pd.notna(sp) and bp > 0:
                        rs.append((sp-bp)/bp)
                except:
                    pass
            if rs:
                ar = np.mean(rs)
                prets.append(ar)
                yr_map.setdefault(dt.year, []).append(ar)

        if not prets:
            return

        cum = np.cumprod([1+r for r in prets])
        total = cum[-1] - 1
        ny = len(prets) * hold / 252
        annual = (1+total)**(1/ny) - 1 if ny > 0 else 0
        sharpe = np.mean(prets) / np.std(prets) * np.sqrt(252/hold)
        mdd = min(cum[i]/max(cum[:i+1])-1 for i in range(len(cum)))
        avg_cl = np.mean(cls) * 100

        print(f"\n{name}")
        print(f"  年化:{annual*100:>+.1f}% Sharpe:{sharpe:.2f} MDD:{mdd*100:.1f}% 命中:{avg_cl:.0f}%")
        for y, rs in sorted(yr_map.items()):
            yr = np.prod([1+r for r in rs]) - 1
            print(f"  {y}: {yr*100:>+7.1f}%")

    print(f"\n{'='*70}")
    print(f"  組合因子測試（含新因子）")
    print(f"{'='*70}")

    combos = [
        ('A: 動能30+投信20+投信連買20+創高20+量價10',
         {'mom20': 0.3, 'trust': 0.2, 'tru_stk': 0.2, 'high': 0.2, 'vp': 0.1}),
        ('B: 動能30+外資連買20+投信連買20+創高20+位階10',
         {'mom20': 0.3, 'for_stk': 0.2, 'tru_stk': 0.2, 'high': 0.2, 'pos': 0.1}),
        ('C: 動能20+外資20+投信20+創高20+營收連成長20',
         {'mom20': 0.2, 'for20': 0.2, 'trust': 0.2, 'high': 0.2, 'rev_stk': 0.2}),
        ('D: 動能30+外資連買30+投信20+創高20',
         {'mom20': 0.3, 'for_stk': 0.3, 'trust': 0.2, 'high': 0.2}),
        ('E: 動能20+投信30+量價20+創高30',
         {'mom20': 0.2, 'trust': 0.3, 'vp': 0.2, 'high': 0.3}),
        ('F: 外資連買30+投信連買30+創高20+量價20',
         {'for_stk': 0.3, 'tru_stk': 0.3, 'high': 0.2, 'vp': 0.2}),
        ('G: 動能30+投信30+創高30+量價10',
         {'mom20': 0.3, 'trust': 0.3, 'high': 0.3, 'vp': 0.1}),
        ('H: 動能50+外資20+投信20+創高10（上次冠軍）',
         {'mom20': 0.5, 'for20': 0.2, 'trust': 0.2, 'high': 0.1}),
        ('I: 動能20+短動能20+投信20+創高20+量價20',
         {'mom20': 0.2, 'mom5': 0.2, 'trust': 0.2, 'high': 0.2, 'vp': 0.2}),
        ('J: 動能20+外資連買20+投信連買20+創高20+營收連成長20',
         {'mom20': 0.2, 'for_stk': 0.2, 'tru_stk': 0.2, 'high': 0.2, 'rev_stk': 0.2}),
        ('K: 短動能30+投信30+創高20+量20',
         {'mom5': 0.3, 'trust': 0.3, 'high': 0.2, 'vol': 0.2}),
        ('L: 動能20+外資20+投信連買20+創高20+營收20',
         {'mom20': 0.2, 'for20': 0.2, 'tru_stk': 0.2, 'high': 0.2, 'rev': 0.2}),
    ]

    for name, w in combos:
        test_combo(w, name)


if __name__ == '__main__':
    main()
