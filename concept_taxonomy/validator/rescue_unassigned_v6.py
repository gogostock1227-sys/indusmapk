"""v6 補族群驗證器。

這一層只處理 v5 嚴格驗證後仍未上架或過度歸零的股票：

1. 熱門概念股先用網路成分股清單做候選，再用 My-TW-Coverage/stock_profiles 驗證本業。
2. 產業型族群用 TWSE/FinLab 產業別、My-TW-Coverage 產業資料夾與報告關鍵段落交叉驗證。
3. ABF、Google TPU、CPU、石英元件、CPO/矽光子、記憶體等高風險題材維持鎖定，不自動補人。
4. 每筆新增都輸出 evidence_trail，低信心者寫入 still_unassigned.csv，不硬塞。
"""
from __future__ import annotations

import argparse
import csv
import importlib
import json
import re
import shutil
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .evidence import build_primary_coverage_text, find_coverage_file, read_coverage_sections

ROOT = Path(__file__).resolve().parents[2]
TAXONOMY_DIR = ROOT / "concept_taxonomy"
VALIDATION_RUNS_DIR = TAXONOMY_DIR / "validation_runs"
CONCEPT_GROUPS_PATH = ROOT / "concept_groups.py"
PROFILES_PATH = TAXONOMY_DIR / "stock_profiles.json"
REPORTS_DIR = ROOT / "My-TW-Coverage" / "Pilot_Reports"
MYTW_SCRIPTS_DIR = ROOT / "My-TW-Coverage" / "scripts"


LOCKED_AUTO_ADD_GROUPS = {
    "ABF載板",
    "Google TPU",
    "CPU 概念股",
    "石英元件",
    "光通訊/CPO",
    "矽光子",
    "記憶體",
}

# 使用者指定 ABF 僅能有三檔。這裡再鎖一次，避免 rescue 誤補設備或材料商。
HARD_EXACT_MEMBERS = {
    "ABF載板": {"3037", "8046", "3189"},
}

MATURE_FOUNDRY_EXACT = {
    "2303",  # 聯電
    "2342",  # 茂矽
    "3707",  # 漢磊
    "5347",  # 世界
    "6770",  # 力積電
}

EXCLUDE_BY_GROUP = {
    "電源供應器/BBU": {"6123"},  # 報告混入順達/上奇錯置，v6 不自動上架。
}


WEB_SEED_SOURCES = {
    "電源供應器/BBU": {
        "source": "web:BBU概念股清單",
        "url": "https://statementdog.com/tags/38068",
        "tickers": [
            "2308", "2301", "6781", "3211", "5309", "3338", "4931",
            "3597", "5328", "8171", "3625", "8038", "6121", "3323",
            "2457", "6282", "6412",
        ],
    },
    "重電": {
        "source": "web:重電概念股清單",
        "url": "https://statementdog.com/tags/20553",
        "tickers": ["1519", "1503", "1513", "1514", "1612", "1605", "1609", "1618"],
    },
    "資安": {
        "source": "web:資安概念股清單",
        "url": "https://statementdog.com/tags/572",
        "tickers": ["2471", "6690", "6214", "3029", "7765", "6140", "5209"],
    },
    "充電樁/充電服務": {
        "source": "web:充電樁概念股清單",
        "url": "https://statementdog.com/tags/1175",
        "tickers": [
            "2308", "3665", "6290", "2360", "6217", "1519", "1513",
            "6282", "2457", "3023", "3003", "3501", "3092", "5328",
        ],
    },
    "光學鏡片/鏡頭": {
        "source": "web:光學鏡頭概念股清單",
        "url": "https://statementdog.com/tags/491",
        "tickers": [
            "3008", "3406", "3019", "3059", "2374", "3362", "3504",
            "3630", "6209", "6668", "6859", "3441", "6517", "4976",
        ],
    },
    "遊戲股": {
        "source": "web:遊戲概念股清單",
        "url": "https://statementdog.com/tags/1156",
        "tickers": [
            "5478", "3687", "3293", "6180", "6111", "4994", "6542",
            "3083", "3086", "6169", "5310", "4946", "3629", "3064",
            "7584", "5287",
        ],
    },
    "半導體設備": {
        "source": "web:半導體設備概念股清單",
        "url": "https://tw.stock.yahoo.com/class-quote?category=%E5%8D%8A%E5%B0%8E%E9%AB%94%E8%A8%AD%E5%82%99&categoryLabel=%E6%A6%82%E5%BF%B5%E8%82%A1",
        "tickers": [
            "2404", "2464", "3131", "3178", "3218", "3413", "3455",
            "3563", "3583", "3587", "3680", "5443", "6187", "6196",
            "6223", "6515", "6532", "6640", "6691", "6712", "6823",
            "6895",
        ],
    },
    "汽車零件/售後": {
        "source": "web:汽車零件概念股清單",
        "url": "https://statementdog.com/tags/847",
        "tickers": [
            "1319", "1338", "1339", "1521", "1522", "1524", "1525",
            "1533", "1563", "1568", "1587", "2115", "2228", "2231",
            "2233", "2236", "2239", "2252", "2256", "4551", "4581",
            "4583", "4590", "4721", "5288", "6605",
        ],
    },
    "PC/電競品牌": {
        "source": "web:PC與電競品牌概念股清單",
        "url": "https://statementdog.com/tags/15",
        "tickers": ["2353", "2356", "2357", "2376", "2377", "2395", "3406", "4938"],
    },
}


DISCOVER_RULES = [
    ("BBU", "電源供應器/BBU", {"core_business", "supply_chain"}),
    ("重電", "重電", {"core_business"}),
    ("充電樁", "充電樁/充電服務", {"core_business"}),
    ("資安", "資安", {"core_business"}),
    ("儲能", "儲能系統/BESS", {"core_business"}),
    ("安防", "安全監控/影像監控", {"core_business"}),
    ("醫材", "醫材", {"core_business"}),
]


KEYWORDS = {
    "電源供應器/BBU": [
        "BBU", "備援電池", "電池備援", "UPS", "伺服器電源",
        "Backup Battery",
    ],
    "重電": [
        "重電", "變壓器", "配電盤", "GIS", "氣體絕緣開關", "強韌電網",
        "台電", "輸配電", "開關設備", "電力設備",
    ],
    "資安": ["資安", "資訊安全", "SOC", "MSSP", "防火牆", "滲透測試", "弱點掃描", "SIEM"],
    "充電樁/充電服務": ["充電樁", "充電站", "充電槍", "EV charging", "充電服務", "電動車充電"],
    "光學鏡片/鏡頭": ["光學", "鏡頭", "鏡片", "鏡頭模組", "影像模組", "相機", "ADAS鏡頭", "攝影機"],
    "遊戲股": ["遊戲", "手遊", "線上遊戲", "MMORPG", "遊戲平台", "博弈", "遊戲研發", "遊戲發行"],
    "半導體設備": [
        "半導體設備", "晶圓廠", "晶圓代工廠", "蝕刻", "沉積", "微影",
        "檢測設備", "測試設備", "探針卡", "Probe Card", "廠務", "無塵室",
    ],
    "資料中心": ["資料中心", "Data Center", "AI 資料中心", "CSP", "雲端資料中心", "伺服器機房"],
    "儲能系統/BESS": ["儲能", "BESS", "Energy Storage", "儲能系統", "儲能櫃", "電池櫃"],
    "安全監控/影像監控": ["安防", "監控", "攝影機", "影像監控", "DVR", "NVR", "門禁", "安全監控"],
    "醫材": ["醫材", "醫療器材", "醫療設備", "診斷設備", "耗材", "內視鏡", "手術器械"],
}


@dataclass(frozen=True)
class AddEvidence:
    group: str
    ticker: str
    confidence: str
    source: str
    reason: str
    evidence: str


def load_current_groups() -> dict[str, list[str]]:
    import concept_groups

    importlib.reload(concept_groups)
    out: dict[str, list[str]] = {}
    for group, members in concept_groups.CONCEPT_GROUPS.items():
        out[group] = list(dict.fromkeys(str(m) for m in members))
    return out


def load_profiles() -> dict[str, dict]:
    return json.loads(PROFILES_PATH.read_text(encoding="utf-8"))


def collect_report_index() -> dict[str, dict]:
    out: dict[str, dict] = {}
    if not REPORTS_DIR.exists():
        return out
    for path in REPORTS_DIR.glob("**/*.md"):
        m = re.match(r"^(\d{4,5})_(.+)\.md$", path.name)
        if not m:
            continue
        ticker, name = m.group(1), m.group(2)
        out[ticker] = {
            "name": name,
            "sector": path.parent.name,
            "path": str(path.relative_to(ROOT)),
        }
    return out


def ticker_name(ticker: str, profiles: dict[str, dict], reports: dict[str, dict]) -> str:
    return (profiles.get(ticker) or {}).get("name") or (reports.get(ticker) or {}).get("name", "")


def has_any(text: str, keywords: Iterable[str]) -> bool:
    t = text.lower()
    return any(kw.lower() in t for kw in keywords if kw)


def first_hit(text: str, keywords: Iterable[str]) -> str:
    t = text.lower()
    for kw in keywords:
        if kw and kw.lower() in t:
            return kw
    return ""


def is_web_seed_ticker(group: str, ticker: str) -> bool:
    return ticker in set((WEB_SEED_SOURCES.get(group) or {}).get("tickers", []))


def coverage_text(ticker: str, cache: dict[str, str]) -> str:
    if ticker not in cache:
        text, _meta = build_primary_coverage_text(ticker, max_chars=5200)
        cache[ticker] = text
    return cache[ticker]


def coverage_parts(ticker: str, cache: dict[str, dict[str, str]]) -> dict[str, str]:
    if ticker in cache:
        return cache[ticker]
    data = read_coverage_sections(ticker)
    sections = data.get("sections", {}) if data.get("found") else {}
    core_chunks: list[str] = []
    supply_chunks: list[str] = []
    for sec, body in sections.items():
        if any(hint in sec for hint in ["業務", "營收"]):
            core_chunks.append(body)
        if any(hint in sec for hint in ["供應鏈", "主要客戶", "供應商"]):
            supply_chunks.append(body)
    if not core_chunks:
        core, _meta = build_primary_coverage_text(ticker, max_chars=2600)
        core_chunks.append(core)
    all_text, _meta = build_primary_coverage_text(ticker, max_chars=5200)
    cache[ticker] = {
        "core": "\n".join(core_chunks)[:3200],
        "supply": "\n".join(supply_chunks)[:2600],
        "all": all_text,
    }
    return cache[ticker]


def local_context(
    ticker: str,
    profiles: dict[str, dict],
    reports: dict[str, dict],
    cache: dict[str, dict[str, str]],
    mode: str = "core",
) -> str:
    prof = profiles.get(ticker) or {}
    report = reports.get(ticker) or {}
    parts_data = coverage_parts(ticker, cache)
    if mode == "all":
        body = parts_data["all"]
    elif mode == "supply":
        body = parts_data["core"] + "\n" + parts_data["supply"]
    else:
        body = parts_data["core"]
    parts = [
        prof.get("name", ""),
        prof.get("twse_industry", ""),
        prof.get("industry_segment", ""),
        prof.get("supply_chain_position", ""),
        " ".join(prof.get("core_themes") or []),
        report.get("sector", ""),
        body,
    ]
    return "\n".join(str(p) for p in parts if p)


def discover_results() -> dict[tuple[str, str], set[str]]:
    """呼叫 My-TW-Coverage/scripts/discover.py 的 search_reports。

    回傳 key=(group,ticker)，value=命中的 buzzword/role 集合。
    """
    if str(MYTW_SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(MYTW_SCRIPTS_DIR))
    try:
        from discover import search_reports
    except Exception:
        return {}

    hits: dict[tuple[str, str], set[str]] = defaultdict(set)
    for buzzword, group, allowed_roles in DISCOVER_RULES:
        try:
            rows = search_reports(buzzword)
        except Exception:
            continue
        for row in rows:
            role = row.get("role", "mentioned")
            if role not in allowed_roles:
                continue
            ticker = str(row.get("ticker", ""))
            if ticker:
                hits[(group, ticker)].add(f"{buzzword}:{role}")
    return hits


def group_exists(group: str, groups: dict[str, list[str]]) -> bool:
    return group in groups


def add_candidate(
    candidates: dict[tuple[str, str], AddEvidence],
    groups: dict[str, list[str]],
    profiles: dict[str, dict],
    reports: dict[str, dict],
    group: str,
    ticker: str,
    confidence: str,
    source: str,
    reason: str,
    evidence: str,
) -> None:
    if not group_exists(group, groups):
        return
    if group in LOCKED_AUTO_ADD_GROUPS:
        return
    if ticker in EXCLUDE_BY_GROUP.get(group, set()):
        return
    if ticker not in profiles and ticker not in reports:
        return
    if ticker in groups.get(group, []):
        return
    key = (group, ticker)
    current = candidates.get(key)
    rank = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}
    if current and rank.get(current.confidence, 0) >= rank.get(confidence, 0):
        return
    candidates[key] = AddEvidence(
        group=group,
        ticker=ticker,
        confidence=confidence,
        source=source,
        reason=reason,
        evidence=evidence[:260].replace("\n", " "),
    )


def validate_seed_group(group: str, ticker: str, ctx: str, prof: dict, report: dict) -> tuple[bool, str]:
    kw = first_hit(ctx, KEYWORDS.get(group, []))
    sector = report.get("sector", "")
    twse = prof.get("twse_industry", "")

    if group == "電源供應器/BBU":
        if kw:
            return True, kw
        return False, ""
    if group == "半導體設備":
        if sector == "Semiconductor Equipment & Materials" and has_any(ctx, ["半導體設備", "晶圓", "封裝", "廠務", "探針", "檢測", "測試", "蝕刻", "沉積", "微影"]):
            return True, "Semiconductor Equipment & Materials + 半導體設備語境"
        if kw and has_any(ctx, ["半導體", "晶圓", "封裝", "IC", "台積電"]):
            return True, kw
        return False, ""
    if group == "重電":
        if kw:
            return True, kw
        return False, ""
    if group == "資安":
        if kw and (
            prof.get("industry_segment") == "SOFTWARE"
            or sector in {"Information Technology Services", "Software - Application", "Software - Infrastructure", "Security & Protection Services"}
            or is_web_seed_ticker(group, ticker)
        ):
            return True, kw
        return False, ""
    if group == "遊戲股":
        if sector == "Electronic Gaming & Multimedia" or is_web_seed_ticker(group, ticker):
            return True, kw or sector or "web seed"
        if kw and prof.get("industry_segment") == "SOFTWARE":
            return True, kw or sector
        return False, ""
    if group == "光學鏡片/鏡頭":
        if kw and (twse == "光電業" or sector in {"Scientific & Technical Instruments", "Electronic Components", "Consumer Electronics"}):
            return True, kw
        return False, ""
    if group == "汽車零件/售後":
        if twse == "汽車工業" or sector == "Auto Parts" or has_any(ctx, ["汽車零件", "AM 售後", "車燈", "保險桿", "傳動", "煞車"]):
            return True, twse or sector or "汽車零件語境"
        return False, ""
    if group == "PC/電競品牌":
        if kw or has_any(ctx, ["電競", "主機板", "筆電", "PC", "顯示卡", "遊戲筆電"]):
            return True, kw or "PC/電競語境"
        return False, ""
    if group in KEYWORDS:
        if kw:
            return True, kw
        return False, ""
    return False, ""


def apply_web_seed_rules(
    candidates: dict[tuple[str, str], AddEvidence],
    groups: dict[str, list[str]],
    profiles: dict[str, dict],
    reports: dict[str, dict],
    cache: dict[str, dict[str, str]],
) -> None:
    for group, payload in WEB_SEED_SOURCES.items():
        for ticker in payload["tickers"]:
            prof = profiles.get(ticker) or {}
            report = reports.get(ticker) or {}
            mode = "supply" if group in {"電源供應器/BBU", "半導體設備"} else "core"
            ctx = local_context(ticker, profiles, reports, cache, mode=mode)
            ok, reason = validate_seed_group(group, ticker, ctx, prof, report)
            if not ok:
                continue
            add_candidate(
                candidates,
                groups,
                profiles,
                reports,
                group,
                ticker,
                "HIGH",
                payload["source"],
                f"網路成分股候選 + 本業/供應鏈驗證命中：{reason}",
                ctx,
            )


def apply_discover_rules(
    candidates: dict[tuple[str, str], AddEvidence],
    groups: dict[str, list[str]],
    profiles: dict[str, dict],
    reports: dict[str, dict],
    cache: dict[str, dict[str, str]],
) -> None:
    for (group, ticker), roles in discover_results().items():
        prof = profiles.get(ticker) or {}
        report = reports.get(ticker) or {}
        mode = "supply" if group in {"電源供應器/BBU", "半導體設備"} else "core"
        ctx = local_context(ticker, profiles, reports, cache, mode=mode)
        ok, reason = validate_seed_group(group, ticker, ctx, prof, report)
        if not ok and group == "儲能系統/BESS":
            ok = has_any(ctx, ["儲能", "BESS", "電池櫃", "能源管理", "PCS", "逆變器"])
            reason = "discover 儲能 + 儲能系統語境" if ok else ""
        if not ok:
            continue
        confidence = "HIGH" if any("core_business" in r for r in roles) else "MEDIUM"
        add_candidate(
            candidates,
            groups,
            profiles,
            reports,
            group,
            ticker,
            confidence,
            "My-TW-Coverage/scripts/discover.py",
            f"discover 命中 {', '.join(sorted(roles))}；本業/供應鏈再驗證：{reason}",
            ctx,
        )


def industry_rescue_group(ticker: str, prof: dict, report: dict, ctx: str) -> tuple[str, str, str] | None:
    twse = prof.get("twse_industry", "")
    segment = prof.get("industry_segment", "")
    position = prof.get("supply_chain_position", "")
    sector = report.get("sector", "")

    if twse == "鋼鐵工業" or sector in {"Steel", "Aluminum", "Copper", "Other Industrial Metals & Mining"}:
        if has_any(ctx, ["螺絲", "螺帽", "緊固件", "扣件"]):
            return "螺絲/螺帽/緊固件", "HIGH", "鋼鐵/金屬產業 + 螺絲扣件語境"
        return "鋼鐵", "HIGH", "TWSE/報告產業為鋼鐵或金屬材料"

    if twse == "紡織纖維" or sector in {"Textile Manufacturing", "Apparel Manufacturing"}:
        return "紡織/機能布", "HIGH", "TWSE/報告產業為紡織"

    if twse == "橡膠工業":
        return "輪胎/橡膠", "HIGH", "TWSE 產業為橡膠工業"

    if twse == "造紙工業" or sector in {"Packaging & Containers", "Lumber & Wood Production"}:
        return "造紙/紙業", "HIGH", "TWSE/報告產業為造紙或紙包材"

    if twse == "汽車工業" or sector in {"Auto Parts", "Auto Manufacturers", "Auto & Truck Dealerships"}:
        if has_any(ctx, ["車用電子", "ADAS", "感測器", "雷達", "鏡頭", "車載"]):
            return "車用電子", "MEDIUM", "汽車產業 + 車用電子語境"
        return "汽車零件/售後", "HIGH", "TWSE/報告產業為汽車零組件"

    if twse == "電器電纜" or sector == "Electrical Equipment & Parts":
        if has_any(ctx, KEYWORDS["重電"]):
            return "重電", "HIGH", "電器電纜/電機設備 + 重電語境"
        if has_any(ctx, ["電纜", "電線", "銅線", "海纜", "海底電纜"]):
            return "銅纜/銅加工", "MEDIUM", "電纜/銅線語境"
        return "綠能/儲能", "MEDIUM", "電力設備產業，未命中特定重電子題材"

    if twse == "電機機械" or sector in {"Specialty Industrial Machinery", "Tools & Accessories", "Industrial Distribution"}:
        if has_any(ctx, KEYWORDS["重電"]):
            return "重電", "HIGH", "電機機械 + 重電/台電/變壓器語境"
        if has_any(ctx, ["工具機", "CNC", "車床", "銑床"]):
            return "工具機", "HIGH", "工具機/CNC 語境"
        if has_any(ctx, ["手工具", "電動工具", "氣動工具"]):
            return "手工具/電動工具", "HIGH", "手工具/電動工具語境"
        if has_any(ctx, ["齒輪", "減速機", "傳動系統"]):
            return "齒輪/減速機", "HIGH", "齒輪/減速機語境"
        if has_any(ctx, ["閥門", "管材", "接頭", "球閥"]):
            return "閥門管材", "HIGH", "閥門管材語境"
        return "精密機械/自動化", "MEDIUM", "電機機械/專用機械產業"

    if twse == "光電業":
        if has_any(ctx, ["面板", "顯示器", "LCD", "TFT", "背光模組"]):
            return "面板/顯示器", "HIGH", "光電業 + 面板/顯示器語境"
        if has_any(ctx, ["鏡頭", "鏡片", "光學", "影像模組", "攝影機", "ADAS鏡頭"]):
            return "光學鏡片/鏡頭", "HIGH", "光電業 + 光學鏡頭/影像語境"
        if has_any(ctx, ["薄膜", "偏光", "保護膜", "光學膜"]):
            return "光學薄膜", "HIGH", "光電業 + 光學薄膜語境"
        if has_any(ctx, ["LED", "Mini LED", "Micro LED", "發光二極體"]):
            return "LED/光電", "HIGH", "光電業 + LED 語境"
        return "利基光電", "MEDIUM", "TWSE 產業為光電業但未命中特定子族群"

    if twse == "半導體業" or sector in {"Semiconductors", "Semiconductor Equipment & Materials"}:
        if ticker in MATURE_FOUNDRY_EXACT and has_any(ctx, ["晶圓代工", "Foundry", "成熟製程", "IDM", "功率半導體"]):
            return "晶圓代工成熟製程", "HIGH", "晶圓代工/成熟製程/IDM 語境"
        if sector == "Semiconductor Equipment & Materials" and has_any(
            ctx,
            [
                "半導體設備", "探針卡", "測試設備", "檢測設備", "製程設備",
                "清洗設備", "蝕刻", "沉積", "微影設備", "AOI", "測試介面",
                "廠務", "無塵室",
            ],
        ):
            if has_any(ctx, ["無塵室", "廠務", "機電工程", "潔淨室"]):
                return "無塵室/廠務工程", "HIGH", "半導體廠務/無塵室工程語境"
            return "半導體設備", "HIGH", "半導體設備/檢測/探針/廠務語境"
        if has_any(ctx, ["無塵室", "廠務", "機電工程", "潔淨室"]):
            return "無塵室/廠務工程", "HIGH", "半導體廠務/無塵室工程語境"
        if has_any(ctx, ["封裝測試", "封測服務", "半導體封測", "IC 封測", "IC封測", "測試服務", "封裝服務"]):
            return "晶片封測", "HIGH", "半導體封裝測試語境"
        if has_any(ctx, ["類比IC", "Analog", "電源管理IC", "PMIC", "驅動IC"]):
            return "半導體類比IC", "HIGH", "類比 IC/PMIC/驅動 IC 語境"
        if (
            has_any(ctx, ["IC設計公司", "晶片設計公司", "Fabless", "無晶圓", "專注於 IC 設計", "專注於晶片設計", "ASIC 設計", "IP 授權"])
            and not has_any(ctx, ["晶圓代工", "Foundry", "製造服務", "晶圓製造"])
        ):
            return "IC設計", "HIGH", "IC 設計/Fabless/IP 語境"
        if has_any(ctx, ["功率半導體", "MOSFET", "二極體", "整流器"]):
            return "功率半導體 IC", "HIGH", "功率半導體/分離式元件語境"
    if twse == "電子零組件業" or sector == "Electronic Components":
        if position == "CONNECTOR" or has_any(ctx, ["連接器", "線束", "端子", "Connector"]):
            return "連接器", "HIGH", "電子零組件 + 連接器/線束語境"
        if position == "PASSIVE" or has_any(ctx, ["被動元件", "電容", "電阻", "電感", "MLCC"]):
            return "被動元件", "HIGH", "電子零組件 + 被動元件語境"
        if position == "THERMAL" or has_any(ctx, ["散熱", "液冷", "熱管", "均熱板", "水冷板"]):
            return "散熱/液冷", "HIGH", "電子零組件 + 散熱/液冷語境"
        if position in {"PCB_HDI", "SUBSTRATE"} or has_any(ctx, ["PCB", "HDI", "銅箔基板", "軟板", "FPC"]):
            if has_any(ctx, ["軟板", "FPC", "Flexible PCB"]):
                return "Flexible PCB/軟板", "HIGH", "電子零組件 + 軟板/FPC 語境"
            return "PCB/銅箔基板", "HIGH", "電子零組件 + PCB/基板語境"
        return "電子零組件/一般", "MEDIUM", "TWSE/報告產業為電子零組件"

    if twse == "其他電子業" or sector in {"Scientific & Technical Instruments", "Business Equipment & Supplies"}:
        if has_any(ctx, ["半導體設備", "探針卡", "檢測", "測試", "AOI", "自動光學檢查"]):
            return "檢測/設備服務", "HIGH", "其他電子 + 檢測/測試設備語境"
        if has_any(ctx, ["無塵室", "廠務", "潔淨室", "機電工程"]):
            return "無塵室/廠務工程", "HIGH", "其他電子 + 廠務/無塵室語境"
        if has_any(ctx, ["工業電腦", "工控", "自動化", "PLC"]):
            return "其他電子/工控", "HIGH", "其他電子 + 工控/自動化語境"
        return "其他電子/工控", "MEDIUM", "TWSE/報告產業為其他電子"

    if twse in {"資訊服務業", "數位雲端"} or sector in {
        "Information Technology Services", "Software - Application",
        "Software - Infrastructure", "Internet Content & Information",
    }:
        if has_any(ctx, KEYWORDS["資安"]):
            return "資安", "HIGH", "資訊服務/數位雲端 + 資安語境"
        if has_any(ctx, KEYWORDS["遊戲股"]) or sector == "Electronic Gaming & Multimedia":
            return "遊戲股", "HIGH", "軟體/數位雲端 + 遊戲語境"
        if has_any(ctx, ["雲端", "SaaS", "IaaS", "PaaS", "Cloud", "訂閱制"]):
            return "雲端服務/SaaS", "HIGH", "軟體/資訊服務 + 雲端/SaaS 語境"
        return "資訊服務/IT服務", "MEDIUM", "TWSE/報告產業為資訊服務或軟體"

    if twse == "電腦及週邊設備業" or sector == "Computer Hardware":
        if has_any(ctx, ["工業電腦", "IPC", "嵌入式", "強固型", "POS"]):
            return "工業電腦/IPC", "HIGH", "電腦週邊 + 工業電腦/IPC 語境"
        if has_any(ctx, ["電競", "遊戲筆電", "主機板", "顯示卡", "PC 品牌", "筆電品牌"]):
            return "PC/電競品牌", "HIGH", "電腦週邊 + PC/電競品牌語境"
        if has_any(ctx, ["伺服器準系統", "Server", "伺服器主機板", "裸機"]):
            return "伺服器準系統", "HIGH", "電腦週邊 + 伺服器準系統語境"
        return "電腦週邊/配件", "MEDIUM", "TWSE/報告產業為電腦及週邊"

    if twse == "通信網路業" or sector in {"Communication Equipment", "Telecom Services"}:
        if has_any(ctx, ["800G", "1.6T", "高速傳輸", "交換器", "Switch", "SerDes"]):
            return "高速傳輸", "HIGH", "通信網路 + 800G/交換器/高速傳輸語境"
        if has_any(ctx, ["5G", "基地台", "小型基地台", "通訊模組"]):
            return "5G 通訊", "HIGH", "通信網路 + 5G/基地台語境"
        if has_any(ctx, ["低軌", "衛星", "LEO"]):
            return "低軌衛星", "HIGH", "通信網路 + 低軌衛星語境"
        return "網通", "MEDIUM", "TWSE/報告產業為通信網路"

    if twse == "綠能環保" or sector in {"Solar", "Utilities - Renewable", "Waste Management", "Pollution & Treatment Controls"}:
        if has_any(ctx, ["太陽能", "光電板", "模組", "逆變器"]):
            return "太陽能/光電板", "HIGH", "綠能環保 + 太陽能語境"
        if has_any(ctx, ["風電", "離岸風電"]):
            return "風電/離岸風電", "HIGH", "綠能環保 + 風電語境"
        if has_any(ctx, ["儲能", "BESS", "電池櫃"]):
            return "儲能系統/BESS", "HIGH", "綠能環保 + 儲能語境"
        if has_any(ctx, ["廢棄物", "回收", "資源化", "環保"]):
            return "廢棄物處理/環保", "HIGH", "綠能環保 + 廢棄物/回收語境"
        return "綠能/儲能", "MEDIUM", "TWSE/報告產業為綠能環保"

    if twse == "化學工業" or sector in {"Chemicals", "Specialty Chemicals"}:
        if has_any(ctx, ["光阻", "半導體", "電子化學", "特殊氣體", "CMP", "顯影液"]):
            return "特用化學/光阻劑", "HIGH", "化學產業 + 半導體電子化學品語境"
        return "化工/染料/特化", "HIGH", "TWSE/報告產業為化學"

    if twse == "航運業" or sector in {"Marine Shipping", "Airlines", "Integrated Freight & Logistics", "Railroads", "Trucking"}:
        if sector == "Marine Shipping" or has_any(ctx, ["貨櫃", "散裝", "航運"]):
            return "交通運輸/物流", "MEDIUM", "航運/物流產業"
        if sector == "Airlines" or has_any(ctx, ["航空", "飛機", "航太"]):
            return "航太", "MEDIUM", "航空/航太語境"
        return "交通運輸/物流", "HIGH", "TWSE/報告產業為航運物流"

    if twse == "文化創意業" or sector in {"Entertainment", "Publishing", "Broadcasting", "Electronic Gaming & Multimedia"}:
        if has_any(ctx, KEYWORDS["遊戲股"]):
            return "遊戲股", "HIGH", "文創/娛樂 + 遊戲語境"
        if has_any(ctx, ["IP", "授權", "內容", "音樂", "影視", "藝文", "演唱會"]):
            return "文創/IP 內容", "HIGH", "文創產業 + IP/內容語境"
        return "文化傳媒/出版", "MEDIUM", "文創/出版/娛樂產業"

    if twse == "運動休閒" or sector in {"Leisure", "Footwear & Accessories", "Recreational Vehicles"}:
        if has_any(ctx, ["健身", "運動用品", "球具", "高爾夫", "自行車", "戶外"]):
            return "健身/運動用品", "HIGH", "運動休閒 + 健身/運動用品語境"
        return "運動休閒", "MEDIUM", "TWSE/報告產業為運動休閒"

    if twse == "居家生活" or sector in {"Furnishings, Fixtures & Appliances", "Home Improvement Retail", "Household & Personal Products"}:
        if has_any(ctx, ["寵物"]):
            return "寵物/生活周邊", "HIGH", "居家生活 + 寵物語境"
        if has_any(ctx, ["美容", "保養", "個人護理", "清潔用品"]):
            return "美容保健/個人護理", "HIGH", "居家生活 + 個人護理語境"
        return "居家修繕/家居用品", "MEDIUM", "TWSE/報告產業為居家生活"

    if segment == "MED_BIO":
        if has_any(ctx, ["CDMO", "委託開發", "委託製造", "代工"]):
            return "CDMO/生技製造服務", "HIGH", "生技醫療 + CDMO/代工語境"
        if has_any(ctx, ["檢測", "診斷", "IVD", "基因檢測"]):
            return "精準診斷/體外診斷", "HIGH", "生技醫療 + 診斷/檢測語境"
        if has_any(ctx, ["醫療器材", "醫材", "手術", "內視鏡"]):
            return "醫材", "HIGH", "生技醫療 + 醫材語境"
        if has_any(ctx, ["新藥", "臨床", "抗體", "疫苗"]):
            return "新藥研發", "HIGH", "生技醫療 + 新藥/臨床語境"
        return "中小型生技", "MEDIUM", "生技醫療 segment"

    return None


def apply_industry_rules(
    candidates: dict[tuple[str, str], AddEvidence],
    groups: dict[str, list[str]],
    profiles: dict[str, dict],
    reports: dict[str, dict],
    cache: dict[str, dict[str, str]],
) -> None:
    for ticker, prof in profiles.items():
        report = reports.get(ticker) or {}
        ctx = local_context(ticker, profiles, reports, cache, mode="core")
        rec = industry_rescue_group(ticker, prof, report, ctx)
        if not rec:
            continue
        group, confidence, reason = rec
        add_candidate(
            candidates,
            groups,
            profiles,
            reports,
            group,
            ticker,
            confidence,
            "stock_profiles + My-TW-Coverage",
            reason,
            ctx,
        )


def build_payload() -> dict:
    groups = load_current_groups()
    profiles = load_profiles()
    reports = collect_report_index()
    cache: dict[str, dict[str, str]] = {}
    candidates: dict[tuple[str, str], AddEvidence] = {}

    apply_web_seed_rules(candidates, groups, profiles, reports, cache)
    apply_discover_rules(candidates, groups, profiles, reports, cache)
    apply_industry_rules(candidates, groups, profiles, reports, cache)

    new_groups = {g: list(members) for g, members in groups.items()}
    evidence_rows: list[dict] = []
    additions_by_group = Counter()
    for (group, ticker), ev in sorted(candidates.items(), key=lambda item: (item[0][0], item[0][1])):
        if ticker in new_groups[group]:
            continue
        new_groups[group].append(ticker)
        additions_by_group[group] += 1
        prof = profiles.get(ticker) or {}
        report = reports.get(ticker) or {}
        evidence_rows.append({
            "group": group,
            "ticker": ticker,
            "name": ticker_name(ticker, profiles, reports),
            "verdict": "CORE" if ev.confidence == "HIGH" else "SATELLITE",
            "confidence": ev.confidence,
            "source": ev.source,
            "reason": ev.reason,
            "evidence": ev.evidence,
            "twse_industry": prof.get("twse_industry", ""),
            "industry_segment": prof.get("industry_segment", ""),
            "supply_chain_position": prof.get("supply_chain_position", ""),
            "report_sector": report.get("sector", ""),
            "coverage_path": report.get("path", ""),
            "decided_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        })

    for group, exact in HARD_EXACT_MEMBERS.items():
        if group in new_groups:
            new_groups[group] = [ticker for ticker in groups[group] if ticker in exact]

    old_members = {t for members in groups.values() for t in members}
    new_members = {t for members in new_groups.values() for t in members}
    unassigned = sorted(set(profiles) - new_members)
    still_rows = []
    for ticker in unassigned:
        prof = profiles.get(ticker) or {}
        report = reports.get(ticker) or {}
        still_rows.append({
            "ticker": ticker,
            "name": ticker_name(ticker, profiles, reports),
            "twse_industry": prof.get("twse_industry", ""),
            "industry_segment": prof.get("industry_segment", ""),
            "supply_chain_position": prof.get("supply_chain_position", ""),
            "core_themes": ";".join(prof.get("core_themes") or []),
            "report_sector": report.get("sector", ""),
            "reason": "v6 未達多源驗證門檻，暫不上架",
        })

    summary_rows = []
    for group in groups:
        old_set = set(groups[group])
        new_set = set(new_groups[group])
        summary_rows.append({
            "group": group,
            "old_count": len(groups[group]),
            "new_count": len(new_groups[group]),
            "added": len(new_set - old_set),
            "removed": len(old_set - new_set),
        })

    return {
        "groups": new_groups,
        "evidence_trail": evidence_rows,
        "still_unassigned": still_rows,
        "summary_rows": summary_rows,
        "summary": {
            "ran_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "validator_version": "v6.0.0-rescue-unassigned",
            "groups_evaluated": len(groups),
            "old_membership_entries": sum(len(m) for m in groups.values()),
            "new_membership_entries": sum(len(m) for m in new_groups.values()),
            "old_unique_members": len(old_members),
            "new_unique_members": len(new_members),
            "added_membership_entries": sum(row["added"] for row in summary_rows),
            "removed_membership_entries": sum(row["removed"] for row in summary_rows),
            "still_unassigned": len(still_rows),
            "additions_by_group": dict(additions_by_group),
        },
    }


def write_run(payload: dict, run_dir: Path) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "master_patch_v6.json").write_text(
        json.dumps(payload["groups"], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    with (run_dir / "evidence_trail.jsonl").open("w", encoding="utf-8") as f:
        for row in payload["evidence_trail"]:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    with (run_dir / "rescue_summary.csv").open("w", encoding="utf-8", newline="") as f:
        fieldnames = ["group", "old_count", "new_count", "added", "removed"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(payload["summary_rows"])
    with (run_dir / "still_unassigned.csv").open("w", encoding="utf-8", newline="") as f:
        fieldnames = [
            "ticker", "name", "twse_industry", "industry_segment",
            "supply_chain_position", "core_themes", "report_sector", "reason",
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(payload["still_unassigned"])
    (run_dir / "manifest.json").write_text(
        json.dumps(payload["summary"] | {"run_id": run_dir.name}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (run_dir / "web_sources.md").write_text(render_web_sources(), encoding="utf-8")
    (run_dir / "diff_vs_current.md").write_text(render_diff(payload), encoding="utf-8")


def render_web_sources() -> str:
    lines = [
        "# v6 網路概念股候選來源",
        "",
        "網路來源只作為候選清單；實際上架仍需通過 My-TW-Coverage/stock_profiles 本業或供應鏈驗證。",
        "",
    ]
    for group, payload in WEB_SEED_SOURCES.items():
        lines.append(f"- {group}: {payload['url']} ({payload['source']})")
    return "\n".join(lines) + "\n"


def render_diff(payload: dict, top_n: int = 80) -> str:
    s = payload["summary"]
    lines = [
        "# v6 補族群結果",
        "",
        f"- 族群數：{s['groups_evaluated']}",
        f"- membership entries：{s['old_membership_entries']} -> {s['new_membership_entries']}",
        f"- unique members：{s['old_unique_members']} -> {s['new_unique_members']}",
        f"- 新增 membership entries：{s['added_membership_entries']}",
        f"- 移除 membership entries：{s['removed_membership_entries']}",
        f"- 仍未上架：{s['still_unassigned']}",
        "",
        "## 新增最多的族群",
    ]
    rows = sorted(payload["summary_rows"], key=lambda r: r["added"], reverse=True)
    for row in rows[:top_n]:
        if not row["added"] and not row["removed"]:
            continue
        lines.append(f"- {row['group']}: {row['old_count']} -> {row['new_count']} (+{row['added']}, -{row['removed']})")
    return "\n".join(lines) + "\n"


def render_concept_groups(payload: dict) -> str:
    profiles = load_profiles()
    reports = collect_report_index()
    current_order = list(load_current_groups().keys())
    groups = payload["groups"]
    lines = [
        '"""網站題材族群清單。',
        "",
        "此檔由 concept_taxonomy.validator.rescue_unassigned_v6 產生。",
        "v6 在 v5 嚴格驗證後，只補回通過網路候選 + 本業/供應鏈、或產業結構多源驗證的股票。",
        "完整證據請看 concept_taxonomy/validation_runs/*_rescue_v6/evidence_trail.jsonl。",
        '"""',
        "",
        "CONCEPT_GROUPS = {",
    ]
    for group_name in current_order:
        keep = list(dict.fromkeys(groups.get(group_name, [])))
        lines.append(f'    "{group_name}": [')
        if keep:
            lines.append(f"        # v6 count={len(keep)}")
        for ticker in keep:
            name = ticker_name(ticker, profiles, reports)
            comment = f"  # {name}" if name else ""
            lines.append(f'        "{ticker}",{comment}')
        lines.append("    ],")
    lines.append("}")
    lines.append("")
    return "\n".join(lines)


def apply_to_site(payload: dict, run_dir: Path) -> None:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = CONCEPT_GROUPS_PATH.with_name(f"concept_groups.py.bak_v6_{ts}")
    shutil.copy(CONCEPT_GROUPS_PATH, backup)
    CONCEPT_GROUPS_PATH.write_text(render_concept_groups(payload), encoding="utf-8")
    shutil.copy(CONCEPT_GROUPS_PATH, run_dir / "snapshot_concept_groups.py")
    print(f"[v6] backup: {backup.name}")
    print("[v6] applied concept_groups.py and snapshot saved")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="write validation run")
    ap.add_argument("--apply", action="store_true", help="apply generated groups to concept_groups.py")
    args = ap.parse_args()

    payload = build_payload()
    s = payload["summary"]
    print(
        "[v6] "
        f"entries={s['old_membership_entries']}->{s['new_membership_entries']} "
        f"unique={s['old_unique_members']}->{s['new_unique_members']} "
        f"added=+{s['added_membership_entries']} "
        f"still_unassigned={s['still_unassigned']}"
    )

    run_dir = VALIDATION_RUNS_DIR / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_rescue_v6"
    if args.write or args.apply:
        write_run(payload, run_dir)
        print(f"[v6] wrote {run_dir.relative_to(ROOT)}")
    if args.apply:
        apply_to_site(payload, run_dir)


if __name__ == "__main__":
    main()
