"""
Phase 11 audit — 對 GROUP_GROUND_TRUTH 中每個 (group, ticker)，跑 dominance 驗證
是否「業務簡介或供應鏈段確實提到該族群 keyword」。

如果 dominance 跑 FAIL（不是 ABSTAIN）→ flag 為「人工標錯」，建議從 GROUND_TRUTH 移除。

入口：
  python -m validator.audit_ground_truth        # 印出所有 false GROUND_TRUTH entry
"""
from __future__ import annotations

import sys
from pathlib import Path

TAXONOMY_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TAXONOMY_DIR))

from validator.dominance import score_dominance  # noqa: E402
from validator.pure_play_pipeline import (  # noqa: E402
    AUTO_GROUND_TRUTH_FROM_DESC,
    GROUP_GROUND_TRUTH,
    KEYWORD_EXPANSIONS,
)


def load_finlab_names() -> dict[str, str]:
    import pandas as pd
    df = pd.read_parquet(TAXONOMY_DIR / "validator" / "cache" / "finlab_snapshot.parquet")
    return df.set_index("symbol")["公司簡稱"].to_dict()


def load_specs() -> dict:
    import json
    return json.loads((TAXONOMY_DIR / "group_specs.json").read_text(encoding="utf-8"))


def main():
    n2 = load_finlab_names()
    specs = load_specs()
    failed_entries = []

    print(f"審計 GROUP_GROUND_TRUTH ({sum(len(v) for v in GROUP_GROUND_TRUTH.values())} 筆) + AUTO_GROUND_TRUTH ({sum(len(v) for v in AUTO_GROUND_TRUTH_FROM_DESC.values())} 筆)")
    print("=" * 100)

    for source_name, gt_dict in [("MANUAL", GROUP_GROUND_TRUTH), ("AUTO", AUTO_GROUND_TRUTH_FROM_DESC)]:
        for group_name, tickers in gt_dict.items():
            spec = specs.get(group_name, {})
            core_keywords = list(spec.get("core_keywords", []))
            # 加入 KEYWORD_EXPANSIONS
            if group_name in KEYWORD_EXPANSIONS:
                core_keywords.extend(KEYWORD_EXPANSIONS[group_name])
            if not core_keywords:
                continue

            for ticker in tickers:
                vote = score_dominance(ticker, core_keywords, group_name=group_name)
                # FAIL = 業務簡介明確不提族群 keyword 或角色排除
                # ABSTAIN = Coverage 不存在（保留）
                if vote.verdict == "FAIL":
                    failed_entries.append({
                        "source": source_name,
                        "group": group_name,
                        "ticker": ticker,
                        "name": n2.get(ticker, "?"),
                        "reason": vote.reason,
                        "excluded_role": vote.excluded_role,
                    })

    print(f"\n找到 {len(failed_entries)} 筆 ground_truth 實際 dominance FAIL（人工標錯候選）：\n")
    # group by source
    for src in ("MANUAL", "AUTO"):
        src_entries = [e for e in failed_entries if e["source"] == src]
        if not src_entries:
            continue
        print(f"\n=== {src} ({len(src_entries)} 筆) ===")
        for e in src_entries:
            role_note = f" [角色排除「{e['excluded_role']}」]" if e["excluded_role"] else ""
            print(f"  ✗ {e['ticker']} {e['name']:8s} 在「{e['group']}」: {e['reason'][:80]}{role_note}")

    # 分群統計
    print(f"\n各群錯誤計數：")
    from collections import Counter
    by_group = Counter(e["group"] for e in failed_entries)
    for g, n in by_group.most_common():
        print(f"  {g}: {n} 筆")


if __name__ == "__main__":
    main()
