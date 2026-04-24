"""
族群輪動策略 - 修正版
修正1: T日選股 → T+1開盤買（不假設收盤價買得到）
修正2: 排除當天漲停股（實際掛單買不到）
修正3: 排除當時未上市股票（消除倖存者偏差）
"""
import warnings
warnings.filterwarnings("ignore")
import sys, os
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from finlab import data
from concept_groups import CONCEPT_GROUPS


def load():
    print("載入資料...")
    close = data.get('price:收盤價').loc['2019-12-01':]
    open_p = data.get('price:開盤價').loc['2019-12-01':]
    info = data.get('company_basic_info')

    # IPO日期對照
    ipo_map = {}
    for _, row in info.iterrows():
        sym = row.get('symbol', '')
        ipo = row.get('上市日期', None) or row.get('上櫃日期', None)
        if pd.notna(ipo) and sym:
            try:
                ipo_map[sym] = pd.Timestamp(ipo)
            except:
                pass
    print("載入完成")
    return close, open_p, ipo_map


def calc_limit_price(prev_close):
    raw = prev_close * 1.10
    if raw < 10:
        return np.floor(raw * 100) / 100
    elif raw < 50:
        return np.floor(raw * 20) / 20
    elif raw < 100:
        return np.floor(raw * 10) / 10
    elif raw < 500:
        return np.floor(raw * 2) / 2
    elif raw < 1000:
        return np.floor(raw)
    else:
        return np.floor(raw / 5) * 5


def is_limit_up(stock, idx, close):
    if idx < 1:
        return False
    try:
        pc = close.iloc[idx - 1][stock]
        tc = close.iloc[idx][stock]
        if pd.isna(pc) or pd.isna(tc) or pc == 0:
            return False
        return tc >= calc_limit_price(pc)
    except:
        return False


def group_returns(close, period):
    ret = close.pct_change(period)
    gr = {}
    for g, members in CONCEPT_GROUPS.items():
        valid = [s for s in members if s in ret.columns]
        if len(valid) >= 3:
            gr[g] = ret[valid].mean(axis=1)
    return pd.DataFrame(gr)


def run(close, open_p, ipo_map, lookback, top_n, hold, pick, max_hold):
    close2 = close.loc['2020-01-01':]
    open2 = open_p.loc['2020-01-01':]
    gr = group_returns(close, lookback).loc['2020-01-01':]
    ret5 = close.pct_change(5).loc['2020-01-01':]

    skip_limit = 0
    skip_ipo = 0

    # 收集每次再平衡的持有期報酬
    all_period_rets = []

    rebal_indices = list(range(max(40, lookback * 2), len(close2) - hold - 2, hold))

    for ri in rebal_indices:
        dt = close2.index[ri]
        if dt not in gr.index:
            continue

        scores = gr.loc[dt].dropna().sort_values(ascending=False)
        top_groups = scores.head(top_n).index.tolist()

        # 候選股
        cands = []
        for g in top_groups:
            members = [s for s in CONCEPT_GROUPS[g] if s in ret5.columns]
            if dt in ret5.index and members:
                gs = ret5.loc[dt, members].dropna().sort_values(ascending=False)
                cands.extend(gs.head(pick * 2).index.tolist())

        # 去重
        seen = set()
        unique_cands = []
        for s in cands:
            if s not in seen:
                seen.add(s)
                unique_cands.append(s)

        # 過濾: 未上市
        filtered = []
        for s in unique_cands:
            if s in ipo_map and dt < ipo_map[s]:
                skip_ipo += 1
            else:
                filtered.append(s)

        # 過濾: 漲停
        final = []
        for s in filtered:
            if is_limit_up(s, ri, close2):
                skip_limit += 1
            else:
                final.append(s)

        # 限制持股數
        if len(final) > max_hold:
            if dt in ret5.index:
                ss = ret5.loc[dt, final].dropna().sort_values(ascending=False)
                final = ss.head(max_hold).index.tolist()
            else:
                final = final[:max_hold]

        if not final:
            continue

        # T+1 開盤買，T+hold+1 開盤賣
        buy_idx = ri + 1
        sell_idx = min(ri + hold + 1, len(close2) - 1)

        if buy_idx >= len(open2) or sell_idx >= len(open2):
            continue

        for s in final:
            try:
                bp = open2.iloc[buy_idx][s]
                sp = open2.iloc[sell_idx][s]
                if pd.notna(bp) and pd.notna(sp) and bp > 0:
                    ret_val = (sp - bp) / bp
                    all_period_rets.append({
                        'buy_date': open2.index[buy_idx],
                        'sell_date': open2.index[sell_idx],
                        'stock': s,
                        'ret': ret_val,
                        'n_stocks': len(final),
                    })
            except:
                pass

    if not all_period_rets:
        return None, {}

    # 轉成每日報酬序列
    df = pd.DataFrame(all_period_rets)
    daily_rets = []

    for buy_dt in df['buy_date'].unique():
        batch = df[df['buy_date'] == buy_dt]
        sell_dt = batch['sell_date'].iloc[0]
        n = batch['n_stocks'].iloc[0]
        avg_ret = batch['ret'].mean()

        buy_i = close2.index.get_loc(buy_dt)
        sell_i = close2.index.get_loc(sell_dt)
        days = sell_i - buy_i
        if days <= 0:
            continue

        daily_r = (1 + avg_ret) ** (1 / days) - 1
        for d in range(buy_i, sell_i):
            daily_rets.append((close2.index[d], daily_r))

    if not daily_rets:
        return None, {}

    dr = pd.DataFrame(daily_rets, columns=['date', 'ret'])
    dr = dr.groupby('date')['ret'].sum()

    return dr, {'skip_limit': skip_limit, 'skip_ipo': skip_ipo}


def metrics(pr):
    cum = (1 + pr).cumprod()
    total = cum.iloc[-1] - 1
    n_years = len(pr) / 252
    annual = (1 + total) ** (1 / n_years) - 1 if n_years > 0 else 0
    sharpe = pr.mean() / pr.std() * np.sqrt(252) if pr.std() > 0 else 0
    peak = cum.expanding().max()
    mdd = ((cum - peak) / peak).min()
    nhp = (cum == peak).sum() / len(cum) * 100
    yearly = pr.groupby(pr.index.year).apply(lambda x: (1 + x).prod() - 1)
    return annual, sharpe, mdd, nhp, yearly


def main():
    close, open_p, ipo_map = load()

    configs = [
        ('週頻 LB5 Top5 選2',  5,  5,  5, 2, 7),
        ('週頻 LB5 Top3 選2',  5,  3,  5, 2, 7),
        ('週頻 LB5 Top5 選3',  5,  5,  5, 3, 7),
        ('週頻 LB10 Top5 選2', 10, 5,  5, 2, 7),
        ('週頻 LB10 Top3 選2', 10, 3,  5, 2, 7),
        ('雙週 LB5 Top5 選2',  5,  5, 10, 2, 7),
        ('雙週 LB5 Top3 選2',  5,  3, 10, 2, 7),
        ('雙週 LB10 Top5 選2', 10, 5, 10, 2, 7),
        ('雙週 LB10 Top3 選3', 10, 3, 10, 3, 7),
        ('月頻 LB10 Top5 選2', 10, 5, 20, 2, 7),
        ('月頻 LB10 Top3 選2', 10, 3, 20, 2, 7),
        ('月頻 LB20 Top3 選2', 20, 3, 20, 2, 7),
    ]

    results = []
    print(f"\n修正版族群輪動回測（2020~2026）")
    print(f"  - 隔日開盤買進（非當日收盤）")
    print(f"  - 排除當日漲停股")
    print(f"  - 排除未上市股票")
    print(f"  - 最大持股 7 檔")
    print(f"\n{'='*80}")
    print(f"{'策略':<24} {'年化':>7} {'Sharpe':>7} {'MDD':>7} {'創高%':>6} {'排除漲停':>7} {'排除IPO':>7}")
    print('-' * 75)

    for name, lb, tn, hd, pk, mh in configs:
        pr, stats = run(close, open_p, ipo_map, lb, tn, hd, pk, mh)
        if pr is None:
            print(f"{name:<24} NO DATA")
            continue

        annual, sharpe, mdd, nhp, yearly = metrics(pr)
        sl = stats['skip_limit']
        si = stats['skip_ipo']
        print(f"{name:<24} {annual*100:>+6.1f}% {sharpe:>6.2f} {mdd*100:>6.1f}% {nhp:>5.1f}% {sl:>6}次 {si:>6}次")
        results.append((name, annual, sharpe, mdd, nhp, yearly, stats))

    results.sort(key=lambda x: -x[2])

    print(f"\n{'='*80}")
    print(f"  Top 3 年度明細")
    print(f"{'='*80}")
    for name, annual, sharpe, mdd, nhp, yearly, stats in results[:3]:
        print(f"\n🏆 {name}")
        print(f"   年化: {annual*100:>+.1f}%  Sharpe: {sharpe:.2f}  MDD: {mdd*100:.1f}%  創高佔比: {nhp:.1f}%")
        print(f"   排除漲停: {stats['skip_limit']}次  排除未上市: {stats['skip_ipo']}次")
        for y, r in yearly.items():
            print(f"   {y}: {r*100:>+7.1f}%")


if __name__ == '__main__':
    main()
