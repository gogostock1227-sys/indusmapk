"""Full-site concept group verifier.

This layer sits above strict_pipeline_v4:

1. v4 remains the strict evidence engine for the current members.
2. Hard-whitelist / manually reviewed hot themes can override noisy profiles.
3. Broad sector groups use TWSE/FinLab industry tags as primary evidence, so
   groups such as 食品/民生 or 生技醫療 are not incorrectly emptied just because
   they do not mention a market buzzword in the first paragraphs.
4. New additions are intentionally conservative: only exact reviewed lists and
   exact sector-industry matches are auto-added.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from .schema import GroupSpec, StockProfile
from .strict_pipeline_v4 import make_spec, run_full_validation
from .evidence import build_primary_coverage_text, find_coverage_file

ROOT = Path(__file__).resolve().parents[2]
TAXONOMY_DIR = ROOT / "concept_taxonomy"
VALIDATION_RUNS_DIR = TAXONOMY_DIR / "validation_runs"
CONCEPT_GROUPS_PATH = ROOT / "concept_groups.py"
PROFILES_PATH = TAXONOMY_DIR / "stock_profiles.json"


# 使用者明確指定：ABF 載板只認三雄，設備、耗材、材料、鑽孔墊板、通路商一律不放這群。
EXACT_KEEP: dict[str, list[str]] = {
    "ABF載板": ["3037", "8046", "3189"],
    # Google TPU：用本業/供應鏈位階 + 市場公開資料交叉後保留核心設計、代工、封測、基板、測試鏈。
    # 移除純 AI 伺服器、光通訊或一般光電但未直接對應 TPU 供應鏈的個股。
    "Google TPU": ["2330", "2454", "3443", "3037", "2449", "3711", "2360", "6515", "6223", "3661"],
    # 電源供應器/BBU：分成伺服器電源與資料中心 BBU；移除資料錯置或僅通路/軟體角色。
    "電源供應器/BBU": ["2308", "2301", "6412", "6282", "2457", "6781", "3211", "3323", "6121", "5309", "8038", "4931", "3625"],
    # CPU 概念股先不讓文字掃描大幅擴張，只保留 v4 已驗證的 CPU/socket/測試/基板/主機板平台鏈。
    "CPU 概念股": ["5269", "5274", "3515", "3533", "6510", "3037", "8046", "2376", "6515", "3653", "4938"],
    "石英元件": ["3042", "2484", "8182", "8289", "3221"],
    "光通訊/CPO": ["4977", "6451", "3081", "6442", "4971"],
    "矽光子": ["3081", "3339", "3363", "3105", "3450"],
    "記憶體": ["2408", "2344", "2337", "8299", "5289", "3006", "8271", "4973"],
}


# 這些是本業型大族群；可用 TWSE/FinLab 產業分類直接驗證與補漏。
SECTOR_RULES: dict[str, dict] = {
    "食品/民生": {"twse_any": ["食品工業"], "add_all": True},
    "生技醫療": {"twse_any": ["生技醫療業"], "add_all": True},
    "電子通路": {"twse_any": ["電子通路業"], "add_all": True},
    "金融證券": {"twse_any": ["金融保險業"], "add_all": True},
    "遊戲股": {"twse_any": ["文化創意業"], "add_all": False},
    "電腦週邊/配件": {"twse_any": ["電腦及週邊設備業"], "add_all": False},
    "營建/資產": {"twse_any": ["建材營造", "建材營造業"], "add_all": False},
    "鋼鐵": {"twse_any": ["鋼鐵工業"], "add_all": False},
    "航運/物流": {"twse_any": ["航運業"], "add_all": False},
    "觀光餐旅": {"twse_any": ["觀光餐旅"], "add_all": False},
    "紡織成衣": {"twse_any": ["紡織纖維"], "add_all": False},
    "塑化/化工": {"twse_any": ["塑膠工業", "化學工業"], "add_all": False},
    "水泥/建材": {"twse_any": ["水泥工業", "建材營造業"], "add_all": False},
    "電機機械": {"twse_any": ["電機機械"], "add_all": False},
    "電器電纜": {"twse_any": ["電器電纜"], "add_all": False},
    "綠能環保": {"twse_any": ["綠能環保"], "add_all": False},
    "油電燃氣": {"twse_any": ["油電燃氣業"], "add_all": False},
    "資訊服務": {"twse_any": ["資訊服務業", "數位雲端"], "add_all": False},
}


# 文字題材要保守，避免「文化創意業」或「電腦週邊設備業」整包塞進來。
TEXT_RULES: dict[str, dict] = {
}


# 對非熱門題材的本業/產業群，profile 的 theme 缺漏不能直接等同「不是這個族群」。
# 僅用於「原本就在族群內」的個股，避免自動擴張造成概念股灌水。
CURRENT_MEMBER_SEGMENT_PRESERVE = {
    "MED_BIO",
    "CONSUMER",
    "FIN",
    "SOFTWARE",
    "MATERIALS",
    "LOGISTICS",
}


STRICT_NO_AUTO_ADD = {
    "AI伺服器",
    "輝達概念股",
    "蘋果概念股",
    "特斯拉概念股",
    "Meta概念股",
    "AWS概念股",
    "Google TPU",
    "CPU 概念股",
}


def load_current_groups() -> dict[str, list[str]]:
    import importlib
    import concept_groups

    importlib.reload(concept_groups)
    return {g: list(dict.fromkeys(members)) for g, members in concept_groups.CONCEPT_GROUPS.items()}


def load_profiles() -> dict[str, dict]:
    return json.loads(PROFILES_PATH.read_text(encoding="utf-8"))


def collect_report_names() -> dict[str, str]:
    out: dict[str, str] = {}
    reports_dir = ROOT / "My-TW-Coverage" / "Pilot_Reports"
    if not reports_dir.exists():
        return out
    for path in reports_dir.glob("**/*.md"):
        m = re.match(r"^(\d{4,5})_(.+)\.md$", path.name)
        if not m:
            continue
        out.setdefault(m.group(1), m.group(2))
    return out


def make_profile_obj(raw: dict | None) -> StockProfile | None:
    if not raw:
        return None
    return StockProfile(
        ticker=raw.get("ticker", ""),
        name=raw.get("name", ""),
        industry_segment=raw.get("industry_segment", ""),
        supply_chain_position=raw.get("supply_chain_position", ""),
        core_themes=raw.get("core_themes", []),
        business_summary=raw.get("business_summary", ""),
        twse_industry=raw.get("twse_industry", ""),
        confidence=raw.get("confidence", 0.0),
        human_reviewed=raw.get("human_reviewed", False),
    )


def ticker_name(ticker: str, profiles: dict[str, dict], report_names: dict[str, str]) -> str:
    prof = profiles.get(ticker) or {}
    return prof.get("name") or report_names.get(ticker, "")


def matches_twse(prof: dict | None, aliases: list[str]) -> bool:
    if not prof:
        return False
    twse = prof.get("twse_industry", "") or ""
    return any(alias in twse for alias in aliases)


def coverage_text(ticker: str, cache: dict[str, str]) -> str:
    if ticker not in cache:
        text, _meta = build_primary_coverage_text(ticker, max_chars=2600)
        cache[ticker] = text
    return cache[ticker]


def text_rule_hit(ticker: str, rule: dict, profiles: dict[str, dict], cache: dict[str, str]) -> bool:
    prof = profiles.get(ticker) or {}
    if rule.get("twse_any") and not matches_twse(prof, rule["twse_any"]):
        return False
    text = coverage_text(ticker, cache).lower()
    if not text:
        return False
    return any(kw.lower() in text for kw in rule.get("keywords", []))


def structural_current_fallback(
    group_name: str,
    members: list[str],
    spec: GroupSpec,
    profiles: dict[str, dict],
    cache: dict[str, str],
) -> tuple[list[str], dict[str, str]]:
    """Keep current members that still match basic industry/position evidence.

    This is intentionally only for current members, not for adding new stocks.
    It prevents broad non-buzzword groups from being emptied by a missing
    keyword, while still removing obvious segment/position mismatches.
    """
    kept: list[str] = []
    reasons: dict[str, str] = {}
    for ticker in members:
        prof = profiles.get(ticker)
        if not prof:
            text = coverage_text(ticker, cache)
            if any(kw and kw in text for kw in spec.core_keywords):
                kept.append(ticker)
                reasons[ticker] = "Coverage 文字命中族群核心字"
            continue

        segment_ok = (not spec.allowed_segments) or prof.get("industry_segment") in spec.allowed_segments
        primary_segment = spec.allowed_segments[0] if spec.allowed_segments else ""
        preserve_current_by_segment = primary_segment in CURRENT_MEMBER_SEGMENT_PRESERVE
        position_ok = (
            (not spec.allowed_positions)
            or prof.get("supply_chain_position") in spec.allowed_positions
            or preserve_current_by_segment
        )
        forbidden_pos = prof.get("supply_chain_position") in set(spec.forbidden_positions or [])
        forbidden_theme = bool(set(prof.get("core_themes") or []) & set(spec.forbidden_themes or []))
        theme_ok = (not spec.required_themes_any) or bool(set(prof.get("core_themes") or []) & set(spec.required_themes_any))

        if segment_ok and position_ok and not forbidden_pos and not forbidden_theme:
            if theme_ok or not spec.required_themes_any or preserve_current_by_segment:
                kept.append(ticker)
                reasons[ticker] = "stock_profile segment/position 命中；本業型族群保留現有成員"
    return list(dict.fromkeys(kept)), reasons


def sector_keep(
    group_name: str,
    current_members: list[str],
    profiles: dict[str, dict],
    rule: dict,
) -> tuple[list[str], dict[str, str]]:
    aliases = rule.get("twse_any", [])
    candidates = [ticker for ticker, prof in profiles.items() if matches_twse(prof, aliases)]
    if rule.get("add_all"):
        keep = candidates
    else:
        keep = [ticker for ticker in current_members if ticker in set(candidates)]
    reasons = {ticker: f"TWSE/FinLab 產業分類命中：{(profiles.get(ticker) or {}).get('twse_industry', '')}" for ticker in keep}
    return sorted(dict.fromkeys(keep)), reasons


def text_keep(
    group_name: str,
    current_members: list[str],
    profiles: dict[str, dict],
    rule: dict,
    cache: dict[str, str],
) -> tuple[list[str], dict[str, str]]:
    all_tickers = set(current_members) | set(profiles.keys())
    keep: list[str] = []
    reasons: dict[str, str] = {}
    for ticker in sorted(all_tickers):
        if ticker in current_members or rule.get("add_all"):
            if text_rule_hit(ticker, rule, profiles, cache):
                keep.append(ticker)
                reasons[ticker] = f"Coverage 命中文字規則：{', '.join(rule.get('keywords', [])[:4])}"
    return keep, reasons


def should_use_structural_fallback(group_name: str, old_count: int, base_keep_count: int, raw_spec: dict | None) -> bool:
    if group_name in EXACT_KEEP or group_name in SECTOR_RULES or group_name in TEXT_RULES:
        return False
    if not raw_spec or old_count < 5:
        return False
    if group_name in STRICT_NO_AUTO_ADD:
        return False
    if base_keep_count == 0:
        return True
    return base_keep_count / max(old_count, 1) < 0.20 and raw_spec.get("owner_batch") == "auto_generated_v1"


def build_verified_payload() -> dict:
    current_groups = load_current_groups()
    profiles = load_profiles()
    report_names = collect_report_names()
    specs_raw = json.loads((TAXONOMY_DIR / "group_specs.json").read_text(encoding="utf-8"))
    base = run_full_validation()
    base_results = base["results"]

    cache: dict[str, str] = {}
    final_results: dict[str, dict] = {}
    evidence_trail: list[dict] = []
    abstain_rows: list[dict] = []
    summary_rows: list[dict] = []

    for group_name, current_members in current_groups.items():
        raw_spec = specs_raw.get(group_name)
        base_rec = base_results.get(group_name, {})
        base_keep = list(dict.fromkeys(base_rec.get("keep") or (base_rec.get("core", []) + base_rec.get("satellite", []))))
        source = "strict_v4"
        reasons: dict[str, str] = {ticker: "v4 CORE/SATELLITE" for ticker in base_keep}

        if group_name in EXACT_KEEP:
            keep = [ticker for ticker in EXACT_KEEP[group_name] if ticker]
            source = "v5_exact_review"
            reasons = {ticker: "人工覆核硬清單/高風險題材覆核清單" for ticker in keep}
        elif group_name in SECTOR_RULES:
            keep, reasons = sector_keep(group_name, current_members, profiles, SECTOR_RULES[group_name])
            source = "v5_sector_twse"
        elif group_name in TEXT_RULES:
            keep, reasons = text_keep(group_name, current_members, profiles, TEXT_RULES[group_name], cache)
            source = "v5_text_rule"
        elif raw_spec and should_use_structural_fallback(group_name, len(current_members), len(base_keep), raw_spec):
            spec = make_spec(group_name, raw_spec)
            keep, reasons = structural_current_fallback(group_name, current_members, spec, profiles, cache)
            source = "v5_structural_current_fallback"
        elif not raw_spec:
            keep = current_members
            source = "v5_no_spec_preserve"
            reasons = {ticker: "尚未建立 group_spec，先保留原始名單並列入後續補規則" for ticker in keep}
        else:
            keep = base_keep

        keep = list(dict.fromkeys(keep))
        old_set = set(current_members)
        new_set = set(keep)
        added = sorted(new_set - old_set)
        removed = sorted(old_set - new_set)
        abstain = [a for a in base_rec.get("abstain", []) if isinstance(a, str) and a not in new_set]

        removed_detail = []
        for ticker in removed:
            removed_detail.append({
                "ticker": ticker,
                "name": ticker_name(ticker, profiles, report_names),
                "reason": "未通過 v5 最終族群驗證；若是灰色案例請看 abstain_queue.csv",
            })

        final_results[group_name] = {
            "kind": "full_site_v5",
            "core": keep,
            "satellite": [],
            "abstain": abstain,
            "removed": removed_detail,
            "keep": keep,
            "added": added,
            "source": source,
            "validated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }

        summary_rows.append({
            "group": group_name,
            "source": source,
            "old_count": len(current_members),
            "new_count": len(keep),
            "added": len(added),
            "removed": len(removed),
            "abstain": len(abstain),
        })

        for ticker in keep:
            prof = profiles.get(ticker) or {}
            evidence_trail.append({
                "group": group_name,
                "ticker": ticker,
                "ticker_name": ticker_name(ticker, profiles, report_names),
                "verdict": "CORE",
                "source": source,
                "reason": reasons.get(ticker, "v5 final keep"),
                "twse_industry": prof.get("twse_industry", ""),
                "industry_segment": prof.get("industry_segment", ""),
                "supply_chain_position": prof.get("supply_chain_position", ""),
                "core_themes": prof.get("core_themes", []),
                "coverage_path": str(find_coverage_file(ticker).relative_to(ROOT)) if find_coverage_file(ticker) else "",
                "decided_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            })
        for ticker in removed:
            prof = profiles.get(ticker) or {}
            abstain_rows.append({
                "group": group_name,
                "ticker": ticker,
                "name": ticker_name(ticker, profiles, report_names),
                "decision": "REMOVE_FROM_SITE",
                "source": source,
                "reason": "v5 final list excluded this ticker",
                "twse_industry": prof.get("twse_industry", ""),
                "industry_segment": prof.get("industry_segment", ""),
                "supply_chain_position": prof.get("supply_chain_position", ""),
            })

    totals = Counter()
    for row in summary_rows:
        totals["old"] += row["old_count"]
        totals["new"] += row["new_count"]
        totals["added"] += row["added"]
        totals["removed"] += row["removed"]
        totals["abstain"] += row["abstain"]

    return {
        "results": final_results,
        "evidence_trail": evidence_trail,
        "abstain_queue": abstain_rows,
        "summary_rows": summary_rows,
        "summary": {
            "ran_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "groups_evaluated": len(final_results),
            "overall_counts": dict(totals),
            "base_regression": base["summary"]["regression"],
        },
    }


def write_run(payload: dict, run_dir: Path) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "master_patch_v5.json").write_text(
        json.dumps(payload["results"], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    with (run_dir / "evidence_trail.jsonl").open("w", encoding="utf-8") as f:
        for row in payload["evidence_trail"]:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    with (run_dir / "abstain_queue.csv").open("w", encoding="utf-8", newline="") as f:
        fieldnames = ["group", "ticker", "name", "decision", "source", "reason", "twse_industry", "industry_segment", "supply_chain_position"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(payload["abstain_queue"])
    with (run_dir / "full_validation_summary.csv").open("w", encoding="utf-8", newline="") as f:
        fieldnames = ["group", "source", "old_count", "new_count", "added", "removed", "abstain"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(payload["summary_rows"])
    (run_dir / "manifest.json").write_text(
        json.dumps(
            {
                "run_id": run_dir.name,
                "ran_at": payload["summary"]["ran_at"],
                "validator_version": "v5.0.0-full-site",
                "groups_evaluated": payload["summary"]["groups_evaluated"],
                "overall_counts": payload["summary"]["overall_counts"],
                "base_fixtures_pass": f"{payload['summary']['base_regression']['passed']}/{payload['summary']['base_regression']['total']}",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (run_dir / "diff_vs_current.md").write_text(render_diff(payload), encoding="utf-8")


def render_diff(payload: dict, top_n: int = 60) -> str:
    s = payload["summary"]["overall_counts"]
    lines = [
        "# v5 全站族群驗證差異",
        "",
        f"- 族群數：{payload['summary']['groups_evaluated']}",
        f"- 總成員：{s.get('old', 0)} -> {s.get('new', 0)}",
        f"- 新增：+{s.get('added', 0)}",
        f"- 移除：-{s.get('removed', 0)}",
        f"- 待審/不上架：{s.get('abstain', 0)}",
        "",
        f"## 變動最大的 {top_n} 群",
    ]
    rows = sorted(payload["summary_rows"], key=lambda r: r["added"] + r["removed"], reverse=True)
    for row in rows[:top_n]:
        if row["added"] == 0 and row["removed"] == 0:
            continue
        lines.append("")
        lines.append(f"### {row['group']} ({row['old_count']} -> {row['new_count']})")
        lines.append(f"- source: `{row['source']}`")
        lines.append(f"- 新增：+{row['added']}；移除：-{row['removed']}；待審：{row['abstain']}")
    return "\n".join(lines) + "\n"


def render_concept_groups(payload: dict) -> str:
    profiles = load_profiles()
    report_names = collect_report_names()
    current_order = list(load_current_groups().keys())
    groups = payload["results"]
    lines = [
        '"""台股族群名單。',
        "",
        "本檔由 concept_taxonomy.validator.full_group_verifier 產生。",
        "只上架 CORE / 高信心名單；移除與待審案例請查 validation_runs/*_full_v5/。",
        '"""',
        "",
        "CONCEPT_GROUPS = {",
    ]
    for group_name in current_order:
        rec = groups.get(group_name)
        if not rec:
            continue
        keep = rec.get("keep", [])
        lines.append(f'    "{group_name}": [')
        if keep:
            lines.append(f'        # v5 source: {rec.get("source", "")}; count={len(keep)}')
        for ticker in keep:
            name = ticker_name(ticker, profiles, report_names)
            comment = f"  # {name}" if name else ""
            lines.append(f'        "{ticker}",{comment}')
        lines.append("    ],")
    lines.append("}")
    lines.append("")
    return "\n".join(lines)


def apply_to_site(payload: dict, run_dir: Path) -> None:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = CONCEPT_GROUPS_PATH.with_name(f"concept_groups.py.bak_v5_{ts}")
    shutil.copy(CONCEPT_GROUPS_PATH, backup)
    new_src = render_concept_groups(payload)
    CONCEPT_GROUPS_PATH.write_text(new_src, encoding="utf-8")
    shutil.copy(CONCEPT_GROUPS_PATH, run_dir / "snapshot_concept_groups.py")
    print(f"[v5] backup: {backup.name}")
    print(f"[v5] applied concept_groups.py and snapshot saved")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="write validation run")
    ap.add_argument("--apply", action="store_true", help="apply generated groups to concept_groups.py")
    args = ap.parse_args()

    payload = build_verified_payload()
    s = payload["summary"]["overall_counts"]
    print(
        f"[v5] groups={payload['summary']['groups_evaluated']} "
        f"members={s.get('old', 0)}->{s.get('new', 0)} "
        f"added=+{s.get('added', 0)} removed=-{s.get('removed', 0)} abstain={s.get('abstain', 0)}"
    )

    run_dir = VALIDATION_RUNS_DIR / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_full_v5"
    if args.write or args.apply:
        write_run(payload, run_dir)
        print(f"[v5] wrote {run_dir.relative_to(ROOT)}")
    if args.apply:
        apply_to_site(payload, run_dir)


if __name__ == "__main__":
    main()
