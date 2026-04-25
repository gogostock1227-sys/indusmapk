"""
Day 6：產出人類可讀的驗證報告。

入口：
    python -m validator.report                  # 寫所有群報告 + 總報告
    python -m validator.report --group HBM 高頻寬記憶體   # 只寫單群

產出：
  - concept_taxonomy/reports/{group}.md  （每群一份）
  - concept_taxonomy/_VERIFICATION_REPORT_v2.md  （總報告）
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

TAXONOMY_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = TAXONOMY_DIR.parent
sys.path.insert(0, str(TAXONOMY_DIR))

REPORTS_DIR = TAXONOMY_DIR / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def load_data():
    df = pd.read_parquet(TAXONOMY_DIR / "validation_results.parquet")
    specs = json.loads((TAXONOMY_DIR / "group_specs.json").read_text(encoding="utf-8"))
    profiles = json.loads((TAXONOMY_DIR / "stock_profiles.json").read_text(encoding="utf-8"))
    return df, specs, profiles


def safe_filename(group_name: str) -> str:
    return group_name.replace("/", "_").replace(" ", "_").replace("\\", "_")


def build_group_report(group: str, df_g: pd.DataFrame, spec: dict, profiles: dict) -> str:
    """產單一群的 markdown 報告。"""
    counts = Counter(df_g["verdict"])
    avg_conf = df_g["confidence"].mean() if len(df_g) else 0.0

    lines = [
        f"# {group} — 驗證報告 v2",
        "",
        f"> 生成於 {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        f"> 三維 spec：allowed_segments={spec.get('allowed_segments')} / "
        f"allowed_positions={spec.get('allowed_positions')} / "
        f"required_themes_any={spec.get('required_themes_any')}",
        "",
        f"## 小結",
        f"",
        f"| 判決 | 檔數 |",
        f"|---|---:|",
        f"| 🟢 core | {counts.get('core', 0)} |",
        f"| 🟡 satellite | {counts.get('satellite', 0)} |",
        f"| 🔴 remove | {counts.get('remove', 0)} |",
        f"| ⚪ skipped (profile 不完整) | {counts.get('skipped', 0)} |",
        f"| **總計** | **{len(df_g)}** |",
        "",
        f"平均信心：**{avg_conf:.2f}**",
        "",
    ]

    # CORE
    core_df = df_g[df_g["verdict"] == "core"].sort_values("confidence", ascending=False)
    if len(core_df):
        lines.append(f"## 🟢 核心成分股（{len(core_df)} 檔）")
        lines.append("")
        for _, row in core_df.iterrows():
            p = profiles.get(row["ticker"], {})
            pos = p.get("supply_chain_position", "")
            themes = p.get("core_themes", [])
            lines.append(f"- **{row['ticker']} {row['name']}** "
                         f"`pos={pos}` `themes={themes}` （信心 {row['confidence']:.2f}）")
        lines.append("")

    # SATELLITE
    sat_df = df_g[df_g["verdict"] == "satellite"].sort_values("confidence", ascending=False)
    if len(sat_df):
        lines.append(f"## 🟡 衛星成分股（{len(sat_df)} 檔）")
        lines.append("")
        for _, row in sat_df.iterrows():
            p = profiles.get(row["ticker"], {})
            pos = p.get("supply_chain_position", "")
            lines.append(f"- {row['ticker']} {row['name']} `pos={pos}` "
                         f"（信心 {row['confidence']:.2f}；{row['rationale'][:60]}...）")
        lines.append("")

    # REMOVE
    rm_df = df_g[df_g["verdict"] == "remove"].sort_values("confidence", ascending=False)
    if len(rm_df):
        lines.append(f"## 🔴 應移除（{len(rm_df)} 檔）")
        lines.append("")
        lines.append("| 代號 | 公司 | 移除原因 | 信心 |")
        lines.append("|---|---|---|---:|")
        for _, row in rm_df.iterrows():
            reason = row["hard_fail_reason"] or row["rationale"][:80]
            lines.append(f"| {row['ticker']} | {row['name']} | {reason} | {row['confidence']:.2f} |")
        lines.append("")

    # SKIPPED
    sk_df = df_g[df_g["verdict"] == "skipped"]
    if len(sk_df):
        lines.append(f"## ⚪ 跳過（profile 待補完）（{len(sk_df)} 檔）")
        lines.append("")
        for _, row in sk_df.iterrows():
            lines.append(f"- {row['ticker']} {row['name']}：{row['rationale']}")
        lines.append("")

    return "\n".join(lines)


def build_overall_report(df: pd.DataFrame, specs: dict) -> str:
    """總報告：跨群統計 + 結構問題清單。"""
    lines = [
        "# 族群三維驗證 — 總報告 v2",
        "",
        f"> 生成於 {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        f"> 驗證 pair 數：**{len(df)}**",
        "",
        "## 全局判決分布",
        "",
    ]
    counts = Counter(df["verdict"])
    total = len(df)
    for v in ["core", "satellite", "remove", "skipped"]:
        n = counts.get(v, 0)
        lines.append(f"- {v}: **{n}** ({n/total*100:.1f}%)")
    lines.append("")
    lines.append(f"平均信心：**{df['confidence'].mean():.2f}**")
    lines.append("")

    # Hard fail 數
    hf = df[df["hard_fail_reason"].fillna("") != ""]
    lines.append(f"Hard-fail 抓出：**{len(hf)}** 檔（強制 remove）")
    lines.append("")

    # TOP 應移除最多的族群
    by_g = df[df["verdict"] == "remove"].groupby("group").size().sort_values(ascending=False)
    lines.append("## TOP 20 應移除最多的族群")
    lines.append("")
    lines.append("| # | 族群 | 應移除 | 群總數 | 移除率 |")
    lines.append("|---|---|---:|---:|---:|")
    for i, (g, n) in enumerate(by_g.head(20).items(), 1):
        total_g = len(df[df["group"] == g])
        lines.append(f"| {i} | {g} | {n} | {total_g} | {n/total_g*100:.0f}% |")
    lines.append("")

    # 結構問題
    deprecated = [n for n, s in specs.items() if not n.startswith("_") and s.get("deprecated")]
    merged = [(n, s.get("merge_into")) for n, s in specs.items()
              if not n.startswith("_") and s.get("merge_into")]
    lines.append("## 結構問題清單")
    lines.append("")
    if deprecated:
        lines.append(f"### 🟠 過時 / 抽象族群（建議廢除，{len(deprecated)} 群）")
        lines.append("")
        for g in deprecated:
            spec = specs[g]
            reason = spec.get("deprecation_reason", "(無)")
            reclassify = spec.get("members_reclassify_to", [])
            lines.append(f"- **{g}** — {reason}")
            if reclassify:
                lines.append(f"  - 成員重歸至：{reclassify}")
        lines.append("")
    if merged:
        lines.append(f"### 🟣 重複族群（建議合併，{len(merged)} 群）")
        lines.append("")
        for g, target in merged:
            lines.append(f"- **{g}** → 合併進 `{target}`")
        lines.append("")

    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--group", help="只產單群（支援部分匹配）")
    args = ap.parse_args()

    print("[1/3] 載入資料 ...")
    df, specs, profiles = load_data()
    print(f"  {len(df)} pair, {len(specs)} specs, {len(profiles)} profiles")

    print("[2/3] 產各群報告 ...")
    n = 0
    target_groups = df["group"].unique() if not args.group else [g for g in df["group"].unique() if args.group in g]
    for g in target_groups:
        df_g = df[df["group"] == g]
        spec = specs.get(g, {})
        report = build_group_report(g, df_g, spec, profiles)
        out = REPORTS_DIR / f"{safe_filename(g)}.md"
        out.write_text(report, encoding="utf-8")
        n += 1
    print(f"  ✓ 寫 {n} 份群報告到 {REPORTS_DIR}")

    if not args.group:
        print("[3/3] 產總報告 ...")
        overall = build_overall_report(df, specs)
        out = TAXONOMY_DIR / "_VERIFICATION_REPORT_v2.md"
        out.write_text(overall, encoding="utf-8")
        print(f"  ✓ {out}")


if __name__ == "__main__":
    main()
