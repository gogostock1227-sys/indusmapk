"""分析 2730 檔的組成，找出可過濾的下市/權證/ETF 等。"""
import sys
import json
import pandas as pd
from pathlib import Path

sys.path.insert(0, 'site')
from build_site import load_data, _apply_name_overrides

d = load_data(use_cache=True)
close = d["close"]
amount = d["amount"]
name_map = d["name_map"]
market_map = d["market_map"]
industry_map = d["industry_map"]

all_syms = list(close.columns)
print(f"[TOTAL] {len(all_syms)} symbols in cache")

# 1. 近 5 天全 NaN（停牌/下市）
last5 = close.iloc[-5:]
no_price = [s for s in all_syms if last5[s].isna().all()]
print(f"[1] 近 5 日完全無收盤價: {len(no_price)} 檔")

# 2. 近 20 天成交量全 0 或 NaN（實質下市）
if amount is not None:
    last20_amt = amount.iloc[-20:]
    zero_vol = [s for s in all_syms if (last20_amt[s].fillna(0).sum() == 0)]
    print(f"[2] 近 20 日成交額 = 0: {len(zero_vol)} 檔")
else:
    zero_vol = []

# 3. 無 name_map（無正式股名）
no_name = [s for s in all_syms if not (name_map.get(s) and name_map.get(s).strip() and name_map.get(s).strip() != s)]
print(f"[3] 無正式股名 (name_map 無或 == sym): {len(no_name)} 檔")

# 4. market tag 異常
markets = {}
for s in all_syms:
    m = market_map.get(s, "")
    markets[m] = markets.get(m, 0) + 1
print(f"[4] market 分布: {markets}")

# 5. 代號長度異常（權證 >= 6 位且以 0 開頭常見權證/牛熊證）
by_len = {}
for s in all_syms:
    by_len[len(s)] = by_len.get(len(s), 0) + 1
print(f"[5] 代號長度分布: {by_len}")

# 合併候選：無價 ∪ 無量 ∪ 無名
merged = set(no_price) | set(zero_vol) | set(no_name)
print(f"\n[FILTER 候選合併]: {len(merged)} 檔（無價 ∪ 無量 ∪ 無名）")
print(f"  → 只剩 {len(all_syms) - len(merged)} 檔可視為 active")

# 取樣看看有哪些
samples = sorted(merged)[:30]
print(f"\n[樣本 30] {samples}")

# 查 no_price 中有沒有熟悉公司
known_concepts = set()
try:
    from concept_groups import CONCEPT_GROUPS
    for members in CONCEPT_GROUPS.values():
        known_concepts.update(members)
except Exception:
    pass
no_price_in_concepts = [s for s in no_price if s in known_concepts]
print(f"\n[WARN] no_price 但在 concept_groups 裡: {len(no_price_in_concepts)} 檔（這些不該殺）")
print(f"  樣本: {sorted(no_price_in_concepts)[:20]}")

# 最安全的下市候選：無名 AND 無價
strict = [s for s in all_syms if s in no_price and s in no_name]
print(f"\n[STRICT 下市候選 = 無價 AND 無名]: {len(strict)} 檔")
print(f"  樣本: {sorted(strict)[:20]}")
# 寫出到檔案
out = Path("delisted_candidates.json")
out.write_text(json.dumps({
    "total": len(all_syms),
    "no_price": sorted(no_price),
    "zero_vol": sorted(zero_vol),
    "no_name": sorted(no_name),
    "strict_delisted": sorted(strict),
}, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"\n[OK] 寫出: {out}")
