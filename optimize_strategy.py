"""
族群飆股策略優化
目標：擴大績效 + 縮小MDD + 降低最大創高天數（回撤後恢復更快）
新增：停損機制、大盤濾網、持股集中度控制、再平衡頻率優化
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
    open_p = data.get('price:開盤價')
    amount = data.get('price:成交金額')
    foreign = data.get('institutional_investors_trading_summary:外陸資買賣超股數(不含外資自營商)')
    trust = data.get('institutional_investors_trading_summary:投信買賣超股數')
    rev_yoy = data.get('monthly_revenue:去年同月增減(%)')
    name_map = data.get('company_basic_info').set_index('symbol')['公司簡稱'].to_dict()

    s2g = {}
    for g, members in CONCEPT_GROUPS.items():
        for s in members:
            s2g.setdefault(s, []).append(g)

    # ── 因子 ──
    mom20 = close.pct_change(20)
    mom10 = close.pct_change(10)
    vol_ratio = amount.rolling(10).mean() / amount.shift(10).rolling(10).mean()
    foreign_amt = (foreign * close).rolling(20).sum()
    trust_streak = (trust > 0).rolling(20).sum()
    rev_daily = rev_yoy.reindex(close.index, method='ffill')
    liquidity = amount.rolling(20).mean()
    high_252 = close.rolling(252).max()
    near_high = close / high_252
    foreign_streak = (foreign > 0).rolling(20).sum()
    low_252 = close.rolling(252).min()
    price_pos = (close - low_252) / (high_252 - low_252)

    # 大盤指標（用全市場均線判斷多空）
    market_avg = close.mean(axis=1)
    market_ma60 = market_avg.rolling(60).mean()
    market_ma20 = market_avg.rolling(20).mean()
    market_bull = market_ma20 > market_ma60  # 短均>長均=多頭

    # 個股停損用
    rev_streak = (rev_yoy > 0).astype(int)
    for i in range(1, len(rev_streak)):
        rev_streak.iloc[i] = rev_streak.iloc[i] * (rev_streak.iloc[i-1] + rev_streak.iloc[i])
    rev_streak_daily = rev_streak.reindex(close.index, method='ffill')

    factors_map = {
        'mom20': mom20, 'mom10': mom10, 'vol': vol_ratio,
        'for20': foreign_amt, 'tru_stk': trust_streak,
        'rev': rev_daily, 'high': near_high,
        'for_stk': foreign_streak, 'pos': price_pos,
        'rev_stk': rev_streak_daily,
    }

    print('資料載入完成\n')

    def run_strategy(weights, top_n=7, hold=10, min_amt=5e7,
                     stop_loss=None, market_filter=False,
                     trailing_stop=None, min_hold=3):
        """
        完整策略回測
        stop_loss: 個股停損線 (e.g. -0.10)
        trailing_stop: 移動停損 (e.g. -0.15 = 從最高點回落15%出場)
        market_filter: True=大盤空頭時減半持倉
        min_hold: 最少持股數（大盤空頭時）
        """
        start_idx = close.index.get_loc(close.loc['2020-01-01':].index[0])
        sample_dates = close.index[start_idx::hold]

        # 逐日模擬
        daily_ret = []
        holdings = []  # 當前持股
        buy_prices = {}  # 買入價
        peak_prices = {}  # 持有期最高價
        yearly = {}

        for dt_idx in range(start_idx, len(close) - 1):
            dt = close.index[dt_idx]
            next_dt = close.index[dt_idx + 1]

            # 是否再平衡日
            is_rebal = dt in sample_dates

            if is_rebal:
                # 評分選股
                liq = liquidity.loc[dt].dropna()
                uni = liq[liq >= min_amt].index.tolist()

                if len(uni) >= 50:
                    score = pd.Series(0.0, index=uni)
                    for fn, w in weights.items():
                        if w == 0 or fn not in factors_map:
                            continue
                        f = factors_map[fn]
                        if dt not in f.index:
                            continue
                        vals = f.loc[dt].reindex(uni).dropna()
                        if len(vals) > 10:
                            score[vals.rank(pct=True).index] += vals.rank(pct=True) * w

                    score = score.dropna().sort_values(ascending=False)

                    # 大盤空頭減持
                    actual_top = top_n
                    if market_filter and dt in market_bull.index:
                        if not market_bull.loc[dt]:
                            actual_top = max(min_hold, top_n // 2)

                    new_holdings = score.head(actual_top).index.tolist()

                    # 更新持股
                    # 賣出不在新名單的
                    holdings = new_holdings
                    # 記錄買入價（用隔日開盤）
                    for s in holdings:
                        if s not in buy_prices:
                            try:
                                buy_prices[s] = open_p.iloc[dt_idx + 1][s]
                                peak_prices[s] = buy_prices[s]
                            except:
                                pass

                    # 清除已賣出的
                    buy_prices = {s: p for s, p in buy_prices.items() if s in holdings}
                    peak_prices = {s: p for s, p in peak_prices.items() if s in holdings}

            # 停損檢查
            if holdings and (stop_loss is not None or trailing_stop is not None):
                to_sell = []
                for s in holdings:
                    try:
                        cur_price = close.loc[dt, s]
                        if pd.isna(cur_price):
                            continue

                        # 更新最高價
                        if s in peak_prices:
                            peak_prices[s] = max(peak_prices[s], cur_price)

                        # 固定停損
                        if stop_loss is not None and s in buy_prices:
                            ret_from_buy = (cur_price - buy_prices[s]) / buy_prices[s]
                            if ret_from_buy <= stop_loss:
                                to_sell.append(s)
                                continue

                        # 移動停損
                        if trailing_stop is not None and s in peak_prices:
                            ret_from_peak = (cur_price - peak_prices[s]) / peak_prices[s]
                            if ret_from_peak <= trailing_stop:
                                to_sell.append(s)
                    except:
                        pass

                for s in to_sell:
                    holdings.remove(s)
                    buy_prices.pop(s, None)
                    peak_prices.pop(s, None)

            # 計算當日報酬
            if holdings:
                rets = []
                for s in holdings:
                    try:
                        p1 = close.iloc[dt_idx][s]
                        p2 = close.iloc[dt_idx + 1][s]
                        if pd.notna(p1) and pd.notna(p2) and p1 > 0:
                            rets.append((p2 - p1) / p1)
                    except:
                        pass
                if rets:
                    day_r = np.mean(rets)
                    daily_ret.append((next_dt, day_r))
                    yearly.setdefault(next_dt.year, []).append(day_r)

        if not daily_ret:
            return None

        dates = [d for d, _ in daily_ret]
        rets = [r for _, r in daily_ret]
        cum = np.cumprod([1 + r for r in rets])
        total = cum[-1] - 1
        ny = len(rets) / 252
        annual = (1 + total) ** (1 / ny) - 1 if ny > 0 else 0
        sharpe = np.mean(rets) / np.std(rets) * np.sqrt(252) if np.std(rets) > 0 else 0
        mdd = min(cum[i] / max(cum[:i + 1]) - 1 for i in range(len(cum)))

        # 最大創高天數（從高點到恢復的最長時間）
        peak_arr = np.maximum.accumulate(cum)
        in_dd = cum < peak_arr
        max_dd_days = 0
        current_dd_days = 0
        for is_dd in in_dd:
            if is_dd:
                current_dd_days += 1
                max_dd_days = max(max_dd_days, current_dd_days)
            else:
                current_dd_days = 0

        yr_results = {}
        for y, rs in yearly.items():
            yr_results[y] = np.prod([1 + r for r in rs]) - 1

        return {
            'annual': annual, 'sharpe': sharpe, 'mdd': mdd,
            'max_dd_days': max_dd_days, 'yearly': yr_results,
            'total': total,
        }

    # ── 測試矩陣 ──
    base_weights = [
        ('L基礎: 動能20+外資20+投信連買20+創高20+營收20',
         {'mom20': 0.2, 'for20': 0.2, 'tru_stk': 0.2, 'high': 0.2, 'rev': 0.2}),
        ('B基礎: 動能30+外資連買20+投信連買20+創高20+位階10',
         {'mom20': 0.3, 'for_stk': 0.2, 'tru_stk': 0.2, 'high': 0.2, 'pos': 0.1}),
    ]

    configs = []

    for bname, bw in base_weights:
        # 無防守
        configs.append((f'{bname}', bw, 7, 10, None, False, None))
        # 固定停損
        for sl in [-0.08, -0.10, -0.15]:
            configs.append((f'{bname} 停損{int(sl*100)}%', bw, 7, 10, sl, False, None))
        # 移動停損
        for ts in [-0.10, -0.15, -0.20]:
            configs.append((f'{bname} 移停{int(ts*100)}%', bw, 7, 10, None, False, ts))
        # 大盤濾網
        configs.append((f'{bname} 大盤濾', bw, 7, 10, None, True, None))
        # 大盤濾網 + 停損
        configs.append((f'{bname} 大盤濾+停損10%', bw, 7, 10, -0.10, True, None))
        configs.append((f'{bname} 大盤濾+移停15%', bw, 7, 10, None, True, -0.15))
        # 不同持股數
        for tn in [5, 10]:
            configs.append((f'{bname} {tn}檔', bw, tn, 10, None, False, None))
        # 不同再平衡
        for hd in [5, 15, 20]:
            configs.append((f'{bname} H{hd}', bw, 7, hd, None, False, None))

    print(f'共 {len(configs)} 種配置\n')
    print(f"{'策略':<50} {'年化':>7} {'Sharpe':>7} {'MDD':>6} {'創高天':>6}")
    print('=' * 80)

    results = []
    for i, (name, w, tn, hd, sl, mf, ts) in enumerate(configs):
        if i % 5 == 0:
            print(f'  進度 {i}/{len(configs)}...')
        r = run_strategy(w, top_n=tn, hold=hd, stop_loss=sl,
                         market_filter=mf, trailing_stop=ts)
        if r:
            print(f"{name:<50} {r['annual']*100:>+6.1f}% {r['sharpe']:>6.2f} {r['mdd']*100:>5.1f}% {r['max_dd_days']:>5}天")
            results.append((name, r))

    # 排序
    print(f"\n{'='*80}")
    print(f"  📊 Sharpe 前 10")
    print(f"{'='*80}")
    by_sharpe = sorted(results, key=lambda x: -x[1]['sharpe'])
    for i, (name, r) in enumerate(by_sharpe[:10], 1):
        print(f"{i:>2}. {name:<48} 年化:{r['annual']*100:>+.1f}% Sharpe:{r['sharpe']:.2f} MDD:{r['mdd']*100:.1f}% 創高天:{r['max_dd_days']}天")

    print(f"\n{'='*80}")
    print(f"  📊 MDD 最小前 10")
    print(f"{'='*80}")
    by_mdd = sorted(results, key=lambda x: -x[1]['mdd'])  # mdd is negative, so -mdd = ascending
    for i, (name, r) in enumerate(by_mdd[:10], 1):
        print(f"{i:>2}. {name:<48} 年化:{r['annual']*100:>+.1f}% Sharpe:{r['sharpe']:.2f} MDD:{r['mdd']*100:.1f}% 創高天:{r['max_dd_days']}天")

    print(f"\n{'='*80}")
    print(f"  📊 最大創高天數最短前 10")
    print(f"{'='*80}")
    by_dd_days = sorted(results, key=lambda x: x[1]['max_dd_days'])
    for i, (name, r) in enumerate(by_dd_days[:10], 1):
        print(f"{i:>2}. {name:<48} 年化:{r['annual']*100:>+.1f}% Sharpe:{r['sharpe']:.2f} MDD:{r['mdd']*100:.1f}% 創高天:{r['max_dd_days']}天")

    # 最佳平衡
    print(f"\n{'='*80}")
    print(f"  🏆 最佳平衡（Sharpe / -MDD / 創高天 綜合）")
    print(f"{'='*80}")
    max_sharpe = max(r['sharpe'] for _, r in results)
    min_mdd_abs = max(-r['mdd'] for _, r in results)
    max_dd_days = max(r['max_dd_days'] for _, r in results)

    balanced = []
    for name, r in results:
        s_score = r['sharpe'] / max_sharpe if max_sharpe > 0 else 0
        m_score = 1 - (-r['mdd'] / min_mdd_abs) if min_mdd_abs > 0 else 0
        d_score = 1 - (r['max_dd_days'] / max_dd_days) if max_dd_days > 0 else 0
        total_score = s_score * 0.4 + m_score * 0.3 + d_score * 0.3
        balanced.append((name, r, total_score))

    balanced.sort(key=lambda x: -x[2])
    for i, (name, r, score) in enumerate(balanced[:10], 1):
        print(f"{i:>2}. {name:<48} 年化:{r['annual']*100:>+.1f}% Sharpe:{r['sharpe']:.2f} MDD:{r['mdd']*100:.1f}% 創高天:{r['max_dd_days']}天 綜合:{score:.3f}")

    # 最佳策略年度明細
    best_name, best_r, _ = balanced[0]
    print(f"\n🏆 最佳策略: {best_name}")
    print(f"   年化:{best_r['annual']*100:>+.1f}% Sharpe:{best_r['sharpe']:.2f} MDD:{best_r['mdd']*100:.1f}% 創高天:{best_r['max_dd_days']}天")
    for y, r in sorted(best_r['yearly'].items()):
        print(f"   {y}: {r*100:>+7.1f}%")


if __name__ == '__main__':
    main()
