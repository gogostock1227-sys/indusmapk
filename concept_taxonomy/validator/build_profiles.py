"""
Day 5：為所有出現在 concept_groups.py 的 unique tickers 建立 stock_profiles.json。

Profile 推論策略：
  1. industry_segment：finlab 產業類別 → TWSE_TO_SEGMENT 表（baseline）
  2. supply_chain_position：
       (a) 若該股 fixture 已存在 → 採用
       (b) 若 Coverage 命中位階關鍵字（Socket/連接器/MLCC/封測 等）→ 推 position
       (c) 否則用「該股身處哪些族群 ∩ 各族群 allowed_positions」取交集眾數
       (d) 都失敗 → 留空，待 Day 6 LLM 補
  3. core_themes：Coverage 命中題材 enum 關鍵字 + 族群身份反推

進度：純規則 baseline，不呼叫 LLM。Coverage 命中率高時準度可達 80%+。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

TAXONOMY_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = TAXONOMY_DIR.parent
sys.path.insert(0, str(TAXONOMY_DIR))

from validator.evidence import (  # noqa: E402
    extract_coverage,
    find_coverage_file,
    infer_segment_from_twse,
    infer_segment_with_coverage,
    load_finlab_snapshot,
    lookup_finlab,
)
from validator.schema import (  # noqa: E402
    CORE_THEME_ENUMS,
    SUPPLY_CHAIN_POSITIONS,
)


# ─────────────────────────────────────────────────────────────────────────────
# Coverage 關鍵字 → 位階 / 題材對應
# ─────────────────────────────────────────────────────────────────────────────
POSITION_KEYWORDS: list[tuple[str, str]] = [
    # ═══════════════════════════════════════════════════════════
    # 第一層：高特異性 / 反模式優先（先 match 才能 override 後面通用詞）
    # ═══════════════════════════════════════════════════════════
    # 矽晶圓必須在「晶圓代工」之前（否則 6488 環球晶 / 3532 台勝科會被誤判）
    ("12 吋拋光晶圓", "MAT_WAFER"), ("12 吋晶圓", "MAT_WAFER"), ("拋光晶圓", "MAT_WAFER"),
    ("矽晶圓供應", "MAT_WAFER"), ("矽晶圓 廠", "MAT_WAFER"), ("矽晶圓上游", "MAT_WAFER"),
    ("大尺寸晶圓", "MAT_WAFER"), ("magnaboard", "MAT_WAFER"), ("Wafer 代理", "DISTRIB"),
    # 服務業必須在「品牌」「ODM」之前（否則 5871 中租 / 9917 中保科會被誤判）
    ("金融租賃", "END_USER"), ("融資租賃", "END_USER"), ("汽車金融", "END_USER"), ("汽車融資", "END_USER"),
    ("房屋仲介", "END_USER"), ("房地產仲介", "END_USER"), ("不動產仲介", "END_USER"),
    ("保全服務", "END_USER"), ("保全集團", "END_USER"), ("物業管理", "END_USER"),
    ("殯葬服務", "END_USER"), ("殯葬業", "END_USER"), ("生前契約", "END_USER"),
    ("補教", "END_USER"), ("補習班", "END_USER"), ("教育機構", "END_USER"),
    ("飯店", "END_USER"), ("旅館", "END_USER"), ("觀光", "END_USER"), ("郵輪", "END_USER"),
    ("印刷業", "BRAND"), ("商業印刷", "BRAND"),
    ("無人機系統整合", "ODM_SYS"), ("無人機整合", "ODM_SYS"), ("國防電子整合", "ODM_SYS"),
    ("系統整合服務", "SVC_SAAS"), ("系統整合 (SI)", "SVC_SAAS"), ("資訊服務", "SVC_SAAS"),
    ("控股公司", "END_USER"), ("投資控股", "END_USER"),
    # ═══════════════════════════════════════════════════════════
    # 第二層：半導體核心位階
    # ═══════════════════════════════════════════════════════════
    ("矽智財", "IP"), ("Silicon IP", "IP"), ("IP 廠", "IP"),
    ("ASIC 設計服務", "ASIC_SVC"), ("Design Service", "ASIC_SVC"),
    ("晶圓代工", "FOUNDRY"), ("Foundry", "FOUNDRY"),
    ("DRAM 製造", "IDM_DRAM"), ("DRAM IDM", "IDM_DRAM"),
    ("NAND Flash 製造", "IDM_NAND"), ("NAND IDM", "IDM_NAND"),
    ("先進封裝", "OSAT_ADV"), ("CoWoS 封測", "OSAT_ADV"), ("HBM 封測", "OSAT_ADV"),
    ("封裝測試", "OSAT_TRAD"), ("OSAT", "OSAT_TRAD"),
    ("探針卡", "TEST_INTF"), ("測試介面", "TEST_INTF"), ("測試座", "TEST_INTF"),
    ("測試代工", "TEST_SVC"),
    ("半導體設備", "EQUIP"), ("濕製程設備", "EQUIP"), ("微影設備", "EQUIP"),
    ("矽晶圓", "MAT_WAFER"),  # 兜底（前面特化詞已先 match）
    ("特用氣體", "MAT_CHEM"), ("光阻液", "MAT_CHEM"), ("研磨液", "MAT_CHEM"),
    ("半導體化學品", "MAT_CHEM"),
    ("ABF 載板", "SUBSTRATE"), ("BT 載板", "SUBSTRATE"), ("IC 載板", "SUBSTRATE"),
    ("IC 設計", "IC_DESIGN"), ("Fabless", "IC_DESIGN"),
    # ═══════════════════════════════════════════════════════════
    # 第三層：電子零組件
    # ═══════════════════════════════════════════════════════════
    ("連接器", "CONNECTOR"), ("Socket", "CONNECTOR"), ("UQD", "CONNECTOR"),
    ("MLCC", "PASSIVE"), ("被動元件", "PASSIVE"), ("晶振", "PASSIVE"),
    ("HDI PCB", "PCB_HDI"), ("高階 PCB", "PCB_HDI"), ("CCL", "PCB_HDI"),
    ("軟板", "PCB_FPC"), ("FPC", "PCB_FPC"),
    ("散熱模組", "THERMAL"), ("液冷", "THERMAL"), ("CDU", "THERMAL"), ("熱交換器", "THERMAL"),
    ("機構件", "CHASSIS"), ("機殼", "CHASSIS"),
    # ═══════════════════════════════════════════════════════════
    # 第四層：系統/應用/通路
    # ═══════════════════════════════════════════════════════════
    ("ODM", "ODM_SYS"), ("代工組裝", "ODM_SYS"), ("EMS", "ODM_SYS"),
    ("品牌商", "BRAND"), ("自有品牌", "BRAND"),
    ("POS", "END_USER"), ("Kiosk", "END_USER"), ("整機廠", "END_USER"),
    ("零售終端", "END_USER"), ("實體門市", "END_USER"),
    ("通路代理", "DISTRIB"), ("半導體通路", "DISTRIB"), ("代理商", "DISTRIB"),
    ("電子通路", "DISTRIB"),
    # ═══════════════════════════════════════════════════════════
    # 第五層：電源 / 光通訊 / 軟體
    # ═══════════════════════════════════════════════════════════
    ("電源供應", "POWER_MOD"), ("BBU", "POWER_MOD"), ("HVDC", "POWER_MOD"), ("UPS", "POWER_MOD"),
    ("光收發模組", "OPTIC_MOD"), ("光模組", "OPTIC_MOD"),
    ("光通訊元件", "OPTIC_COMP"), ("光被動元件", "OPTIC_COMP"),
    ("SaaS", "SVC_SAAS"), ("軟體服務", "SVC_SAAS"), ("雲端服務", "SVC_SAAS"),
    # ═══════════════════════════════════════════════════════════
    # 第六層：通用詞兜底（避免落空）
    # ═══════════════════════════════════════════════════════════
    ("品牌", "BRAND"),
    ("代工", "ODM_SYS"),
]

THEME_KEYWORDS: list[tuple[str, str]] = [
    ("HBM3E", "HBM3E_HBM4"), ("HBM4", "HBM3E_HBM4"), ("HBM 高頻寬", "HBM3E_HBM4"),
    ("DDR5", "DDR5_RISE"),
    ("Niche DRAM", "NICHE_DRAM"), ("利基型 DRAM", "NICHE_DRAM"),
    ("aiDAPTIV", "aiDAPTIV"),
    ("NAND Flash", "NAND_TIGHT"),
    ("SoCAMM", "SOCAMM2"),
    ("CoWoS", "COWOS"), ("CoWoP", "COWOP"),
    ("SoIC", "SOIC_3D"),
    ("FOPLP", "FOPLP"), ("面板級扇出", "FOPLP"),
    ("Wafer on Wafer", "WOW"),
    ("GB300", "GB300_RUBIN"), ("GB200", "GB300_RUBIN"), ("Rubin", "GB300_RUBIN"), ("Blackwell", "GB300_RUBIN"),
    ("Trainium", "ASIC_TRAINIUM"),
    ("TPU", "ASIC_TPU"),
    ("MTIA", "ASIC_MTIA"),
    ("矽光子", "CPO_PHOTONIC"), ("CPO", "CPO_PHOTONIC"), ("共封裝光學", "CPO_PHOTONIC"),
    ("800G", "OPTIC_800G_1.6T"), ("1.6T", "OPTIC_800G_1.6T"),
    ("SerDes", "SERDES_224G"), ("224G", "SERDES_224G"),
    ("VCSEL", "VCSEL"),
    ("液冷", "LIQUID_COOL"),
    ("HVDC 800V", "HVDC_800V"),
    ("BBU", "BBU"),
    ("2nm", "N2_2NM"), ("2 奈米", "N2_2NM"),
    ("3nm", "N3_3NM"), ("3 奈米", "N3_3NM"),
    ("EUV", "EUV_RISE"),
    ("玻璃基板", "GLASS_GCS"),
    ("AI GPU 測試", "AI_GPU_TEST"),
    ("HBM 測試", "HBM_TEST"),
    ("EV 電池", "EV_BATTERY"), ("電動車電池", "EV_BATTERY"), ("動力電池", "EV_BATTERY"),
    ("低軌衛星", "LEO_SAT"),
    ("量子電腦", "QUANTUM"),
    ("人形機器人", "ROBOTICS"), ("機器人", "ROBOTICS"),
    ("GLP-1", "GLP1_OBESITY"), ("減重新藥", "GLP1_OBESITY"),
    ("Wi-Fi 7", "WIFI7"),
    ("5G ", "5G_6G"), ("6G", "5G_6G"),
    ("Chiplet", "CHIPLET"), ("小晶片", "CHIPLET"),
    ("ADAS", "ADAS"),
    ("CDMO", "CDMO_BIO"),
]


def parse_concept_groups() -> dict[str, list[str]]:
    src = (PROJECT_ROOT / "concept_groups.py").read_text(encoding="utf-8")
    pattern = re.compile(r'"([^"]+?)"\s*:\s*\[(.*?)\]', re.DOTALL)
    result = {}
    for m in pattern.finditer(src):
        name = m.group(1)
        if name == "_meta":
            continue
        tickers = re.findall(r'"(\d{4,5})"', m.group(2))
        if tickers:
            result[name] = tickers
    return result


def build_groups_index(groups: dict[str, list[str]]) -> dict[str, list[str]]:
    """反轉：{ticker: [groups it belongs to]}。"""
    idx: dict[str, list[str]] = {}
    for g, tickers in groups.items():
        for t in tickers:
            idx.setdefault(t, []).append(g)
    return idx


def detect_position(coverage_text: str) -> tuple[str, str]:
    """從 coverage 全文 hit position 關鍵字。回 (position, matched_keyword) 或 ("", "")."""
    if not coverage_text:
        return "", ""
    for kw, pos in POSITION_KEYWORDS:
        if kw in coverage_text:
            return pos, kw
    return "", ""


def detect_themes(coverage_text: str, max_themes: int = 3) -> list[str]:
    """從 coverage 全文 hit theme enum 關鍵字。回最多 N 個。"""
    if not coverage_text:
        return []
    hits: list[str] = []
    seen = set()
    for kw, theme in THEME_KEYWORDS:
        if kw in coverage_text and theme not in seen:
            hits.append(theme)
            seen.add(theme)
            if len(hits) >= max_themes:
                break
    return hits


def vote_position_from_groups(
    ticker: str,
    groups_idx: dict[str, list[str]],
    specs: dict,
) -> str:
    """看該股屬於哪些族群，取那些族群 allowed_positions 的眾數位階作為推論。"""
    pos_counter: Counter = Counter()
    for g in groups_idx.get(ticker, []):
        spec = specs.get(g, {})
        for p in spec.get("allowed_positions", []):
            pos_counter[p] += 1
    if not pos_counter:
        return ""
    return pos_counter.most_common(1)[0][0]


def build_profile(
    ticker: str,
    snapshot,
    groups_idx: dict[str, list[str]],
    specs: dict,
    fixture_profiles: dict,
    manual_overrides: dict | None = None,
) -> dict:
    """為單一個股產 profile。

    優先序：manual_overrides > fixture > Coverage heuristic > group voting
    """
    manual_overrides = manual_overrides or {}

    # 0. manual_overrides 優先（人工 ground truth；regex 撞 bug 的最終解）
    if ticker in manual_overrides:
        p = dict(manual_overrides[ticker])
        p["last_validated"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        p["confidence"] = 0.95
        p["human_reviewed"] = True
        return p

    # 1. fixture 次之
    if ticker in fixture_profiles:
        p = dict(fixture_profiles[ticker])
        p["last_validated"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        p["confidence"] = 0.95  # human-curated
        p["human_reviewed"] = True
        return p

    # 2. finlab 拉基本資料
    fl = lookup_finlab(ticker, snapshot)
    if not fl["found"]:
        return {
            "ticker": ticker,
            "name": "",
            "industry_segment": "",
            "supply_chain_position": "",
            "core_themes": [],
            "business_summary": "",
            "twse_industry": "",
            "cite_sources": [],
            "confidence": 0.0,
            "last_validated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "human_reviewed": False,
            "_skip_reason": "finlab_not_found",
        }

    # 3. Coverage 抽全文（先抓，後面 segment 推論用得到）
    cov_path = find_coverage_file(ticker)
    cov_text = cov_path.read_text(encoding="utf-8") if cov_path else ""
    coverage_folder = cov_path.parent.name if cov_path else ""

    # finlab 主、Coverage industry_folder 次（金融/服務業 finlab 標「其他」走這條）
    seg = infer_segment_with_coverage(fl["twse_industry"], coverage_folder) or ""

    # 4. Position 推論
    pos, kw_pos = detect_position(cov_text)
    pos_source = f"coverage:{kw_pos}" if pos else ""
    if not pos:
        pos = vote_position_from_groups(ticker, groups_idx, specs)
        if pos:
            pos_source = "group_vote"

    # 5. Themes
    themes = detect_themes(cov_text)

    # 6. 信心：依證據強度估
    confidence = 0.30
    if cov_path:
        confidence += 0.30
    if pos:
        confidence += 0.20
    if themes:
        confidence += 0.10
    confidence = min(confidence, 0.85)  # 非人工 cap 0.85

    # 7. cite_sources
    cite = [{"type": "finlab", "field": "產業類別", "value": fl["twse_industry"]}]
    if cov_path:
        cite.append({
            "type": "coverage",
            "path": str(cov_path.relative_to(PROJECT_ROOT)),
            "section": "業務簡介",
            "quote": "(自動偵測 position/themes)",
        })

    return {
        "ticker": ticker,
        "name": fl["name"],
        "industry_segment": seg,
        "supply_chain_position": pos,
        "core_themes": themes,
        "business_summary": "",
        "twse_industry": fl["twse_industry"],
        "cite_sources": cite,
        "confidence": round(confidence, 2),
        "last_validated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "human_reviewed": False,
        "_position_source": pos_source,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="寫入 stock_profiles.json")
    args = ap.parse_args()

    print("[1/5] 讀取 concept_groups.py...")
    groups = parse_concept_groups()
    groups_idx = build_groups_index(groups)
    unique_tickers = sorted(groups_idx.keys())
    print(f"  共 {len(groups)} 群、{len(unique_tickers)} unique tickers")

    print("[2/5] 載入 finlab snapshot...")
    snapshot = load_finlab_snapshot()
    print(f"  {len(snapshot)} 檔")

    print("[3/5] 載入 group_specs + fixture profiles...")
    specs_path = TAXONOMY_DIR / "group_specs.json"
    specs = json.loads(specs_path.read_text(encoding="utf-8"))
    fixture_path = TAXONOMY_DIR / "tests" / "fixtures" / "test_profiles.json"
    fixtures = json.loads(fixture_path.read_text(encoding="utf-8"))
    fixtures = {k: v for k, v in fixtures.items() if not k.startswith("_")}

    # 人工覆寫層（priority 最高）
    overrides_path = TAXONOMY_DIR / "manual_overrides.json"
    manual_overrides = {}
    if overrides_path.exists():
        manual_overrides = json.loads(overrides_path.read_text(encoding="utf-8"))
        manual_overrides = {k: v for k, v in manual_overrides.items() if not k.startswith("_")}
        print(f"  manual_overrides：{len(manual_overrides)} 檔人工覆寫")

    print(f"[4/5] 為 {len(unique_tickers)} 檔產畫像...")
    profiles = {}
    stats = {"with_seg": 0, "with_pos": 0, "with_themes": 0, "with_coverage": 0, "skipped": 0}
    for i, sym in enumerate(unique_tickers, 1):
        p = build_profile(sym, snapshot, groups_idx, specs, fixtures, manual_overrides)
        profiles[sym] = p
        if p.get("_skip_reason"):
            stats["skipped"] += 1
        else:
            if p["industry_segment"]: stats["with_seg"] += 1
            if p["supply_chain_position"]: stats["with_pos"] += 1
            if p["core_themes"]: stats["with_themes"] += 1
            if any(c.get("type") == "coverage" for c in p.get("cite_sources", [])):
                stats["with_coverage"] += 1
        if i % 200 == 0:
            print(f"  {i} / {len(unique_tickers)}...")

    n = len(unique_tickers) - stats["skipped"]
    print(f"\n[5/5] 完成。覆蓋率：")
    print(f"  industry_segment    : {stats['with_seg']}/{n} = {stats['with_seg']/n*100:.1f}%")
    print(f"  supply_chain_position: {stats['with_pos']}/{n} = {stats['with_pos']/n*100:.1f}%")
    print(f"  core_themes (≥1)    : {stats['with_themes']}/{n} = {stats['with_themes']/n*100:.1f}%")
    print(f"  Coverage hit        : {stats['with_coverage']}/{n} = {stats['with_coverage']/n*100:.1f}%")
    print(f"  finlab not found    : {stats['skipped']}")

    if args.apply:
        out_path = TAXONOMY_DIR / "stock_profiles.json"
        out_path.write_text(json.dumps(profiles, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n✓ 寫入 {out_path}（{len(profiles)} 檔）")
    else:
        print("\n(dry run，加 --apply 才會寫入)")


if __name__ == "__main__":
    main()
