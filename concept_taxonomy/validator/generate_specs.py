"""
Day 4：從 concept_groups.py 批量產出 group_specs.json（剩餘 179 群）。

策略：規則式啟發 + finlab 群眾投票
  1. 群名關鍵字 → 推 allowed_positions / required_themes_any
  2. finlab 統計 → 推 allowed_segments（取出現次數 ≥ 30% 的板塊）
  3. 不命中任何關鍵字 → permissive 預設（segments=多選 / positions=空白名單 / themes=空）

產出：concept_taxonomy/group_specs.json 增量更新
  - 已存在的群保留（不覆蓋手寫精修）
  - 新群 owner_batch="auto_generated_v1" 標記，後續可逐步精修

CLI：
    python -m validator.generate_specs           # dry run，印 diff
    python -m validator.generate_specs --apply   # 寫入 group_specs.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

TAXONOMY_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = TAXONOMY_DIR.parent
sys.path.insert(0, str(TAXONOMY_DIR))

from validator.evidence import infer_segment_from_twse, load_finlab_snapshot  # noqa: E402


# ─────────────────────────────────────────────────────────────────────────────
# 群名關鍵字 → 位階與題材推論表
# ─────────────────────────────────────────────────────────────────────────────
# 順序重要：先匹配的優先（特化詞放前）
NAME_RULES: list[tuple[str, dict]] = [
    # 半導體深度細分
    ("HBM", {"positions": ["IDM_DRAM","OSAT_ADV","TEST_INTF","MAT_WAFER","DISTRIB","ASIC_SVC","FOUNDRY"], "themes_any": ["HBM3E_HBM4"], "segments": ["AI_SEMI"]}),
    ("CoWoS", {"positions": ["FOUNDRY","OSAT_ADV","SUBSTRATE","MAT_WAFER","MAT_CHEM","TEST_INTF","EQUIP","ASIC_SVC"], "themes_any": ["COWOS","COWOP","SOIC_3D","FOPLP"], "segments": ["AI_SEMI","ELEC_COMP"]}),
    ("DDR5", {"positions": ["IDM_DRAM","IC_DESIGN","DISTRIB","TEST_INTF"], "themes_any": ["DDR5_RISE","NICHE_DRAM"], "segments": ["AI_SEMI"]}),
    ("LPDDR", {"positions": ["IDM_DRAM","IC_DESIGN","DISTRIB"], "themes_any": ["DDR5_RISE","NICHE_DRAM"], "segments": ["AI_SEMI"]}),
    ("NAND", {"positions": ["IDM_NAND","IC_DESIGN","DISTRIB","OSAT_TRAD"], "themes_any": ["NAND_TIGHT","aiDAPTIV"], "segments": ["AI_SEMI"]}),
    ("SSD", {"positions": ["IC_DESIGN","DISTRIB","ODM_SYS","BRAND"], "themes_any": ["NAND_TIGHT"], "segments": ["AI_SEMI","COMP_HW"]}),
    ("ABF", {"positions": ["SUBSTRATE"], "themes_any": ["COWOS","GB300_RUBIN"], "segments": ["AI_SEMI","ELEC_COMP"]}),
    ("BT載板", {"positions": ["SUBSTRATE"], "themes_any": [], "segments": ["AI_SEMI","ELEC_COMP"]}),
    ("載板", {"positions": ["SUBSTRATE"], "themes_any": ["COWOS","GB300_RUBIN"], "segments": ["AI_SEMI","ELEC_COMP"]}),
    ("矽光子", {"positions": ["OPTIC_MOD","OPTIC_COMP","IC_DESIGN","FOUNDRY"], "themes_any": ["CPO_PHOTONIC","OPTIC_800G_1.6T","VCSEL"], "segments": ["AI_SEMI","ELEC_COMP","NETCOM"]}),
    ("CPO", {"positions": ["OPTIC_MOD","OPTIC_COMP","IC_DESIGN"], "themes_any": ["CPO_PHOTONIC","OPTIC_800G_1.6T"], "segments": ["AI_SEMI","NETCOM"]}),
    ("光通訊", {"positions": ["OPTIC_MOD","OPTIC_COMP","IC_DESIGN"], "themes_any": ["OPTIC_800G_1.6T","CPO_PHOTONIC","VCSEL"], "segments": ["NETCOM","ELEC_COMP","AI_SEMI"]}),
    ("矽晶圓", {"positions": ["MAT_WAFER"], "themes_any": ["HBM3E_HBM4","DDR5_RISE","N2_2NM","N3_3NM"], "segments": ["AI_SEMI"]}),
    ("ASIC", {"positions": ["ASIC_SVC","IC_DESIGN","IP"], "themes_any": ["ASIC_TRAINIUM","ASIC_TPU","ASIC_MTIA"], "segments": ["AI_SEMI"]}),
    ("矽智財", {"positions": ["IP","ASIC_SVC","IC_DESIGN"], "themes_any": ["ASIC_TRAINIUM","ASIC_TPU","CHIPLET"], "segments": ["AI_SEMI"]}),
    # 工業電腦 必須在 "IP" 之前，避免 "IPC" 誤匹配
    ("工業電腦", {"positions": ["ODM_SYS","BRAND","END_USER","CHASSIS"], "themes_any": ["GB300_RUBIN","ROBOTICS"], "segments": ["COMP_HW","ELEC_COMP"]}),
    ("IPC", {"positions": ["ODM_SYS","BRAND","END_USER","CHASSIS"], "themes_any": [], "segments": ["COMP_HW","ELEC_COMP"]}),
    ("IP", {"positions": ["IP","ASIC_SVC","IC_DESIGN"], "themes_any": ["ASIC_TPU","ASIC_TRAINIUM"], "segments": ["AI_SEMI"]}),
    ("IC設計", {"positions": ["IC_DESIGN","ASIC_SVC","IP"], "themes_any": ["GB300_RUBIN","ASIC_TPU","DDR5_RISE","ADAS"], "segments": ["AI_SEMI"]}),
    ("晶圓代工", {"positions": ["FOUNDRY"], "themes_any": ["N2_2NM","N3_3NM","EUV_RISE","COWOS"], "segments": ["AI_SEMI"]}),
    ("先進製程", {"positions": ["FOUNDRY","EQUIP","MAT_CHEM"], "themes_any": ["N2_2NM","N3_3NM","EUV_RISE"], "segments": ["AI_SEMI"]}),
    ("成熟製程", {"positions": ["FOUNDRY"], "themes_any": [], "segments": ["AI_SEMI"]}),
    ("封測", {"positions": ["OSAT_ADV","OSAT_TRAD","TEST_INTF","TEST_SVC"], "themes_any": ["COWOS","HBM3E_HBM4","AI_GPU_TEST"], "segments": ["AI_SEMI"]}),
    ("先進封裝", {"positions": ["OSAT_ADV","FOUNDRY","TEST_INTF"], "themes_any": ["COWOS","SOIC_3D","FOPLP"], "segments": ["AI_SEMI","ELEC_COMP"]}),
    ("探針卡", {"positions": ["TEST_INTF"], "themes_any": ["AI_GPU_TEST","HBM_TEST","N2_2NM"], "segments": ["AI_SEMI"]}),
    ("測試", {"positions": ["TEST_INTF","TEST_SVC","OSAT_TRAD"], "themes_any": ["AI_GPU_TEST","HBM_TEST"], "segments": ["AI_SEMI"]}),
    ("半導體設備", {"positions": ["EQUIP","MAT_CHEM"], "themes_any": ["N2_2NM","EUV_RISE","COWOS"], "segments": ["AI_SEMI"]}),
    ("半導體耗材", {"positions": ["MAT_CHEM","MAT_WAFER","EQUIP"], "themes_any": ["N2_2NM","COWOS"], "segments": ["AI_SEMI"]}),
    ("特用氣體", {"positions": ["MAT_CHEM"], "themes_any": ["N2_2NM","EUV_RISE"], "segments": ["AI_SEMI"]}),
    ("光阻", {"positions": ["MAT_CHEM"], "themes_any": ["EUV_RISE","N2_2NM"], "segments": ["AI_SEMI"]}),
    # 電子零組件
    ("連接器", {"positions": ["CONNECTOR"], "themes_any": ["GB300_RUBIN","LIQUID_COOL","SERDES_224G","ADAS","HVDC_800V"], "segments": ["ELEC_COMP"]}),
    ("被動元件", {"positions": ["PASSIVE"], "themes_any": ["GB300_RUBIN","DDR5_RISE","ADAS","HVDC_800V"], "segments": ["ELEC_COMP"]}),
    ("MLCC", {"positions": ["PASSIVE"], "themes_any": ["GB300_RUBIN","ADAS","DDR5_RISE"], "segments": ["ELEC_COMP"]}),
    ("PCB", {"positions": ["PCB_HDI","PCB_FPC","SUBSTRATE","MAT_CHEM"], "themes_any": ["GB300_RUBIN","COWOS"], "segments": ["ELEC_COMP"]}),
    ("軟板", {"positions": ["PCB_FPC"], "themes_any": ["GB300_RUBIN","ADAS"], "segments": ["ELEC_COMP"]}),
    ("FPC", {"positions": ["PCB_FPC"], "themes_any": ["GB300_RUBIN","ADAS"], "segments": ["ELEC_COMP"]}),
    ("HDI", {"positions": ["PCB_HDI"], "themes_any": ["GB300_RUBIN","COWOS"], "segments": ["ELEC_COMP"]}),
    ("散熱", {"positions": ["THERMAL"], "themes_any": ["LIQUID_COOL","GB300_RUBIN","ASIC_TRAINIUM"], "segments": ["ELEC_COMP","POWER_GREEN"]}),
    ("液冷", {"positions": ["THERMAL"], "themes_any": ["LIQUID_COOL","GB300_RUBIN"], "segments": ["ELEC_COMP","POWER_GREEN"]}),
    ("機殼", {"positions": ["CHASSIS"], "themes_any": ["GB300_RUBIN"], "segments": ["ELEC_COMP","COMP_HW"]}),
    ("機構件", {"positions": ["CHASSIS"], "themes_any": ["GB300_RUBIN","ADAS"], "segments": ["ELEC_COMP"]}),
    # 系統 / 應用
    ("AI伺服器", {"positions": ["ODM_SYS","BRAND","CHASSIS","THERMAL","POWER_MOD","PCB_HDI","PASSIVE","CONNECTOR","MAT_CHEM","FOUNDRY","OSAT_ADV","END_USER"], "themes_any": ["GB300_RUBIN","ASIC_TRAINIUM","ASIC_TPU","LIQUID_COOL","HVDC_800V"], "segments": ["COMP_HW","ELEC_COMP","POWER_GREEN","AI_SEMI","NETCOM"]}),
    ("伺服器", {"positions": ["ODM_SYS","BRAND","CHASSIS","THERMAL","POWER_MOD","PCB_HDI"], "themes_any": ["GB300_RUBIN","ASIC_TRAINIUM"], "segments": ["COMP_HW","ELEC_COMP"]}),
    ("資料中心", {"positions": ["ODM_SYS","BRAND","CHASSIS","THERMAL","POWER_MOD","OPTIC_MOD"], "themes_any": ["GB300_RUBIN","HVDC_800V","LIQUID_COOL","DATACENTER_POWER"], "segments": ["COMP_HW","ELEC_COMP","POWER_GREEN","NETCOM"]}),
    ("輝達", {"positions": ["FOUNDRY","ODM_SYS","BRAND","SUBSTRATE","TEST_INTF","OSAT_ADV","CONNECTOR","THERMAL","PCB_HDI"], "themes_any": ["GB300_RUBIN","COWOS","ASIC_TPU"], "segments": ["AI_SEMI","COMP_HW","ELEC_COMP"]}),
    ("Google", {"positions": ["ASIC_SVC","FOUNDRY","IC_DESIGN","TEST_INTF","OSAT_ADV","SUBSTRATE","OPTIC_MOD"], "themes_any": ["ASIC_TPU","COWOS","AI_GPU_TEST","CPO_PHOTONIC"], "segments": ["AI_SEMI","ELEC_COMP"]}),
    ("TPU", {"positions": ["ASIC_SVC","FOUNDRY","IC_DESIGN","TEST_INTF","OSAT_ADV","SUBSTRATE"], "themes_any": ["ASIC_TPU","COWOS"], "segments": ["AI_SEMI","ELEC_COMP"]}),
    ("Trainium", {"positions": ["ASIC_SVC","FOUNDRY","IC_DESIGN","TEST_INTF","OSAT_ADV"], "themes_any": ["ASIC_TRAINIUM","COWOS"], "segments": ["AI_SEMI","ELEC_COMP"]}),
    ("ODM", {"positions": ["ODM_SYS"], "themes_any": ["GB300_RUBIN"], "segments": ["COMP_HW","NETCOM"]}),
    ("品牌", {"positions": ["BRAND"], "themes_any": ["GB300_RUBIN"], "segments": ["COMP_HW"]}),
    ("通路", {"positions": ["DISTRIB"], "themes_any": [], "segments": ["AI_SEMI","ELEC_COMP","COMP_HW"]}),
    ("代理", {"positions": ["DISTRIB"], "themes_any": [], "segments": ["AI_SEMI","ELEC_COMP"]}),
    ("筆電", {"positions": ["ODM_SYS","BRAND"], "themes_any": [], "segments": ["COMP_HW"]}),
    ("PC", {"positions": ["ODM_SYS","BRAND"], "themes_any": [], "segments": ["COMP_HW"]}),
    # 電源 / 綠能
    ("電源", {"positions": ["POWER_MOD"], "themes_any": ["HVDC_800V","BBU","GB300_RUBIN"], "segments": ["POWER_GREEN","ELEC_COMP"]}),
    ("BBU", {"positions": ["POWER_MOD"], "themes_any": ["BBU","GB300_RUBIN"], "segments": ["POWER_GREEN"]}),
    ("HVDC", {"positions": ["POWER_MOD"], "themes_any": ["HVDC_800V","DATACENTER_POWER"], "segments": ["POWER_GREEN"]}),
    ("UPS", {"positions": ["POWER_MOD"], "themes_any": ["BBU","HVDC_800V"], "segments": ["POWER_GREEN"]}),
    ("太陽能", {"positions": ["POWER_MOD","MAT_WAFER"], "themes_any": [], "segments": ["POWER_GREEN"]}),
    ("風電", {"positions": ["POWER_MOD","CHASSIS"], "themes_any": [], "segments": ["POWER_GREEN"]}),
    ("儲能", {"positions": ["POWER_MOD","PASSIVE"], "themes_any": ["EV_BATTERY","DATACENTER_POWER"], "segments": ["POWER_GREEN"]}),
    ("綠能", {"positions": ["POWER_MOD"], "themes_any": [], "segments": ["POWER_GREEN"]}),
    ("氫能", {"positions": ["POWER_MOD","MAT_CHEM"], "themes_any": [], "segments": ["POWER_GREEN"]}),
    ("充電樁", {"positions": ["POWER_MOD","CONNECTOR"], "themes_any": ["EV_BATTERY"], "segments": ["POWER_GREEN","EV_AUTO"]}),
    # 車用
    ("車用", {"positions": ["IC_DESIGN","CONNECTOR","PASSIVE","ODM_SYS","CHASSIS"], "themes_any": ["ADAS","EV_BATTERY"], "segments": ["EV_AUTO","ELEC_COMP","AI_SEMI"]}),
    ("電動車", {"positions": ["POWER_MOD","PASSIVE","IC_DESIGN","CHASSIS","CONNECTOR"], "themes_any": ["EV_BATTERY","ADAS"], "segments": ["EV_AUTO","ELEC_COMP","POWER_GREEN"]}),
    ("ADAS", {"positions": ["IC_DESIGN","ASIC_SVC","CONNECTOR"], "themes_any": ["ADAS"], "segments": ["AI_SEMI","EV_AUTO"]}),
    ("電池", {"positions": ["MAT_CHEM","POWER_MOD"], "themes_any": ["EV_BATTERY"], "segments": ["POWER_GREEN","EV_AUTO","MATERIALS"]}),
    ("汽車", {"positions": ["ODM_SYS","BRAND","CHASSIS","CONNECTOR"], "themes_any": ["ADAS","EV_BATTERY"], "segments": ["EV_AUTO","ELEC_COMP"]}),
    # 網通
    ("網通", {"positions": ["ODM_SYS","BRAND","IC_DESIGN","OPTIC_MOD"], "themes_any": ["WIFI7","5G_6G","SERDES_224G"], "segments": ["NETCOM","AI_SEMI"]}),
    ("交換器", {"positions": ["ODM_SYS","IC_DESIGN","OPTIC_MOD"], "themes_any": ["SERDES_224G","OPTIC_800G_1.6T"], "segments": ["NETCOM"]}),
    ("Wi-Fi", {"positions": ["IC_DESIGN","ODM_SYS"], "themes_any": ["WIFI7"], "segments": ["NETCOM","AI_SEMI"]}),
    ("5G", {"positions": ["IC_DESIGN","ODM_SYS","CONNECTOR"], "themes_any": ["5G_6G"], "segments": ["NETCOM","AI_SEMI"]}),
    ("6G", {"positions": ["IC_DESIGN","ODM_SYS"], "themes_any": ["5G_6G"], "segments": ["NETCOM","AI_SEMI"]}),
    ("低軌衛星", {"positions": ["IC_DESIGN","ODM_SYS","OPTIC_MOD"], "themes_any": ["LEO_SAT","MILITARY_SAT"], "segments": ["NETCOM","DEFENSE"]}),
    ("衛星", {"positions": ["IC_DESIGN","ODM_SYS","OPTIC_MOD"], "themes_any": ["LEO_SAT","MILITARY_SAT"], "segments": ["NETCOM","DEFENSE"]}),
    # 軍工
    ("軍工", {"positions": ["ODM_SYS","BRAND","CHASSIS","IC_DESIGN"], "themes_any": ["DEFENSE_DRONE","MILITARY_SAT"], "segments": ["DEFENSE"]}),
    ("國防", {"positions": ["ODM_SYS","BRAND","CHASSIS"], "themes_any": ["DEFENSE_DRONE","MILITARY_SAT"], "segments": ["DEFENSE"]}),
    ("無人機", {"positions": ["ODM_SYS","IC_DESIGN","CHASSIS"], "themes_any": ["DEFENSE_DRONE"], "segments": ["DEFENSE","AI_SEMI"]}),
    # 生技
    ("CDMO", {"positions": ["END_USER"], "themes_any": ["CDMO_BIO"], "segments": ["MED_BIO"]}),
    ("新藥", {"positions": ["END_USER"], "themes_any": ["MED_GLP1","CDMO_BIO"], "segments": ["MED_BIO"]}),
    ("生技", {"positions": ["END_USER"], "themes_any": ["CDMO_BIO","MED_GLP1"], "segments": ["MED_BIO"]}),
    ("智慧醫療", {"positions": ["END_USER","SVC_SAAS"], "themes_any": ["CDMO_BIO"], "segments": ["MED_BIO","SOFTWARE"]}),
    ("醫材", {"positions": ["END_USER"], "themes_any": [], "segments": ["MED_BIO"]}),
    ("GLP", {"positions": ["END_USER","MAT_CHEM"], "themes_any": ["GLP1_OBESITY","MED_GLP1"], "segments": ["MED_BIO"]}),
    ("減重", {"positions": ["END_USER"], "themes_any": ["GLP1_OBESITY","MED_GLP1"], "segments": ["MED_BIO"]}),
    # 機器人
    ("機器人", {"positions": ["IC_DESIGN","ASIC_SVC","ODM_SYS","CHASSIS","CONNECTOR"], "themes_any": ["ROBOTICS"], "segments": ["AI_SEMI","ELEC_COMP","COMP_HW"]}),
    # 量子
    ("量子", {"positions": ["IC_DESIGN","FOUNDRY","ASIC_SVC"], "themes_any": ["QUANTUM"], "segments": ["AI_SEMI"]}),
    # 其他熱門
    ("Apple", {"positions": ["ODM_SYS","IC_DESIGN","SUBSTRATE","CONNECTOR","PASSIVE","PCB_HDI","PCB_FPC","CHASSIS"], "themes_any": [], "segments": ["AI_SEMI","ELEC_COMP","COMP_HW"]}),
    ("蘋果", {"positions": ["ODM_SYS","IC_DESIGN","SUBSTRATE","CONNECTOR","PASSIVE","PCB_HDI","PCB_FPC","CHASSIS"], "themes_any": [], "segments": ["AI_SEMI","ELEC_COMP","COMP_HW"]}),
    ("VR", {"positions": ["ODM_SYS","IC_DESIGN","BRAND"], "themes_any": [], "segments": ["AI_SEMI","COMP_HW","ELEC_COMP"]}),
    ("AR", {"positions": ["ODM_SYS","IC_DESIGN","BRAND"], "themes_any": [], "segments": ["AI_SEMI","COMP_HW","ELEC_COMP"]}),
    ("元宇宙", {"positions": ["ODM_SYS","IC_DESIGN","BRAND","SVC_SAAS"], "themes_any": [], "segments": ["AI_SEMI","COMP_HW","SOFTWARE"]}),
    # 軟體
    ("軟體", {"positions": ["SVC_SAAS"], "themes_any": [], "segments": ["SOFTWARE"]}),
    ("資安", {"positions": ["SVC_SAAS"], "themes_any": [], "segments": ["SOFTWARE"]}),
    ("遊戲", {"positions": ["SVC_SAAS"], "themes_any": [], "segments": ["SOFTWARE"]}),
    ("電商", {"positions": ["SVC_SAAS","BRAND"], "themes_any": [], "segments": ["SOFTWARE","CONSUMER"]}),
    # 消費
    ("食品", {"positions": ["BRAND","END_USER"], "themes_any": [], "segments": ["CONSUMER"]}),
    ("觀光", {"positions": ["BRAND","END_USER"], "themes_any": [], "segments": ["CONSUMER"]}),
    ("零售", {"positions": ["BRAND","END_USER"], "themes_any": [], "segments": ["CONSUMER"]}),
    ("寵物", {"positions": ["BRAND","END_USER"], "themes_any": ["PETS_ECONOMY"], "segments": ["CONSUMER","MED_BIO"]}),
    # 原物料
    ("鋼鐵", {"positions": ["MAT_CHEM"], "themes_any": [], "segments": ["MATERIALS"]}),
    ("水泥", {"positions": ["MAT_CHEM"], "themes_any": [], "segments": ["MATERIALS"]}),
    ("塑化", {"positions": ["MAT_CHEM"], "themes_any": [], "segments": ["MATERIALS"]}),
    ("化工", {"positions": ["MAT_CHEM"], "themes_any": [], "segments": ["MATERIALS"]}),
    ("橡膠", {"positions": ["MAT_CHEM"], "themes_any": [], "segments": ["MATERIALS"]}),
    ("輪胎", {"positions": ["MAT_CHEM"], "themes_any": [], "segments": ["MATERIALS"]}),
    ("造紙", {"positions": ["MAT_CHEM"], "themes_any": [], "segments": ["MATERIALS"]}),
    ("玻璃", {"positions": ["MAT_CHEM"], "themes_any": [], "segments": ["MATERIALS"]}),
    ("紡織", {"positions": ["MAT_CHEM"], "themes_any": [], "segments": ["MATERIALS","CONSUMER"]}),
    # 物流
    ("航運", {"positions": ["END_USER"], "themes_any": [], "segments": ["LOGISTICS"]}),
    ("貨櫃", {"positions": ["END_USER"], "themes_any": [], "segments": ["LOGISTICS"]}),
    ("航空", {"positions": ["END_USER"], "themes_any": [], "segments": ["LOGISTICS"]}),
    # 金融
    ("金融", {"positions": ["SVC_SAAS"], "themes_any": [], "segments": ["FIN"]}),
    ("銀行", {"positions": ["SVC_SAAS"], "themes_any": [], "segments": ["FIN"]}),
    ("保險", {"positions": ["SVC_SAAS"], "themes_any": [], "segments": ["FIN"]}),
    ("證券", {"positions": ["SVC_SAAS"], "themes_any": [], "segments": ["FIN"]}),
    # 記憶體（兜底）
    ("記憶體", {"positions": ["IDM_DRAM","IC_DESIGN","DISTRIB"], "themes_any": ["DDR5_RISE","NICHE_DRAM","HBM3E_HBM4"], "segments": ["AI_SEMI"]}),
]

DEFAULT_SEGMENTS = ["AI_SEMI", "ELEC_COMP", "COMP_HW", "NETCOM", "POWER_GREEN", "EV_AUTO",
                    "DEFENSE", "MED_BIO", "FIN", "CONSUMER", "MATERIALS", "LOGISTICS", "SOFTWARE"]


def parse_concept_groups() -> dict[str, list[str]]:
    """讀 concept_groups.py，回 {group_name: [tickers]}。"""
    src = (PROJECT_ROOT / "concept_groups.py").read_text(encoding="utf-8")
    pattern = re.compile(r'"([^"]+?)"\s*:\s*\[(.*?)\]', re.DOTALL)
    result: dict[str, list[str]] = {}
    for m in pattern.finditer(src):
        name = m.group(1)
        if name in {"_meta",} or len(name) < 2:
            continue
        tickers = re.findall(r'"(\d{4,5})"', m.group(2))
        if tickers:
            result[name] = tickers
    return result


def vote_segments(tickers: list[str], snapshot) -> list[str]:
    """投票：成分股 finlab 產業 → segment，取出現比例 ≥ 25% 的板塊。"""
    counts: Counter = Counter()
    for sym in tickers:
        row = snapshot[snapshot["symbol"] == sym]
        if row.empty:
            continue
        seg = infer_segment_from_twse(row.iloc[0]["產業類別"])
        if seg:
            counts[seg] += 1
    if not counts:
        return []
    total = sum(counts.values())
    threshold = max(1, int(total * 0.25))
    return [seg for seg, c in counts.most_common() if c >= threshold]


def match_name_rule(group_name: str) -> dict | None:
    for keyword, rule in NAME_RULES:
        if keyword.lower() in group_name.lower():
            return rule
    return None


def generate_spec(group_name: str, tickers: list[str], snapshot) -> dict:
    """產出單一群的啟發式 spec。"""
    rule = match_name_rule(group_name)
    voted_segments = vote_segments(tickers, snapshot)

    if rule:
        positions = rule["positions"]
        themes_any = rule["themes_any"]
        # segments 取規則 ∪ 投票結果（避免漏掉跨 segment 成分）
        segments = list(set(rule["segments"]) | set(voted_segments)) or rule["segments"]
    else:
        positions = []  # 空白名單 = 所有位階都允許（permissive）
        themes_any = []
        segments = voted_segments or DEFAULT_SEGMENTS

    return {
        "allowed_segments": segments,
        "allowed_positions": positions,
        "required_themes_any": themes_any,
        "required_themes_strong": themes_any[:2] if len(themes_any) >= 2 else [],
        "forbidden_positions": [],
        "forbidden_themes": [],
        "downstream_demote": [],
        "core_keywords": [group_name.split("/")[0].split(" ")[0]],
        "exclusion_keywords": [],
        "deprecated": False,
        "merge_into": None,
        "owner_batch": "auto_generated_v1",
        "rationale": f"自動生成（規則匹配={'是' if rule else '否'}；finlab 投票 segments={voted_segments}）",
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="寫入 group_specs.json")
    ap.add_argument("--no-finlab", action="store_true", help="跳過 finlab snapshot（純規則）")
    args = ap.parse_args()

    specs_path = TAXONOMY_DIR / "group_specs.json"
    existing = json.loads(specs_path.read_text(encoding="utf-8"))

    groups = parse_concept_groups()
    print(f"concept_groups.py 共 {len(groups)} 群；group_specs.json 已有 {len([k for k in existing if not k.startswith('_')])} 群")

    snapshot = None
    if not args.no_finlab:
        try:
            snapshot = load_finlab_snapshot()
            print(f"finlab snapshot 載入：{len(snapshot)} 檔")
        except Exception as e:
            print(f"⚠ finlab 載入失敗，fallback 純規則：{e}")
            snapshot = None

    new_specs = {}
    for name, tickers in groups.items():
        if name in existing:
            continue
        if snapshot is not None:
            spec = generate_spec(name, tickers, snapshot)
        else:
            # 無 finlab：只用規則
            rule = match_name_rule(name)
            spec = {
                "allowed_segments": rule["segments"] if rule else DEFAULT_SEGMENTS,
                "allowed_positions": rule["positions"] if rule else [],
                "required_themes_any": rule["themes_any"] if rule else [],
                "required_themes_strong": rule["themes_any"][:2] if rule and len(rule["themes_any"]) >= 2 else [],
                "forbidden_positions": [],
                "forbidden_themes": [],
                "downstream_demote": [],
                "core_keywords": [name.split("/")[0].split(" ")[0]],
                "exclusion_keywords": [],
                "deprecated": False,
                "merge_into": None,
                "owner_batch": "auto_generated_v1_rule_only",
                "rationale": f"自動生成（規則匹配={'是' if rule else '否'}，無 finlab 投票）",
            }
        new_specs[name] = spec

    matched = sum(1 for s in new_specs.values() if s["allowed_positions"])
    permissive = len(new_specs) - matched
    print(f"\n新增 {len(new_specs)} 群：規則匹配 {matched}，permissive {permissive}")

    if args.apply:
        existing.update(new_specs)
        # _meta 更新
        existing["_meta"]["coverage"] = f"{len([k for k in existing if not k.startswith('_')])} / {len(groups)}"
        existing["_meta"]["last_updated"] = datetime_now()
        specs_path.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"✓ 寫回 {specs_path}")
    else:
        print("\n(dry run，加 --apply 才會寫入)")


def datetime_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


if __name__ == "__main__":
    main()
