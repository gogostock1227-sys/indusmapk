"""
從 finlab 全部 2315 公司簡稱自動 build NAME_ALIASES，取代手動維護。

策略：對每個公司簡稱，產出多個 alias 變體：
  原名: 「全新」「貿聯-KY」「國巨*」
  變體: 「貿聯」(去 -KY) / 「國巨」(去 *) / 「世芯」(KY 主稱)

回 dict[alias → finlab 真名]，可直接覆蓋 sync_ground_truth.py 的 NAME_ALIASES。
"""
from __future__ import annotations

import re
import json
from pathlib import Path

TAXONOMY_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = TAXONOMY_DIR.parent


def build_aliases() -> dict[str, str]:
    """從 finlab snapshot 全自動產 alias map。"""
    import pandas as pd
    df = pd.read_parquet(TAXONOMY_DIR / "validator" / "cache" / "finlab_snapshot.parquet")
    aliases: dict[str, str] = {}

    for _, row in df.iterrows():
        full = str(row["公司簡稱"]).strip()
        if not full or len(full) < 2:
            continue
        # 1. 原名直接 map
        aliases[full] = full
        # 2. 去 *（國巨* / 世紀*）
        clean_star = full.rstrip("*")
        if clean_star != full and len(clean_star) >= 2:
            aliases[clean_star] = full
        # 3. 去 -KY（貿聯-KY → 貿聯）
        clean_ky = re.sub(r"[-－]KY$", "", clean_star)
        if clean_ky != clean_star and len(clean_ky) >= 2:
            aliases[clean_ky] = full
        # 4. 去 控股 / 投控（連展投控 → 連展）
        for suffix in ["投控", "控股", "工業", "企業", "科技", "電子", "電機", "實業"]:
            cleaned = re.sub(rf"{suffix}$", "", clean_ky)
            if cleaned != clean_ky and len(cleaned) >= 2:
                aliases.setdefault(cleaned, full)

    return aliases


def main():
    aliases = build_aliases()
    print(f"自動 build {len(aliases)} 個 alias")
    # 寫成 JSON 給其他模組讀
    out = TAXONOMY_DIR / "validator" / "cache" / "name_aliases_auto.json"
    out.write_text(json.dumps(aliases, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✓ 寫 {out}")


if __name__ == "__main__":
    main()
