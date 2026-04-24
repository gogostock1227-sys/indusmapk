"""
每日族群漲停追蹤器 v2
功能：
  1. 漲停/跌停偵測 + 漲停板強度（量縮鎖板 vs 量增封板）
  2. 連板追蹤（標示連續漲停天數）
  3. 族群資金流向（成交金額排行）
  4. 跌停族群監控
  5. HTML 互動式報表輸出
  6. 族群輪動熱力圖
  7. 外資/投信同步標記
  8. 自動族群發現（無分類股自動歸類）

用法:
  python 族群統計/daily_group_tracker.py                    # 最近1天
  python 族群統計/daily_group_tracker.py --days 5           # 最近5天
  python 族群統計/daily_group_tracker.py --days 10 --html   # 10天 + HTML報表
"""
import warnings
warnings.filterwarnings("ignore")
import argparse
import pandas as pd
import numpy as np
from datetime import datetime
from collections import defaultdict
import ast
import json
import os

from concept_groups import CONCEPT_GROUPS

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from finlab import data


# ─────────────────── 資料載入 ───────────────────

def load_all_data():
    """一次載入所有需要的資料"""
    print("正在下載資料...")
    d = {}
    d['close'] = data.get('price:收盤價')
    d['open'] = data.get('price:開盤價')
    d['high'] = data.get('price:最高價')
    d['low'] = data.get('price:最低價')
    d['volume'] = data.get('price:成交股數')
    d['amount'] = data.get('price:成交金額')
    d['name_map'] = _get_stock_names()

    # 法人資料
    try:
        d['foreign'] = data.get('institutional_investors_trading_summary:外陸資買賣超股數(不含外資自營商)')
    except:
        d['foreign'] = None
    try:
        d['trust'] = data.get('institutional_investors_trading_summary:投信買賣超股數')
    except:
        d['trust'] = None

    # 產業分類（用於自動歸群）
    try:
        d['industry'] = data.get('security_categories')
    except:
        d['industry'] = None

    print("資料載入完成。")
    return d


def _get_stock_names():
    """取得股票名稱對照表"""
    info = data.get('company_basic_info')
    return info.set_index('symbol')['公司簡稱'].to_dict()


# ─────────────────── 核心分析 ───────────────────

def calc_limit_price(prev_close):
    """
    計算台股漲停/跌停價（含跳檔規則）
    台股漲跌幅限制 10%，但實際漲停價要經過跳檔(tick)取整
    """
    raw_up = prev_close * 1.10
    raw_down = prev_close * 0.90

    # 台股跳檔規則
    def tick_round_down(price):
        if price < 10:
            return np.floor(price * 100) / 100      # 0.01
        elif price < 50:
            return np.floor(price * 20) / 20         # 0.05
        elif price < 100:
            return np.floor(price * 10) / 10         # 0.1
        elif price < 500:
            return np.floor(price * 2) / 2           # 0.5
        elif price < 1000:
            return np.floor(price)                   # 1
        else:
            return np.floor(price / 5) * 5           # 5

    def tick_round_up(price):
        if price < 10:
            return np.ceil(price * 100) / 100
        elif price < 50:
            return np.ceil(price * 20) / 20
        elif price < 100:
            return np.ceil(price * 10) / 10
        elif price < 500:
            return np.ceil(price * 2) / 2
        elif price < 1000:
            return np.ceil(price)
        else:
            return np.ceil(price / 5) * 5

    limit_up = tick_round_down(raw_up)
    limit_down = tick_round_up(raw_down)
    return limit_up, limit_down


def find_limit_stocks(close, days=1, up_threshold=None, down_threshold=None, start_date=None, end_date=None):
    """
    找出漲停/跌停股
    使用台股漲停價計算（收盤價 = 漲停價）
    支援 start_date / end_date 日期範圍篩選
    """
    if start_date or end_date:
        # 日期範圍模式
        if start_date:
            start_dt = pd.Timestamp(start_date)
            # 需要往前多取一天當作前日收盤
            start_idx = close.index.searchsorted(start_dt)
            start_idx = max(0, start_idx - 1)
        else:
            start_idx = 0
        if end_date:
            end_dt = pd.Timestamp(end_date)
            end_idx = close.index.searchsorted(end_dt, side='right')
        else:
            end_idx = len(close)
        recent_close = close.iloc[start_idx:end_idx]
    else:
        recent_close = close.iloc[-(days+1):]  # 多取一天算前日收盤
    limit_up = {}
    limit_down = {}

    for i in range(1, len(recent_close)):
        date = recent_close.index[i]
        prev = recent_close.iloc[i-1]
        today = recent_close.iloc[i]

        up_stocks = {}
        down_stocks = {}

        for stock in today.dropna().index:
            if stock not in prev.index or pd.isna(prev[stock]) or prev[stock] == 0:
                continue
            pc = prev[stock]
            tc = today[stock]
            lim_up, lim_down = calc_limit_price(pc)

            ret = (tc - pc) / pc

            if tc >= lim_up:  # 收盤價 >= 漲停價 = 漲停
                up_stocks[stock] = ret
            elif tc <= lim_down:  # 收盤價 <= 跌停價 = 跌停
                down_stocks[stock] = ret

        limit_up[date] = pd.Series(up_stocks).sort_values(ascending=False)
        limit_down[date] = pd.Series(down_stocks).sort_values(ascending=True)

    return limit_up, limit_down


def analyze_limit_strength(stock, date, d):
    """
    分析漲停板強度
    回傳: (強度等級, 描述)
    - 'lock':  一字板（開=高=收，量極縮）
    - 'strong': 量增強封（量>5日均量，收盤=最高）
    - 'normal': 普通漲停
    """
    try:
        idx = d['close'].index.get_loc(date)
        o = d['open'].loc[date, stock]
        h = d['high'].loc[date, stock]
        l = d['low'].loc[date, stock]
        c = d['close'].loc[date, stock]
        vol = d['volume'].loc[date, stock]

        # 5日均量
        vol_5d = d['volume'].iloc[max(0, idx-5):idx][stock].mean()
        vol_ratio = vol / vol_5d if vol_5d > 0 else 1

        # 一字板：開=高=低=收（或近似）
        price_range = h - l
        if price_range <= c * 0.001:
            return 'lock', f'一字板(量比{vol_ratio:.1f})'

        # 強封：收盤=最高且量大
        if abs(c - h) <= c * 0.001 and vol_ratio >= 1.5:
            return 'strong', f'量增強封(量比{vol_ratio:.1f})'

        return 'normal', f'普通封板(量比{vol_ratio:.1f})'
    except:
        return 'normal', ''


def find_consecutive_limit(close, stock, end_date, max_lookback=20):
    """計算個股連板天數（往回追溯），使用漲停價判斷"""
    try:
        end_idx = close.index.get_loc(end_date)
    except:
        return 0

    count = 0
    for i in range(end_idx, max(end_idx - max_lookback, 0), -1):
        try:
            if i < 1:
                break
            pc = close.iloc[i-1][stock]
            tc = close.iloc[i][stock]
            if pd.isna(pc) or pd.isna(tc) or pc == 0:
                break
            lim_up, _ = calc_limit_price(pc)
            if tc >= lim_up:
                count += 1
            else:
                break
        except:
            break
    return count


def classify_stocks(stock_list):
    """將股票清單歸類到概念股族群"""
    stock_set = set(stock_list)
    group_hits = defaultdict(list)
    for group_name, members in CONCEPT_GROUPS.items():
        for stock in members:
            if stock in stock_set:
                group_hits[group_name].append(stock)
    return dict(group_hits)


def auto_classify_uncategorized(stock_list, industry_df):
    """將未被任何族群收錄的股票用產業分類自動歸類"""
    all_concept_stocks = set()
    for members in CONCEPT_GROUPS.values():
        all_concept_stocks.update(members)

    uncategorized = [s for s in stock_list if s not in all_concept_stocks]
    if not uncategorized or industry_df is None:
        return {}

    auto_groups = defaultdict(list)
    cat_map = industry_df.set_index('symbol')['category'].to_dict()

    for stock in uncategorized:
        cat = cat_map.get(stock, '其他')
        auto_groups[f'[自動]{cat}'].append(stock)

    return dict(auto_groups)


def get_institutional_info(stock, date, d):
    """取得法人買賣超資訊"""
    info = []
    try:
        if d['foreign'] is not None and stock in d['foreign'].columns:
            val = d['foreign'].loc[date, stock] if date in d['foreign'].index else None
            if pd.notna(val) and val != 0:
                shares = val / 1000  # 張
                tag = '外資買' if val > 0 else '外資賣'
                info.append(f'{tag}{abs(shares):.0f}張')
    except:
        pass
    try:
        if d['trust'] is not None and stock in d['trust'].columns:
            val = d['trust'].loc[date, stock] if date in d['trust'].index else None
            if pd.notna(val) and val != 0:
                shares = val / 1000
                tag = '投信買' if val > 0 else '投信賣'
                info.append(f'{tag}{abs(shares):.0f}張')
    except:
        pass
    return ' | '.join(info) if info else ''


def find_laggards(group_name, hot_stocks, d, top_n=5):
    """找同族群落後補漲候選"""
    members = CONCEPT_GROUPS.get(group_name, [])
    hot_set = set(hot_stocks)
    close = d['close']
    ret_5d = close.pct_change(5).iloc[-1]

    laggards = []
    for stock in members:
        if stock not in hot_set and stock in ret_5d.index and pd.notna(ret_5d[stock]):
            laggards.append((stock, ret_5d[stock]))
    laggards.sort(key=lambda x: x[1])
    return laggards[:top_n]


def calc_group_turnover(group_name, date, d):
    """計算族群當日成交金額"""
    members = CONCEPT_GROUPS.get(group_name, [])
    total = 0
    for stock in members:
        try:
            val = d['amount'].loc[date, stock]
            if pd.notna(val):
                total += val
        except:
            pass
    return total


# ─────────────────── Console 輸出 ───────────────────

def print_report(args, d):
    """主報表：console 輸出"""
    close = d['close']
    name_map = d['name_map']

    start_date = getattr(args, 'start', None)
    end_date = getattr(args, 'end', None)

    limit_up, limit_down = find_limit_stocks(close, days=args.days, start_date=start_date, end_date=end_date)

    if start_date and end_date:
        title = f"  族群漲停追蹤器 v2 — {start_date} ~ {end_date}"
    elif start_date:
        title = f"  族群漲停追蹤器 v2 — {start_date} 起"
    else:
        title = f"  族群漲停追蹤器 v2 — 最近 {args.days} 個交易日"

    print(f"\n{'='*70}")
    print(title)
    print(f"{'='*70}")

    # 收集所有資料供 HTML 使用
    report_data = {
        'days': args.days,
        'daily_up': [],
        'daily_down': [],
        'group_ranking': [],
        'group_down_ranking': [],
        'laggards': {},
        'heatmap': {},
        'turnover_ranking': [],
    }

    group_total_hits = defaultdict(set)
    group_day_count = defaultdict(int)
    group_down_total = defaultdict(set)
    group_down_day_count = defaultdict(int)
    heatmap_data = {}  # {date_str: {group: count}}

    all_dates = sorted(limit_up.keys())

    for date in all_dates:
        stocks_up = limit_up[date]
        stocks_down = limit_down[date]
        date_str = date.strftime('%Y-%m-%d')

        # ═══ 漲停清單 ═══
        stock_list_up = stocks_up.index.tolist()
        group_hits = classify_stocks(stock_list_up)
        auto_groups = auto_classify_uncategorized(stock_list_up, d.get('industry'))

        day_data_up = []
        print(f"\n{'─'*70}")
        print(f" {date_str}  漲停/近漲停 {len(stocks_up)} 檔 | 跌停/近跌停 {len(stocks_down)} 檔")
        print(f"{'─'*70}")

        if len(stocks_up) > 0:
            print(f"\n  {'代號':<8} {'股名':<8} {'漲幅%':<7} {'強度':<16} {'連板':<5} {'法人動向':<20} {'族群'}")
            print(f"  {'-'*90}")

            for stock, ret in stocks_up.items():
                name = name_map.get(stock, '')
                belongs = [g for g, members in CONCEPT_GROUPS.items() if stock in members]
                # 加上自動分類
                for g, members in auto_groups.items():
                    if stock in members and g not in belongs:
                        belongs.append(g)
                groups_str = ', '.join(belongs) if belongs else '（無分類）'

                strength, strength_desc = analyze_limit_strength(stock, date, d)
                consec = find_consecutive_limit(close, stock, date)
                consec_str = f'{consec}連板' if consec >= 2 else ''
                inst_info = get_institutional_info(stock, date, d)

                strength_icon = {'lock': '🔒', 'strong': '🔥', 'normal': '📈'}[strength]
                print(f"  {stock:<8} {name:<8} {ret*100:>5.1f}%  {strength_icon}{strength_desc:<14} {consec_str:<5} {inst_info:<20} {groups_str}")

                day_data_up.append({
                    'stock': stock, 'name': name, 'ret': ret,
                    'strength': strength, 'strength_desc': strength_desc,
                    'consec': consec, 'inst': inst_info, 'groups': belongs
                })

        report_data['daily_up'].append({'date': date_str, 'stocks': day_data_up})

        # ═══ 跌停清單 ═══
        if len(stocks_down) > 0:
            stock_list_down = stocks_down.index.tolist()
            group_hits_down = classify_stocks(stock_list_down)

            day_data_down = []
            print(f"\n  ⬇ 跌停股：")
            print(f"  {'代號':<8} {'股名':<8} {'跌幅%':<8} {'族群'}")
            print(f"  {'-'*50}")
            for stock, ret in stocks_down.items():
                name = name_map.get(stock, '')
                belongs = [g for g, members in CONCEPT_GROUPS.items() if stock in members]
                groups_str = ', '.join(belongs) if belongs else '（無分類）'
                print(f"  {stock:<8} {name:<8} {ret*100:>6.1f}%  {groups_str}")
                day_data_down.append({'stock': stock, 'name': name, 'ret': ret, 'groups': belongs})

            for group, members in group_hits_down.items():
                group_down_total[group].update(members)
                group_down_day_count[group] += 1

            report_data['daily_down'].append({'date': date_str, 'stocks': day_data_down})

        # 彙總漲停族群
        for group, members in group_hits.items():
            group_total_hits[group].update(members)
            group_day_count[group] += 1

        # 熱力圖資料
        heatmap_data[date_str] = {}
        for group, members in group_hits.items():
            heatmap_data[date_str][group] = len(members)

    # ═══ 族群熱度排行 ═══
    print(f"\n\n{'='*70}")
    print(f"  🔥 族群熱度排行（依漲停家數）")
    print(f"{'='*70}")

    group_ranking = sorted(group_total_hits.items(), key=lambda x: len(x[1]), reverse=True)
    report_data['group_ranking'] = group_ranking

    print(f"\n  {'排名':<4} {'族群':<16} {'漲停家數':<8} {'出現天數':<10} {'漲停個股'}")
    print(f"  {'-'*80}")
    for i, (group, stocks) in enumerate(group_ranking, 1):
        days = group_day_count[group]
        stock_names = [f"{s}({name_map.get(s, '')})" for s in stocks]
        streak_tag = ' 🔥連續' if days >= 2 else ''
        print(f"  {i:<4} {group:<16} {len(stocks):<8} {days}/{args.days}天{streak_tag:<8} {', '.join(stock_names)}")

    # ═══ 跌停族群警示 ═══
    if group_down_total:
        print(f"\n\n{'='*70}")
        print(f"  ⚠ 跌停族群警示")
        print(f"{'='*70}")
        group_down_ranking = sorted(group_down_total.items(), key=lambda x: len(x[1]), reverse=True)
        report_data['group_down_ranking'] = group_down_ranking
        for group, stocks in group_down_ranking:
            stock_names = [f"{s}({name_map.get(s, '')})" for s in stocks]
            print(f"  【{group}】跌停 {len(stocks)} 檔: {', '.join(stock_names)}")

    # ═══ 族群資金流向 ═══
    print(f"\n\n{'='*70}")
    print(f"  💰 族群資金流向（最近交易日成交金額）")
    print(f"{'='*70}")

    last_date = all_dates[-1] if all_dates else close.index[-1]
    turnover_list = []
    for group_name in CONCEPT_GROUPS:
        amt = calc_group_turnover(group_name, last_date, d)
        if amt > 0:
            turnover_list.append((group_name, amt))
    turnover_list.sort(key=lambda x: x[1], reverse=True)
    report_data['turnover_ranking'] = turnover_list

    print(f"\n  {'排名':<4} {'族群':<16} {'成交金額(億)':<14} {'佔比'}")
    print(f"  {'-'*50}")
    total_amt = sum(x[1] for x in turnover_list) if turnover_list else 1
    for i, (group, amt) in enumerate(turnover_list[:15], 1):
        amt_yi = amt / 1e8
        pct = amt / total_amt * 100
        bar = '█' * int(pct / 2)
        print(f"  {i:<4} {group:<16} {amt_yi:>10.1f}億    {pct:>4.1f}% {bar}")

    # ═══ 落後補漲候選 ═══
    if group_ranking:
        print(f"\n\n{'='*70}")
        print(f"  📊 熱門族群落後補漲候選")
        print(f"{'='*70}")

        for group, hot_stocks in group_ranking[:5]:
            laggards = find_laggards(group, hot_stocks, d)
            if laggards:
                report_data['laggards'][group] = laggards
                print(f"\n  【{group}】已漲停 {len(hot_stocks)} 檔，落後候選：")
                for stock, ret in laggards:
                    name = name_map.get(stock, '')
                    inst = get_institutional_info(stock, last_date, d)
                    inst_str = f'  ({inst})' if inst else ''
                    print(f"    {stock} {name:<8} 近5日: {ret*100:>6.1f}%{inst_str}")

    # ═══ 族群輪動觀察 ═══
    if args.days >= 3 and len(all_dates) >= 3:
        print(f"\n\n{'='*70}")
        print(f"  🔄 族群輪動觀察（熱力圖）")
        print(f"{'='*70}")

        all_groups_in_heatmap = set()
        for day_data in heatmap_data.values():
            all_groups_in_heatmap.update(day_data.keys())
        all_groups_sorted = sorted(all_groups_in_heatmap,
            key=lambda g: sum(heatmap_data[dt].get(g, 0) for dt in heatmap_data), reverse=True)

        header = f"  {'族群':<16}" + ''.join(f'{dt[-5:]:<8}' for dt in sorted(heatmap_data.keys()))
        print(f"\n{header}")
        print(f"  {'-'*(16 + 8*len(heatmap_data))}")

        for group in all_groups_sorted[:15]:
            row = f"  {group:<16}"
            for dt in sorted(heatmap_data.keys()):
                count = heatmap_data[dt].get(group, 0)
                if count == 0:
                    cell = '  ·   '
                elif count == 1:
                    cell = '  ■   '
                elif count == 2:
                    cell = ' ■■   '
                else:
                    cell = f' ■x{count}  '
                row += f'{cell:<8}'
            print(row)

    report_data['heatmap'] = heatmap_data

    print(f"\n\n分析完成！")
    return report_data


# ─────────────────── HTML 報表 ───────────────────

def generate_html_report(report_data, d, output_path):
    """產生互動式 HTML 報表"""
    name_map = d['name_map']
    days = report_data['days']

    # 準備熱力圖 JSON
    heatmap = report_data.get('heatmap', {})
    dates_sorted = sorted(heatmap.keys())
    all_groups = set()
    for day_data in heatmap.values():
        all_groups.update(day_data.keys())
    groups_sorted = sorted(all_groups,
        key=lambda g: sum(heatmap[dt].get(g, 0) for dt in dates_sorted), reverse=True)

    heatmap_json = json.dumps({
        'dates': dates_sorted,
        'groups': groups_sorted[:20],
        'data': [[heatmap.get(dt, {}).get(g, 0) for dt in dates_sorted] for g in groups_sorted[:20]]
    }, ensure_ascii=False)

    # 漲停族群排行 JSON
    ranking_json = json.dumps([
        {'group': g, 'count': len(s), 'stocks': [{'id': st, 'name': name_map.get(st, '')} for st in s]}
        for g, s in report_data.get('group_ranking', [])
    ], ensure_ascii=False)

    # 資金流 JSON
    turnover_json = json.dumps([
        {'group': g, 'amount': round(a / 1e8, 1)}
        for g, a in report_data.get('turnover_ranking', [])[:15]
    ], ensure_ascii=False)

    # 每日漲停明細 JSON
    daily_json = json.dumps(report_data.get('daily_up', []), ensure_ascii=False, default=str)

    # 每日跌停 JSON
    daily_down_json = json.dumps(report_data.get('daily_down', []), ensure_ascii=False, default=str)

    # 落後補漲 JSON
    laggards_json = json.dumps({
        g: [{'stock': s, 'name': name_map.get(s, ''), 'ret': round(r*100, 1)} for s, r in lags]
        for g, lags in report_data.get('laggards', {}).items()
    }, ensure_ascii=False)

    html = f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>族群漲停追蹤器 — 最近 {days} 個交易日</title>
<style>
  :root {{
    --bg: #0f1117; --card: #1a1d29; --border: #2a2d3a;
    --text: #e4e4e7; --text2: #a1a1aa; --accent: #f59e0b;
    --red: #ef4444; --green: #22c55e; --blue: #3b82f6;
  }}
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ background:var(--bg); color:var(--text); font-family:'Segoe UI',system-ui,sans-serif; padding:20px; }}
  h1 {{ text-align:center; font-size:1.8em; margin:20px 0; color:var(--accent); }}
  h2 {{ font-size:1.3em; margin:25px 0 15px; padding-left:10px; border-left:4px solid var(--accent); }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fit, minmax(450px, 1fr)); gap:20px; margin:20px 0; }}
  .card {{ background:var(--card); border:1px solid var(--border); border-radius:12px; padding:20px; }}
  .card h3 {{ color:var(--accent); margin-bottom:15px; font-size:1.1em; }}
  table {{ width:100%; border-collapse:collapse; font-size:0.9em; }}
  th {{ background:#252836; padding:8px 10px; text-align:left; color:var(--text2); font-weight:500; position:sticky; top:0; }}
  td {{ padding:6px 10px; border-bottom:1px solid var(--border); }}
  tr:hover td {{ background:rgba(245,158,11,0.05); }}
  .up {{ color:var(--red); font-weight:600; }}
  .down {{ color:var(--green); font-weight:600; }}
  .tag {{ display:inline-block; padding:2px 8px; border-radius:4px; font-size:0.8em; margin:1px; }}
  .tag-group {{ background:rgba(59,130,246,0.15); color:var(--blue); }}
  .tag-lock {{ background:rgba(239,68,68,0.15); color:var(--red); }}
  .tag-strong {{ background:rgba(245,158,11,0.15); color:var(--accent); }}
  .tag-consec {{ background:rgba(168,85,247,0.15); color:#a855f7; }}
  .tag-foreign {{ background:rgba(34,197,94,0.15); color:var(--green); }}
  .tag-trust {{ background:rgba(6,182,212,0.15); color:#06b6d4; }}
  .bar-container {{ display:flex; align-items:center; gap:8px; }}
  .bar {{ height:20px; border-radius:4px; min-width:2px; transition:width 0.5s; }}
  .bar-up {{ background:linear-gradient(90deg, var(--red), #f97316); }}
  .bar-down {{ background:linear-gradient(90deg, var(--green), #06b6d4); }}
  .bar-amt {{ background:linear-gradient(90deg, var(--accent), #f97316); }}
  .heatmap {{ overflow-x:auto; }}
  .heatmap table td {{ text-align:center; width:60px; min-width:60px; }}
  .heat-0 {{ background:transparent; color:var(--text2); }}
  .heat-1 {{ background:rgba(239,68,68,0.2); color:var(--red); }}
  .heat-2 {{ background:rgba(239,68,68,0.4); color:var(--red); font-weight:600; }}
  .heat-3 {{ background:rgba(239,68,68,0.6); color:#fff; font-weight:700; }}
  .heat-4 {{ background:rgba(239,68,68,0.8); color:#fff; font-weight:700; }}
  .tabs {{ display:flex; gap:8px; margin-bottom:15px; flex-wrap:wrap; }}
  .tab {{ padding:6px 16px; border-radius:6px; cursor:pointer; background:var(--border); color:var(--text2); border:none; font-size:0.9em; }}
  .tab.active {{ background:var(--accent); color:#000; font-weight:600; }}
  .tab-content {{ display:none; }}
  .tab-content.active {{ display:block; }}
  .summary-grid {{ display:grid; grid-template-columns:repeat(auto-fit, minmax(180px, 1fr)); gap:15px; margin:20px 0; }}
  .summary-item {{ background:var(--card); border:1px solid var(--border); border-radius:10px; padding:15px; text-align:center; }}
  .summary-item .number {{ font-size:2em; font-weight:700; color:var(--accent); }}
  .summary-item .label {{ color:var(--text2); font-size:0.85em; margin-top:5px; }}
  .footer {{ text-align:center; color:var(--text2); margin-top:40px; padding:20px; font-size:0.85em; }}
</style>
</head>
<body>

<h1>族群漲停追蹤器</h1>
<p style="text-align:center;color:var(--text2);margin-bottom:20px;">最近 {days} 個交易日 | 產生時間 {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>

<div class="summary-grid" id="summary"></div>

<h2>🔥 族群熱度排行</h2>
<div class="card" id="ranking-card"></div>

<h2>💰 族群資金流向</h2>
<div class="card" id="turnover-card"></div>

<div class="grid">
  <div>
    <h2>📈 漲停明細</h2>
    <div class="card">
      <div class="tabs" id="up-tabs"></div>
      <div id="up-content"></div>
    </div>
  </div>
  <div>
    <h2>📊 落後補漲候選</h2>
    <div class="card" id="laggard-card"></div>
  </div>
</div>

<h2>🔄 族群輪動熱力圖</h2>
<div class="card heatmap" id="heatmap-card"></div>

<h2>⚠ 跌停族群警示</h2>
<div class="card" id="down-card"></div>

<div class="footer">族群漲停追蹤器 v2 | FinLab 資料驅動</div>

<script>
const ranking = {ranking_json};
const turnover = {turnover_json};
const daily = {daily_json};
const dailyDown = {daily_down_json};
const heatmap = {heatmap_json};
const laggards = {laggards_json};

// Summary
(() => {{
  const totalUp = daily.reduce((s, d) => s + d.stocks.length, 0);
  const totalDown = dailyDown.reduce((s, d) => s + d.stocks.length, 0);
  const hotGroup = ranking.length > 0 ? ranking[0].group : '-';
  const lockCount = daily.reduce((s, d) => s + d.stocks.filter(st => st.strength === 'lock').length, 0);
  document.getElementById('summary').innerHTML = `
    <div class="summary-item"><div class="number">${{totalUp}}</div><div class="label">漲停檔數</div></div>
    <div class="summary-item"><div class="number">${{totalDown}}</div><div class="label">跌停檔數</div></div>
    <div class="summary-item"><div class="number">${{ranking.length}}</div><div class="label">活躍族群</div></div>
    <div class="summary-item"><div class="number" style="font-size:1.2em">${{hotGroup}}</div><div class="label">最熱族群</div></div>
    <div class="summary-item"><div class="number">${{lockCount}}</div><div class="label">一字板</div></div>
  `;
}})();

// Ranking
(() => {{
  if (!ranking.length) {{ document.getElementById('ranking-card').innerHTML = '<p style="color:var(--text2)">無漲停族群</p>'; return; }}
  const maxCount = ranking[0].count;
  let html = '<table><tr><th>#</th><th>族群</th><th>漲停家數</th><th>個股</th></tr>';
  ranking.forEach((r, i) => {{
    const barW = (r.count / maxCount * 100);
    const stocks = r.stocks.map(s => `<span class="tag tag-group">${{s.id}} ${{s.name}}</span>`).join(' ');
    html += `<tr><td>${{i+1}}</td><td><b>${{r.group}}</b></td><td><div class="bar-container"><div class="bar bar-up" style="width:${{barW}}%"></div><span>${{r.count}}</span></div></td><td>${{stocks}}</td></tr>`;
  }});
  html += '</table>';
  document.getElementById('ranking-card').innerHTML = html;
}})();

// Turnover
(() => {{
  if (!turnover.length) return;
  const maxAmt = turnover[0].amount;
  let html = '<table><tr><th>#</th><th>族群</th><th>成交金額(億)</th><th></th></tr>';
  turnover.forEach((t, i) => {{
    const barW = (t.amount / maxAmt * 100);
    html += `<tr><td>${{i+1}}</td><td>${{t.group}}</td><td>${{t.amount.toFixed(1)}}</td><td><div class="bar bar-amt" style="width:${{barW}}%;display:inline-block"></div></td></tr>`;
  }});
  html += '</table>';
  document.getElementById('turnover-card').innerHTML = html;
}})();

// Daily Up Tabs
(() => {{
  const tabsEl = document.getElementById('up-tabs');
  const contentEl = document.getElementById('up-content');
  if (!daily.length) {{ contentEl.innerHTML = '<p style="color:var(--text2)">無漲停股</p>'; return; }}

  daily.forEach((day, idx) => {{
    const tab = document.createElement('button');
    tab.className = 'tab' + (idx === daily.length-1 ? ' active' : '');
    tab.textContent = day.date.slice(5);
    tab.onclick = () => {{
      tabsEl.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      contentEl.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
      document.getElementById('day-'+idx).classList.add('active');
    }};
    tabsEl.appendChild(tab);

    const div = document.createElement('div');
    div.id = 'day-'+idx;
    div.className = 'tab-content' + (idx === daily.length-1 ? ' active' : '');

    let tbl = '<table><tr><th>代號</th><th>股名</th><th>漲幅</th><th>強度</th><th>連板</th><th>法人</th><th>族群</th></tr>';
    day.stocks.forEach(s => {{
      const retClass = s.ret >= 0 ? 'up' : 'down';
      const strengthTag = s.strength === 'lock' ? '<span class="tag tag-lock">一字板</span>'
        : s.strength === 'strong' ? '<span class="tag tag-strong">強封</span>' : '';
      const consecTag = s.consec >= 2 ? `<span class="tag tag-consec">${{s.consec}}連板</span>` : '';
      const instTags = s.inst ? s.inst.split(' | ').map(i =>
        i.includes('外資') ? `<span class="tag tag-foreign">${{i}}</span>` : `<span class="tag tag-trust">${{i}}</span>`
      ).join('') : '';
      const groupTags = s.groups.map(g => `<span class="tag tag-group">${{g}}</span>`).join(' ');
      tbl += `<tr><td>${{s.stock}}</td><td>${{s.name}}</td><td class="${{retClass}}">${{(s.ret*100).toFixed(1)}}%</td><td>${{strengthTag}}</td><td>${{consecTag}}</td><td>${{instTags}}</td><td>${{groupTags}}</td></tr>`;
    }});
    tbl += '</table>';
    div.innerHTML = tbl;
    contentEl.appendChild(div);
  }});
}})();

// Heatmap
(() => {{
  const el = document.getElementById('heatmap-card');
  if (!heatmap.dates.length || !heatmap.groups.length) {{ el.innerHTML = '<p style="color:var(--text2)">需要 >=3 天資料</p>'; return; }}
  let html = '<table><tr><th>族群</th>';
  heatmap.dates.forEach(d => html += `<th>${{d.slice(5)}}</th>`);
  html += '</tr>';
  heatmap.groups.forEach((g, gi) => {{
    html += `<tr><td><b>${{g}}</b></td>`;
    heatmap.data[gi].forEach(v => {{
      const cls = v === 0 ? 'heat-0' : v === 1 ? 'heat-1' : v === 2 ? 'heat-2' : v >= 3 ? 'heat-3' : 'heat-0';
      html += `<td class="${{cls}}">${{v || '·'}}</td>`;
    }});
    html += '</tr>';
  }});
  html += '</table>';
  el.innerHTML = html;
}})();

// Laggards
(() => {{
  const el = document.getElementById('laggard-card');
  const groups = Object.keys(laggards);
  if (!groups.length) {{ el.innerHTML = '<p style="color:var(--text2)">無落後候選</p>'; return; }}
  let html = '';
  groups.forEach(g => {{
    html += `<h4 style="color:var(--accent);margin:10px 0 5px">【${{g}}】</h4>`;
    html += '<table><tr><th>代號</th><th>股名</th><th>近5日漲幅</th></tr>';
    laggards[g].forEach(s => {{
      const cls = s.ret >= 0 ? 'up' : '';
      html += `<tr><td>${{s.stock}}</td><td>${{s.name}}</td><td class="${{cls}}">${{s.ret.toFixed(1)}}%</td></tr>`;
    }});
    html += '</table>';
  }});
  el.innerHTML = html;
}})();

// Down
(() => {{
  const el = document.getElementById('down-card');
  if (!dailyDown.length) {{ el.innerHTML = '<p style="color:var(--text2)">無跌停股 ✅</p>'; return; }}
  let html = '';
  dailyDown.forEach(day => {{
    html += `<h4 style="margin:10px 0 5px">${{day.date}}</h4>`;
    html += '<table><tr><th>代號</th><th>股名</th><th>跌幅</th><th>族群</th></tr>';
    day.stocks.forEach(s => {{
      const groupTags = s.groups.map(g => `<span class="tag tag-group">${{g}}</span>`).join(' ') || '（無分類）';
      html += `<tr><td>${{s.stock}}</td><td>${{s.name}}</td><td class="down">${{(s.ret*100).toFixed(1)}}%</td><td>${{groupTags}}</td></tr>`;
    }});
    html += '</table>';
  }});
  el.innerHTML = html;
}})();
</script>
</body>
</html>"""

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"\n📄 HTML 報表已產生: {output_path}")
    return output_path


# ─────────────────── 主程式 ───────────────────

def main():
    parser = argparse.ArgumentParser(description='族群漲停追蹤器 v2')
    parser.add_argument('--days', type=int, default=1, help='分析最近N個交易日')
    parser.add_argument('--start', type=str, default=None, help='起始日期 (YYYY-MM-DD)')
    parser.add_argument('--end', type=str, default=None, help='結束日期 (YYYY-MM-DD)')
    parser.add_argument('--html', action='store_true', help='產生HTML互動式報表')
    parser.add_argument('--output', type=str, default=None, help='HTML輸出路徑')
    args = parser.parse_args()

    d = load_all_data()
    report_data = print_report(args, d)

    if args.html:
        if args.output:
            output_path = args.output
        elif args.start and args.end:
            output_path = os.path.join(os.path.dirname(__file__), '..', f'report_族群追蹤_{args.start}~{args.end}.html')
        else:
            output_path = os.path.join(os.path.dirname(__file__), '..', f'report_族群追蹤_{args.days}日.html')
        generate_html_report(report_data, d, output_path)


if __name__ == '__main__':
    main()
