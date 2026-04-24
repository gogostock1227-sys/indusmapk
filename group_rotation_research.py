"""
族群輪動策略自動研究
測試多種方法：
  1. 動能策略：買上月/上季漲幅最強族群
  2. 加速策略：找漲幅正在加速的族群（本月 > 上月）
  3. 突破策略：找成交量暴增的族群（量能啟動）
  4. 組合策略：動能 + 量能 + 法人
"""
import warnings
warnings.filterwarnings("ignore")
import sys, os
import numpy as np
import pandas as pd
from collections import defaultdict
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from finlab import data
from finlab.backtest import sim
from concept_groups import CONCEPT_GROUPS


def load_data():
    print("載入資料...")
    d = {}
    d['close'] = data.get('price:收盤價')
    d['volume'] = data.get('price:成交股數')
    d['amount'] = data.get('price:成交金額')
    try:
        d['foreign'] = data.get('institutional_investors_trading_summary:外陸資買賣超股數(不含外資自營商)')
    except:
        d['foreign'] = None
    try:
        d['trust'] = data.get('institutional_investors_trading_summary:投信買賣超股數')
    except:
        d['trust'] = None
    d['info'] = data.get('company_basic_info')
    d['name_map'] = d['info'].set_index('symbol')['公司簡稱'].to_dict()
    print("資料載入完成")
    return d


def calc_group_returns(close, periods=20):
    """計算每個族群的滾動報酬"""
    ret = close.pct_change(periods)
    group_ret = {}
    for g, members in CONCEPT_GROUPS.items():
        valid = [s for s in members if s in ret.columns]
        if len(valid) >= 3:
            group_ret[g] = ret[valid].mean(axis=1)
    return pd.DataFrame(group_ret)


def calc_group_volume_ratio(amount, periods=20):
    """計算每個族群的量能比（近N日成交額 / 前N日成交額）"""
    group_vol = {}
    for g, members in CONCEPT_GROUPS.items():
        valid = [s for s in members if s in amount.columns]
        if len(valid) >= 3:
            grp_amount = amount[valid].sum(axis=1)
            recent = grp_amount.rolling(periods).mean()
            prev = grp_amount.shift(periods).rolling(periods).mean()
            group_vol[g] = recent / prev
    return pd.DataFrame(group_vol)


def calc_group_foreign_flow(foreign, close, periods=20):
    """計算每個族群的外資買超金額（滾動N日）"""
    if foreign is None:
        return None
    group_flow = {}
    common = foreign.columns.intersection(close.columns)
    for g, members in CONCEPT_GROUPS.items():
        valid = [s for s in members if s in common]
        if len(valid) >= 3:
            # 外資買超股數 × 收盤價 = 金額
            flow = (foreign[valid] * close[valid]).rolling(periods).sum().sum(axis=1)
            group_flow[g] = flow
    return pd.DataFrame(group_flow)


def strategy_momentum(close, lookback=20, top_n=3, hold_days=20):
    """
    策略1：純動能
    每月初，買上月漲幅前 top_n 族群的成分股（等權）
    """
    group_ret = calc_group_returns(close, periods=lookback)

    # 建立選股訊號：每 hold_days 天換一次
    all_stocks = set()
    for members in CONCEPT_GROUPS.values():
        all_stocks.update(members)
    valid_stocks = [s for s in all_stocks if s in close.columns]

    # 產生持股信號 DataFrame
    signal = pd.DataFrame(False, index=close.index, columns=valid_stocks)

    rebal_dates = close.index[lookback::hold_days]

    for dt in rebal_dates:
        if dt not in group_ret.index:
            continue
        scores = group_ret.loc[dt].dropna().sort_values(ascending=False)
        top_groups = scores.head(top_n).index.tolist()

        selected = set()
        for g in top_groups:
            selected.update([s for s in CONCEPT_GROUPS[g] if s in valid_stocks])

        for s in selected:
            # 持有到下一個再平衡日
            idx = close.index.get_loc(dt)
            end_idx = min(idx + hold_days, len(close) - 1)
            signal.iloc[idx:end_idx][s] = True

    return signal


def strategy_momentum_volume(close, amount, lookback=20, top_n=3, hold_days=20):
    """
    策略2：動能 + 量能
    族群漲幅排名 + 成交量放大排名 → 綜合排名
    """
    group_ret = calc_group_returns(close, periods=lookback)
    group_vol = calc_group_volume_ratio(amount, periods=lookback)

    all_stocks = set()
    for members in CONCEPT_GROUPS.values():
        all_stocks.update(members)
    valid_stocks = [s for s in all_stocks if s in close.columns]

    signal = pd.DataFrame(False, index=close.index, columns=valid_stocks)
    rebal_dates = close.index[lookback * 2::hold_days]

    for dt in rebal_dates:
        if dt not in group_ret.index or dt not in group_vol.index:
            continue

        ret_scores = group_ret.loc[dt].dropna()
        vol_scores = group_vol.loc[dt].dropna()

        common_groups = ret_scores.index.intersection(vol_scores.index)
        if len(common_groups) < top_n:
            continue

        # 排名分數（排名越前分數越高）
        ret_rank = ret_scores[common_groups].rank(ascending=False)
        vol_rank = vol_scores[common_groups].rank(ascending=False)

        # 綜合分數 = 動能排名*0.6 + 量能排名*0.4
        combined = ret_rank * 0.6 + vol_rank * 0.4
        top_groups = combined.nsmallest(top_n).index.tolist()

        selected = set()
        for g in top_groups:
            selected.update([s for s in CONCEPT_GROUPS[g] if s in valid_stocks])

        for s in selected:
            idx = close.index.get_loc(dt)
            end_idx = min(idx + hold_days, len(close) - 1)
            signal.iloc[idx:end_idx][s] = True

    return signal


def strategy_acceleration(close, lookback_short=10, lookback_long=20, top_n=3, hold_days=20):
    """
    策略3：加速動能
    找近10日報酬 > 近20日報酬的族群 = 正在加速
    再從中選漲幅最大的
    """
    group_ret_short = calc_group_returns(close, periods=lookback_short)
    group_ret_long = calc_group_returns(close, periods=lookback_long)

    all_stocks = set()
    for members in CONCEPT_GROUPS.values():
        all_stocks.update(members)
    valid_stocks = [s for s in all_stocks if s in close.columns]

    signal = pd.DataFrame(False, index=close.index, columns=valid_stocks)
    rebal_dates = close.index[lookback_long::hold_days]

    for dt in rebal_dates:
        if dt not in group_ret_short.index or dt not in group_ret_long.index:
            continue

        short_ret = group_ret_short.loc[dt].dropna()
        long_ret = group_ret_long.loc[dt].dropna()

        common = short_ret.index.intersection(long_ret.index)

        # 加速中的族群：短期 > 長期
        accelerating = [g for g in common if short_ret[g] > long_ret[g] and short_ret[g] > 0]

        if not accelerating:
            # 沒有加速的就選動能最強的
            accelerating = common.tolist()

        # 從加速族群中選漲幅最大的
        accel_ret = short_ret[accelerating].sort_values(ascending=False)
        top_groups = accel_ret.head(top_n).index.tolist()

        selected = set()
        for g in top_groups:
            selected.update([s for s in CONCEPT_GROUPS[g] if s in valid_stocks])

        for s in selected:
            idx = close.index.get_loc(dt)
            end_idx = min(idx + hold_days, len(close) - 1)
            signal.iloc[idx:end_idx][s] = True

    return signal


def backtest_signal(signal, close, name, position_limit=10):
    """用 signal DataFrame 跑回測"""
    # 從 signal 中每天選最多 position_limit 檔
    # 按照近期漲幅排序，選最強的
    ret_5d = close.pct_change(5)

    final_signal = pd.DataFrame(False, index=signal.index, columns=signal.columns)

    for dt in signal.index:
        candidates = signal.columns[signal.loc[dt]].tolist()
        if not candidates:
            continue
        if len(candidates) <= position_limit:
            for s in candidates:
                final_signal.loc[dt, s] = True
        else:
            # 選近5日漲幅最強的
            if dt in ret_5d.index:
                scores = ret_5d.loc[dt, candidates].dropna().sort_values(ascending=False)
                for s in scores.head(position_limit).index:
                    final_signal.loc[dt, s] = True

    # 計算等權報酬
    daily_ret = close.pct_change()
    portfolio_ret = []

    for dt in final_signal.index:
        held = final_signal.columns[final_signal.loc[dt]].tolist()
        if held:
            day_ret = daily_ret.loc[dt, held].dropna().mean()
            portfolio_ret.append(day_ret)
        else:
            portfolio_ret.append(0)

    port_ret = pd.Series(portfolio_ret, index=final_signal.index)
    cum_ret = (1 + port_ret).cumprod()

    # 績效指標
    total_ret = cum_ret.iloc[-1] - 1
    annual_ret = (1 + total_ret) ** (252 / len(cum_ret)) - 1
    daily_std = port_ret.std()
    sharpe = (port_ret.mean() / daily_std * np.sqrt(252)) if daily_std > 0 else 0

    # MDD
    peak = cum_ret.expanding().max()
    dd = (cum_ret - peak) / peak
    mdd = dd.min()

    # 年度報酬
    yearly = port_ret.groupby(port_ret.index.year).apply(lambda x: (1 + x).prod() - 1)

    return {
        'name': name,
        'total_ret': total_ret,
        'annual_ret': annual_ret,
        'sharpe': sharpe,
        'mdd': mdd,
        'yearly': yearly,
        'cum_ret': cum_ret,
    }


def print_result(r):
    print(f"\n{'='*50}")
    print(f"  {r['name']}")
    print(f"{'='*50}")
    print(f"  總報酬: {r['total_ret']*100:>+.1f}%")
    print(f"  年化報酬: {r['annual_ret']*100:>+.1f}%")
    print(f"  Sharpe: {r['sharpe']:.2f}")
    print(f"  最大回撤: {r['mdd']*100:.1f}%")
    print(f"\n  年度報酬:")
    for year, ret in r['yearly'].items():
        print(f"    {year}: {ret*100:>+7.1f}%")


def main():
    d = load_data()
    close = d['close']
    amount = d['amount']

    # 只用 2020 年以後的資料
    close = close.loc['2020-01-01':]
    amount = amount.loc['2020-01-01':]

    results = []

    # ━━━ 策略1：月頻動能 Top 3 ━━━
    print("\n測試策略1: 月頻動能 Top 3...")
    sig = strategy_momentum(close, lookback=20, top_n=3, hold_days=20)
    r = backtest_signal(sig, close, "月頻動能 Top3 (持10檔)", position_limit=10)
    print_result(r)
    results.append(r)

    # ━━━ 策略1b：月頻動能 Top 5 ━━━
    print("\n測試策略1b: 月頻動能 Top 5...")
    sig = strategy_momentum(close, lookback=20, top_n=5, hold_days=20)
    r = backtest_signal(sig, close, "月頻動能 Top5 (持10檔)", position_limit=10)
    print_result(r)
    results.append(r)

    # ━━━ 策略2：動能+量能 Top 3 ━━━
    print("\n測試策略2: 動能+量能 Top 3...")
    sig = strategy_momentum_volume(close, amount, lookback=20, top_n=3, hold_days=20)
    r = backtest_signal(sig, close, "動能+量能 Top3 (持10檔)", position_limit=10)
    print_result(r)
    results.append(r)

    # ━━━ 策略3：加速動能 Top 3 ━━━
    print("\n測試策略3: 加速動能 Top 3...")
    sig = strategy_acceleration(close, lookback_short=10, lookback_long=20, top_n=3, hold_days=20)
    r = backtest_signal(sig, close, "加速動能 Top3 (持10檔)", position_limit=10)
    print_result(r)
    results.append(r)

    # ━━━ 策略4：雙週頻動能 Top 3 ━━━
    print("\n測試策略4: 雙週頻動能 Top 3...")
    sig = strategy_momentum(close, lookback=10, top_n=3, hold_days=10)
    r = backtest_signal(sig, close, "雙週頻動能 Top3 (持10檔)", position_limit=10)
    print_result(r)
    results.append(r)

    # ━━━ 大盤基準 ━━━
    bench_ret = close.mean(axis=1).pct_change()
    bench_cum = (1 + bench_ret.fillna(0)).cumprod()
    bench_total = bench_cum.iloc[-1] - 1
    bench_annual = (1 + bench_total) ** (252 / len(bench_cum)) - 1

    # ━━━ 匯總比較 ━━━
    print(f"\n\n{'='*70}")
    print(f"  📊 策略比較總表")
    print(f"{'='*70}")
    print(f"{'策略':<28} {'年化報酬':>8} {'Sharpe':>8} {'MDD':>8}")
    print(f"{'-'*56}")
    for r in results:
        print(f"{r['name']:<28} {r['annual_ret']*100:>+7.1f}% {r['sharpe']:>7.2f} {r['mdd']*100:>7.1f}%")
    print(f"{'大盤等權':<28} {bench_annual*100:>+7.1f}%")

    # 找最佳
    best = max(results, key=lambda x: x['sharpe'])
    print(f"\n🏆 最佳策略: {best['name']} (Sharpe {best['sharpe']:.2f})")


if __name__ == '__main__':
    main()
