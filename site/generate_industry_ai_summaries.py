"""補齊每個有效族群的產業分析摘要。

用途：
- 保留既有手寫/深度 AI 摘要。
- 對新增的產業細分族群，依大族群、細產業與代表成分股生成分析文字。
- 輸出 site/.ai_summaries.json，供 topic_detail.html 顯示「產業分析」區塊。
"""

from __future__ import annotations

import argparse
import ast
import json
import re
from dataclasses import dataclass
from pathlib import Path

from industry_meta import get_meta


ROOT = Path(__file__).resolve().parents[1]
SITE_DIR = ROOT / "site"
CONCEPT_GROUPS_PATH = ROOT / "concept_groups.py"
SUMMARY_PATH = SITE_DIR / ".ai_summaries.json"
STOCK_NAME_OVERRIDES_PATH = SITE_DIR / "stock_name_overrides.json"


@dataclass(frozen=True)
class Profile:
    focus: str
    chain: str
    cycle: str
    drivers: tuple[str, str, str]
    risks: tuple[str, str]


DEFAULT_PROFILE = Profile(
    focus="細分市場需求、產品組合與供應鏈位置",
    chain="連結上游原料/零組件、製造加工與終端客戶需求",
    cycle="終端需求、庫存水位、價格與匯率變化",
    drivers=("需求回溫與庫存去化", "產品組合升級", "代表廠商接單與產能利用率改善"),
    risks=("終端需求不如預期", "價格競爭或原料成本波動"),
)


PROFILE_RULES: tuple[tuple[tuple[str, ...], Profile], ...] = (
    (
        ("化學纖維", "化纖原料", "聚酯", "尼龍", "加工絲", "粘膠", "亞克力"),
        Profile(
            focus="PTA、EG、CPL、AN 等原料到聚酯、尼龍、人纖與加工絲的價差與稼動率",
            chain="承接石化原料，供應紡紗、織布、成衣、工業用布、機能服飾與包材應用",
            cycle="油價與原料價差、品牌服飾庫存、亞洲同業供給、台幣匯率與出口訂單",
            drivers=("品牌庫存回補與機能布需求", "原料價差改善", "環保回收纖維與高機能材料滲透"),
            risks=("中國與東南亞低價產能競爭", "油價急漲壓縮加工利差"),
        ),
    ),
    (
        ("紡紗", "織布", "成衣", "紡織", "不織布", "工業紡織品"),
        Profile(
            focus="紗線、布料、染整、成衣代工與機能布料的訂單能見度",
            chain="由纖維原料延伸至紡紗、織布、染整、品牌服飾與戶外運動供應鏈",
            cycle="品牌客戶庫存、運動休閒需求、匯率、棉花/化纖原料價格與產能移轉",
            drivers=("運動戶外與機能服飾需求", "品牌客戶補庫存", "高附加價值布料滲透"),
            risks=("品牌砍單或庫存調整", "匯率與原料成本波動"),
        ),
    ),
    (
        ("食品", "乳製品", "飲料", "速食麵", "罐頭", "肉品", "水產品", "保健食品", "調味"),
        Profile(
            focus="民生消費、通路鋪貨、品牌力與原料成本控管",
            chain="涵蓋農畜水產原料、加工製造、冷鏈物流、零售通路與外食需求",
            cycle="原物料價格、節慶旺季、通路促銷、外食景氣與消費信心",
            drivers=("民生剛性需求", "新品與通路滲透", "原料成本回落帶動毛利修復"),
            risks=("原料價格或匯率上升", "食品安全與通路促銷壓力"),
        ),
    ),
    (
        ("水泥", "混凝土", "建材", "營造", "地產", "玻璃", "陶瓷"),
        Profile(
            focus="工程需求、房建循環、公共建設與低碳建材轉型",
            chain="連結石灰石/砂石原料、水泥熟料、預拌混凝土、建材加工與營建工程",
            cycle="公共工程進度、房市景氣、能源成本、碳費與區域供需",
            drivers=("公共建設與都市更新", "低碳製程與節能設備升級", "價格紀律與區域供需改善"),
            risks=("房市量縮拖累需求", "煤電成本與碳費壓力"),
        ),
    ),
    (
        ("塑化", "PVC", "PE", "PP", "ABS", "PS", "EVA", "PTA", "EG", "DOP", "芳香烴", "烯烴", "橡膠"),
        Profile(
            focus="石化原料價差、下游塑膠加工需求與亞洲供需變化",
            chain="由油氣裂解與中間體延伸至塑膠、橡膠、包材、電子材料、汽車與民生用品",
            cycle="油價、乙烯/丙烯/芳香烴價差、中國開工率、下游庫存與出口訂單",
            drivers=("原料價差修復", "下游包材與汽車/電子需求", "高值化材料與循環材料滲透"),
            risks=("中國新增產能壓力", "油價大幅波動造成庫存損失"),
        ),
    ),
    (
        ("化學工業", "肥料", "農藥", "染料", "塗料", "顏料", "接著劑", "清潔用品", "特用化學", "電子化學"),
        Profile(
            focus="基礎化工原料、農用資材、特用化學品與下游客戶需求",
            chain="由化工原料延伸至肥料、農藥、染料、塗料、電子化學品與民生清潔用品",
            cycle="原料報價、農業與工業需求、環保法規、匯率與客戶庫存",
            drivers=("農業與工業需求回溫", "特用化學品高值化", "原料價差改善"),
            risks=("原料成本與能源價格波動", "中國同業低價競爭與環保成本"),
        ),
    ),
    (
        ("IC", "半導體", "晶圓", "封裝", "測試", "ASIC", "MCU", "記憶體", "矽晶圓", "光罩"),
        Profile(
            focus="製程節點、設計導入、晶圓/封測產能利用率與終端電子需求",
            chain="橫跨 IC 設計、晶圓製造、材料設備、封裝測試與系統客戶",
            cycle="消費電子庫存、AI/車用/工控需求、先進製程投片與資本支出",
            drivers=("AI、車用與邊緣運算帶動晶片升級", "庫存去化後補單", "先進製程與高階封裝滲透"),
            risks=("終端需求轉弱", "價格競爭與客戶拉貨遞延"),
        ),
    ),
    (
        ("PCB", "HDI", "銅箔", "基板", "ABF", "印刷電路板"),
        Profile(
            focus="高階板材、載板、低損耗材料與伺服器/車用電子需求",
            chain="由銅箔、樹脂、玻纖布延伸至 CCL、PCB、載板與系統組裝",
            cycle="AI 伺服器拉貨、手機/PC 新機週期、車用電子滲透與材料報價",
            drivers=("AI 伺服器與高速傳輸升級", "高階 HDI/ABF 供需改善", "車用與低軌衛星板材需求"),
            risks=("終端產品遞延拉貨", "銅價與材料成本上升"),
        ),
    ),
    (
        ("連接器", "被動元件", "電源", "電池", "散熱", "電子零件", "電線電纜", "傳輸介面"),
        Profile(
            focus="規格升級、客戶認證、材料成本與終端應用出貨量",
            chain="供應伺服器、車用、工控、消費電子與通訊設備所需關鍵零組件",
            cycle="終端出貨、庫存水位、銅/鋁/稀土等材料價格與新平台導入",
            drivers=("AI 伺服器與車用電子規格升級", "高頻高速與高功率需求", "客戶認證帶來訂單黏著度"),
            risks=("客戶庫存調整", "材料成本與價格競爭壓力"),
        ),
    ),
    (
        ("電腦", "伺服器", "筆記型", "主機板", "工業電腦", "網通", "雲端", "資料中心"),
        Profile(
            focus="平台換機、伺服器/網通設備出貨、客戶結構與系統整合能力",
            chain="整合主板、機殼、散熱、電源、網通與整機組裝，供應品牌與雲端服務客戶",
            cycle="企業 IT 支出、AI/雲端資本支出、PC 換機潮與通路庫存",
            drivers=("AI 與雲端基礎建設升級", "企業換機與工控需求", "高階系統整合毛利改善"),
            risks=("CSP 資本支出放緩", "平台轉換期庫存調整"),
        ),
    ),
    (
        ("光通訊", "光學", "LED", "面板", "顯示器", "相機", "鏡頭", "OLED", "MicroLED"),
        Profile(
            focus="光學規格升級、資料中心傳輸、顯示技術替代與終端拉貨節奏",
            chain="涵蓋光學材料、元件、模組、顯示面板、感測與終端裝置",
            cycle="消費電子新機、資料中心升級、面板供需、價格與稼動率",
            drivers=("高速光通訊與 AI 資料中心需求", "車用/手機光學規格提升", "新型顯示技術滲透"),
            risks=("面板與 LED 供過於求", "終端新機銷售不如預期"),
        ),
    ),
    (
        ("汽車", "車用", "電動車", "自行車", "機車", "輪胎"),
        Profile(
            focus="車用零組件、電動化、輕量化與售後市場需求",
            chain="供應整車廠、Tier 1、電池/電控、內裝、底盤與售後維修市場",
            cycle="全球車市銷量、EV 滲透率、客戶平台導入、原物料與匯率",
            drivers=("電動車與智慧車電子含量提升", "客戶平台量產", "售後市場與外銷訂單回溫"),
            risks=("車市需求放緩", "價格競爭與客戶年降壓力"),
        ),
    ),
    (
        ("機械", "工具機", "機器人", "設備", "工業", "自動化", "航太", "無人機"),
        Profile(
            focus="資本支出、設備訂單、客戶投資週期與自動化滲透",
            chain="服務半導體、電子、汽車、航太、金屬加工與一般製造業設備需求",
            cycle="全球製造業 PMI、匯率、客戶擴產計畫與交機認列",
            drivers=("自動化與智慧製造升級", "半導體/車用/航太設備需求", "外銷訂單與交機遞延回補"),
            risks=("企業資本支出縮手", "匯率與中國同業價格競爭"),
        ),
    ),
    (
        ("醫", "藥", "生技", "檢驗", "醫材", "細胞治療", "新藥"),
        Profile(
            focus="產品證照、臨床進度、通路放量與醫療需求剛性",
            chain="涵蓋研發、原料藥、製劑、醫材、檢測服務、通路與終端醫療院所",
            cycle="臨床/法規時程、健保與自費需求、海外授權、通路庫存",
            drivers=("高齡化與慢性病需求", "新產品取證與通路放量", "海外授權或代工訂單"),
            risks=("臨床或法規進度延遲", "價格管制與研發費用上升"),
        ),
    ),
    (
        ("金融", "銀行", "保險", "證券", "租賃", "投信", "金控"),
        Profile(
            focus="利差、資產品質、手續費收入與資本市場活絡度",
            chain="服務存放款、保險、投資、財富管理、證券交易與企業融資需求",
            cycle="利率循環、股債市行情、信用風險與監理資本要求",
            drivers=("利差維持與財富管理成長", "資本市場成交量回升", "股利政策與資產品質改善"),
            risks=("降息壓縮利差", "信用成本上升或金融市場波動"),
        ),
    ),
    (
        ("航運", "運輸", "物流", "空運", "貨櫃", "散裝", "倉儲"),
        Profile(
            focus="運價、艙位供需、油價與全球貿易流量",
            chain="涵蓋海運、空運、貨代、倉儲、物流配送與港口服務",
            cycle="全球貿易、旺季出貨、運力供給、燃油成本與地緣航線變化",
            drivers=("旺季貨量與補庫存", "航線供需改善", "電商與冷鏈物流需求"),
            risks=("運力過剩壓低運價", "油價與地緣風險推升成本"),
        ),
    ),
    (
        ("休閒", "觀光", "餐飲", "旅遊", "住宿", "運動", "娛樂"),
        Profile(
            focus="人流、展店、客單價、旅遊需求與品牌經營效率",
            chain="連結餐飲、飯店、旅行社、運動用品、休閒娛樂與線下消費場景",
            cycle="假期旺季、入出境旅客、消費信心、人事租金成本",
            drivers=("旅遊與線下消費復甦", "展店與品牌升級", "會員經營帶動回購"),
            risks=("消費信心轉弱", "人事租金與食材成本上升"),
        ),
    ),
    (
        ("服務業", "保全", "殯葬", "婚宴", "教育", "人力資源", "商業服務", "消費者服務", "清潔服務", "顧問"),
        Profile(
            focus="合約續約率、客戶黏著度、人力配置效率、通路觸點與服務單價",
            chain="涵蓋線上/線下通路、會員與企業客戶、現場服務交付、客服維運與品牌經營",
            cycle="消費信心、企業外包需求、薪資與租金成本、展店速度與合約調價能力",
            drivers=("企業外包與專業服務需求", "會員經營與通路滲透", "人力排班與數位化帶動效率提升"),
            risks=("人力成本上升壓縮毛利", "景氣轉弱使客戶延後消費或外包預算"),
        ),
    ),
    (
        ("太陽能", "綠能", "環保", "水資源", "電力", "儲能", "風力", "充電"),
        Profile(
            focus="政策補助、電力需求、案場建置、設備稼動率與能源價格",
            chain="涵蓋發電設備、工程建置、儲能、電網、環保處理與能源服務",
            cycle="政策時程、案場併網、利率、原物料價格與電價制度",
            drivers=("能源轉型與電網升級", "儲能與充電基礎建設", "企業綠電與碳管理需求"),
            risks=("政策或併網進度延遲", "設備價格下跌與專案毛利波動"),
        ),
    ),
    (
        ("鋼", "金屬", "銅", "鋁", "不鏽鋼", "非鐵", "螺絲", "線材"),
        Profile(
            focus="金屬報價、加工利差、外銷訂單與下游製造需求",
            chain="由礦石/廢料、冶煉、軋延、加工製品延伸至建築、汽車、機械與電子應用",
            cycle="全球製造業需求、中國供需、原料報價、匯率與庫存評價",
            drivers=("製造業補庫存", "基建與能源設備需求", "高值化金屬加工產品滲透"),
            risks=("金屬價格下跌造成庫存損失", "需求疲弱與低價進口競爭"),
        ),
    ),
)


def load_concept_groups() -> dict[str, list[str]]:
    module = ast.parse(CONCEPT_GROUPS_PATH.read_text(encoding="utf-8"))
    for node in module.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "CONCEPT_GROUPS":
                return ast.literal_eval(node.value)
    raise ValueError("找不到 CONCEPT_GROUPS")


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def parse_member_comments() -> dict[str, dict[str, str]]:
    group_re = re.compile(r'^\s{4}"(?P<group>.+)": \[\s*$')
    member_re = re.compile(r'^\s{8}"(?P<code>[^"]+)",\s*(?:#\s*(?P<name>.*))?$')
    comments: dict[str, dict[str, str]] = {}
    current_group: str | None = None
    for line in CONCEPT_GROUPS_PATH.read_text(encoding="utf-8").splitlines():
        group_match = group_re.match(line)
        if group_match:
            current_group = group_match.group("group")
            comments.setdefault(current_group, {})
            continue
        if current_group is None:
            continue
        if line.startswith("    ],"):
            current_group = None
            continue
        member_match = member_re.match(line)
        if member_match:
            comments.setdefault(current_group, {})[member_match.group("code")] = (
                member_match.group("name") or ""
            ).strip()
    return comments


def infer_profile(group: str, category: str) -> Profile:
    text = f"{group} {category}"
    for keywords, profile in PROFILE_RULES:
        if any(keyword in text for keyword in keywords):
            return profile
    return DEFAULT_PROFILE


def stock_label(code: str, group: str, comments: dict[str, dict[str, str]], overrides: dict[str, str]) -> str:
    name = overrides.get(code) or comments.get(group, {}).get(code) or ""
    name = name.strip()
    return f"{code} {name}" if name else code


def lead_text(leaders: list[str]) -> str:
    if not leaders:
        return "代表公司"
    return "、".join(leaders)


def compact_text(text: str, limit: int = 22) -> str:
    text = " ".join(str(text).split())
    if len(text) <= limit:
        return text
    for sep in ("、", "，", "與", "及"):
        if sep in text:
            first = text.split(sep, 1)[0].strip()
            if first:
                return first[:limit]
    return text[:limit]


def make_summary(
    group: str,
    members: list[str],
    comments: dict[str, dict[str, str]],
    overrides: dict[str, str],
) -> dict[str, object]:
    meta = get_meta(group)
    category = meta.get("category") or "產業"
    profile = infer_profile(group, category)
    leaders = [stock_label(code, group, comments, overrides) for code in members[:3]]
    leaders_joined = lead_text(leaders)
    count = len(members)
    chain_intro = profile.chain
    if not chain_intro.startswith(("連結", "涵蓋", "橫跨", "由", "承接", "供應", "服務", "整合")):
        chain_intro = f"連結{chain_intro}"
    leader_card = lead_text(leaders[:2])

    hero_desc = (
        f"{group}聚焦{profile.focus}，{chain_intro}。"
        f"目前收錄 {count} 檔成分股，代表公司包括 {leaders_joined}。"
    )

    analysis = (
        f"{group}位於{category}產業鏈中的重要細分領域，核心觀察在於{profile.focus}。"
        f"產業鏈位置上，{profile.chain}，因此營收與毛利通常會同時受到{profile.cycle}影響。"
        f"目前台股成分股以{leaders_joined}等公司為代表，投資研究可從訂單能見度、產品組合、產能利用率與報價變化交叉驗證。"
        f"中期成長動能主要來自{profile.drivers[0]}、{profile.drivers[1]}與{profile.drivers[2]}；"
        f"需要留意{profile.risks[0]}，以及{profile.risks[1]}對評價與獲利的壓力。"
    )

    return {
        "hero_desc": hero_desc,
        "analysis": analysis,
        "key_drivers": list(profile.drivers),
        "risks": list(profile.risks),
        "leaders": leaders,
        "indicators": [
            {"label": "觀察重點", "value": compact_text(profile.focus)},
            {"label": "成長動能", "value": compact_text(profile.drivers[0])},
            {"label": "風險變數", "value": compact_text(profile.risks[0])},
            {"label": "代表公司", "value": leader_card},
        ],
    }


def normalize_existing_summary(summary: dict, group: str, members: list[str], comments, overrides) -> dict:
    if not isinstance(summary, dict):
        return make_summary(group, members, comments, overrides)
    merged = dict(summary)
    fallback = None
    if not merged.get("hero_desc"):
        meta = get_meta(group)
        merged["hero_desc"] = meta.get("desc") or make_summary(group, members, comments, overrides)["hero_desc"]
    for key in ("analysis", "key_drivers", "risks", "leaders", "indicators"):
        if not merged.get(key):
            fallback = fallback or make_summary(group, members, comments, overrides)
            merged[key] = fallback[key]
    if get_meta(group).get("actual_count") is not None:
        fallback = fallback or make_summary(group, members, comments, overrides)
        for key in ("hero_desc", "analysis", "key_drivers", "risks", "leaders", "indicators"):
            merged[key] = fallback[key]
        merged["indicators"] = fallback["indicators"]
    return merged


def main() -> int:
    parser = argparse.ArgumentParser(description="補齊 site/.ai_summaries.json")
    parser.add_argument("--write", action="store_true", help="實際寫入檔案")
    parser.add_argument("--json", action="store_true", help="輸出 JSON 摘要")
    args = parser.parse_args()

    groups = load_concept_groups()
    existing = load_json(SUMMARY_PATH)
    overrides = load_json(STOCK_NAME_OVERRIDES_PATH)
    comments = parse_member_comments()

    output: dict[str, dict] = {}
    generated = 0
    preserved = 0
    for group, members in groups.items():
        if group in existing:
            output[group] = normalize_existing_summary(existing[group], group, members, comments, overrides)
            preserved += 1
        else:
            output[group] = make_summary(group, members, comments, overrides)
            generated += 1

    if args.write:
        SUMMARY_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    report = {
        "mode": "write" if args.write else "dry-run",
        "groups": len(groups),
        "preserved": preserved,
        "generated": generated,
        "output": str(SUMMARY_PATH.relative_to(ROOT)),
    }
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"模式: {report['mode']}")
        print(f"族群: {report['groups']}")
        print(f"保留既有摘要: {report['preserved']}")
        print(f"新產生摘要: {report['generated']}")
        print(f"輸出: {report['output']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
