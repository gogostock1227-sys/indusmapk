"""
Phase 10 自我大檢查 — 找出所有「ai 描述龍頭 vs 成分股」不一致 + 系統性問題。

5 個自查維度：
  D1. industry_meta.py desc 提及但 finlab name_map 抓不到的公司名（漏 NAME_ALIASES）
  D2. AUTO_GROUND_TRUTH ticker 不在 concept_groups.py 該群 list 中（apply 失敗）
  D3. concept_groups.py 中的中文註解 vs finlab 真實公司名不符（亂寫註解）
  D4. dominance keep_rate < 25% 的剩餘群（仍過 prune）
  D5. industry_meta 有 desc 但 group_specs.json 沒對應 spec 的群（spec 缺漏）
"""
from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

TAXONOMY_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = TAXONOMY_DIR.parent
sys.path.insert(0, str(TAXONOMY_DIR))

from validator.sync_ground_truth import NAME_ALIASES  # noqa: E402


def load_industry_meta() -> dict:
    spec = importlib.util.spec_from_file_location(
        "industry_meta", PROJECT_ROOT / "site" / "industry_meta.py"
    )
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m.INDUSTRY_META


def load_finlab_name_to_ticker() -> dict[str, str]:
    import pandas as pd
    df = pd.read_parquet(TAXONOMY_DIR / "validator" / "cache" / "finlab_snapshot.parquet")
    return df.set_index("公司簡稱")["symbol"].to_dict()


def load_finlab_ticker_to_name() -> dict[str, str]:
    import pandas as pd
    df = pd.read_parquet(TAXONOMY_DIR / "validator" / "cache" / "finlab_snapshot.parquet")
    return df.set_index("symbol")["公司簡稱"].to_dict()


def parse_concept_groups() -> dict[str, list[tuple[str, str]]]:
    src = (PROJECT_ROOT / "concept_groups.py").read_text(encoding="utf-8")
    pattern = re.compile(r'"([^"]+?)"\s*:\s*\[(.*?\n    \]),', re.DOTALL)
    result = {}
    for m in pattern.finditer(src):
        group = m.group(1)
        if group == "_meta":
            continue
        body = m.group(2)
        items = []
        for tk_m in re.finditer(r'"(\d{4,5})"\s*,?\s*(?:#\s*([^\n]*))?', body):
            items.append((tk_m.group(1), (tk_m.group(2) or "").strip()))
        if items:
            result[group] = items
    return result


def main():
    meta = load_industry_meta()
    n2t = load_finlab_name_to_ticker()
    t2n = load_finlab_ticker_to_name()
    groups = parse_concept_groups()

    print("=" * 100)
    print("Phase 10 自我大檢查 — 系統性問題盤點")
    print("=" * 100)

    # === D1. desc 提及公司名但漏抓 ===
    print("\n[D1] industry_meta desc 提及公司名但 NAME_ALIASES 漏抓")
    print("-" * 100)
    miss_aliases = []
    # 從 desc 抓中文公司名 patterns（簡單啟發：2-4 個中文字 + ）
    chinese_company_pattern = re.compile(r"[一-龥]{2,5}(?=[、）\)\(（。\s,，])")
    for g, info in meta.items():
        if not isinstance(info, dict):
            continue
        desc = info.get("desc", "") + " " + " ".join(
            ind.get("value", "") for ind in info.get("indicators", []) if isinstance(ind, dict)
        )
        candidates = chinese_company_pattern.findall(desc)
        for cand in candidates:
            if cand in NAME_ALIASES:
                continue
            # 直接從 finlab 反查
            if cand in n2t:
                miss_aliases.append((g, cand, n2t[cand]))
    # 去重
    seen = set()
    unique_miss = []
    for g, cand, tk in miss_aliases:
        if (cand, tk) not in seen:
            seen.add((cand, tk))
            unique_miss.append((g, cand, tk))
    print(f"找到 {len(unique_miss)} 個漏抓的公司名（NAME_ALIASES 應加）")
    for g, cand, tk in unique_miss[:30]:
        print(f"  「{cand}」({tk}) ← {g}")

    # === D2. AUTO_GT ticker 不在 group list ===
    print("\n[D2] AUTO_GROUND_TRUTH 中的 ticker 不在 concept_groups.py 該群")
    print("-" * 100)
    from validator.pure_play_pipeline import AUTO_GROUND_TRUTH_FROM_DESC, GROUP_GROUND_TRUTH
    missing_apply = []
    for g, expected_tickers in {**AUTO_GROUND_TRUTH_FROM_DESC, **GROUP_GROUND_TRUTH}.items():
        actual = {t for t, _ in groups.get(g, [])}
        for tk in expected_tickers:
            if tk not in actual:
                missing_apply.append((g, tk, t2n.get(tk, "?")))
    print(f"找到 {len(missing_apply)} 個 ground truth 沒進到 concept_groups.py")
    for g, tk, name in missing_apply[:30]:
        print(f"  {tk} {name} 應在「{g}」但不在")

    # === D3. 中文註解 vs finlab 真名不符 ===
    print("\n[D3] concept_groups.py 中文註解錯寫")
    print("-" * 100)
    wrong_comments = []
    for g, items in groups.items():
        for tk, comment in items:
            if not comment:
                continue
            real_name = t2n.get(tk)
            if not real_name:
                continue
            # 註解第一個 token 應該等於 real_name
            first_token = re.match(r"^([^\s—\-\[]+)", comment)
            if first_token:
                first_word = first_token.group(1).strip()
                if first_word and first_word != real_name and first_word not in real_name and real_name not in first_word:
                    wrong_comments.append((g, tk, first_word, real_name))
    print(f"找到 {len(wrong_comments)} 個註解錯寫")
    for g, tk, written, real in wrong_comments[:20]:
        print(f"  {tk} 在「{g}」註解寫「{written}」實際 finlab = 「{real}」")

    # === D4. 仍過 prune (keep < 5 且 keep_rate < 25%) ===
    print("\n[D4] 仍過 prune 的 strict 群（keep < 5 且 keep_rate < 25%）")
    print("-" * 100)
    patch = json.loads((TAXONOMY_DIR / "master_patch_v3.json").read_text(encoding="utf-8"))
    over_prune = []
    for g, p in patch.items():
        if g.startswith("_") or p.get("deprecated") or p.get("merge_into"):
            continue
        if "permissive" in p.get("source", ""):
            continue
        keep = len(p.get("keep", []))
        removed = len(p.get("removed", []))
        total = keep + removed
        if total > 5 and keep < 5 and (keep / total) < 0.25:
            over_prune.append((g, keep, total))
    print(f"找到 {len(over_prune)} 個過 prune 群")
    for g, k, t in over_prune[:30]:
        print(f"  {g}: keep {k}/{t}")

    # === D5. industry_meta 有 desc 但無 spec ===
    print("\n[D5] industry_meta 有族群但 group_specs.json 沒對應 spec")
    print("-" * 100)
    specs = json.loads((TAXONOMY_DIR / "group_specs.json").read_text(encoding="utf-8"))
    missing_specs = []
    for g in meta.keys():
        if g not in specs and g not in groups:
            missing_specs.append(g)
    print(f"找到 {len(missing_specs)} 個 industry_meta 有但 spec/groups 沒")
    for g in missing_specs[:30]:
        print(f"  {g}")

    print("\n" + "=" * 100)
    print(f"📊 總結：")
    print(f"  D1 漏抓公司名：{len(unique_miss)}")
    print(f"  D2 ground_truth 沒套用：{len(missing_apply)}")
    print(f"  D3 註解錯寫：{len(wrong_comments)}")
    print(f"  D4 仍過 prune 群：{len(over_prune)}")
    print(f"  D5 missing spec：{len(missing_specs)}")
    print("=" * 100)


if __name__ == "__main__":
    main()
