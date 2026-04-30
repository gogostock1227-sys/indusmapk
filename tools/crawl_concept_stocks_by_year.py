from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable
from urllib.parse import parse_qs, quote_plus, unquote, urljoin, urlparse

import requests
import urllib3
from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
OUT_ROOT = ROOT / "data" / "concept_stocks_by_year"
CACHE_DIR = ROOT / "data" / ".cache" / "cmoney_concepts"
CMONEY_INDEX = "https://www.cmoney.tw/forum/concept"
CRAWL_DATE = datetime.now().strftime("%Y-%m-%d")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.7",
}

CSV_FIELDS = [
    "stock_id",
    "stock_name",
    "concept_name",
    "normalized_concept_name",
    "folder_year",
    "source_year",
    "inferred_theme_year",
    "source_platform",
    "source_type",
    "source_url",
    "source_title",
    "theme_source_title",
    "theme_source_url",
    "theme_source_platform",
    "matched_by",
    "confidence",
    "evidence_text",
    "crawl_date",
    "notes",
]

# 這份年份表是「題材被市場明顯討論的年份」種子；成分股仍由 CMoney
# 詳頁或本專案既有 concept_groups 補齊。概念可跨年重複，代表該題材
# 在不同年度都曾被市場討論。
YEAR_CONCEPT_SEEDS: dict[int, list[str]] = {
    2020: [
        "防疫",
        "遠距教學",
        "居家辦公(WFH)",
        "宅經濟",
        "Chromebook",
        "電商",
        "物流",
        "線上遊戲",
        "5G",
        "O-RAN",
        "WiFi 6",
        "Mini LED",
        "PCB",
        "IC載板",
        "被動元件",
        "電源供應器",
        "生技醫療",
        "保健食品",
        "旅遊",
    ],
    2021: [
        "電動車",
        "Tesla特斯拉",
        "MIH",
        "鴻海MIH電動車平台",
        "元宇宙",
        "虛擬貨幣",
        "比特幣挖礦",
        "碳權",
        "風力發電",
        "太陽能",
        "氫燃料電池",
        "功率半導體",
        "第三方支付",
        "電商",
        "物流",
        "散熱模組",
        "資安",
    ],
    2022: [
        "軍工/國防",
        "無人機",
        "資安",
        "美元升值",
        "航空/航太",
        "原料藥",
        "生技醫療",
        "醫療器材耗材",
        "智慧醫療",
        "電動車",
        "車用電子",
        "智慧電網",
        "風力發電",
        "太陽能",
        "半導體設備",
        "矽晶圓",
    ],
    2023: [
        "ChatGPT",
        "AI人工智慧",
        "AI伺服器",
        "CoWoS",
        "CoWoS先進封裝",
        "散熱模組",
        "散熱/液冷",
        "光通訊",
        "光通訊/CPO",
        "衛星/低軌衛星",
        "低軌衛星",
        "軍工/國防",
        "無人機",
        "資安",
        "碳權",
        "電源供應器",
        "電源供應器/BBU",
    ],
    2024: [
        "AI PC",
        "AI PC/邊緣AI",
        "HBM",
        "HBM 高頻寬記憶體",
        "GB200",
        "ASIC",
        "ASIC/IP矽智財",
        "矽智財IP",
        "CoWoS",
        "CoWoS先進封裝",
        "玻璃基板 E-Core Sys.",
        "FOPLP扇出型封裝",
        "記憶體",
        "光通訊",
        "光通訊/CPO",
        "BBU",
        "電源供應器/BBU",
        "PCB",
        "銅箔基板",
        "半導體設備",
    ],
    2025: [
        "GB300",
        "TPU",
        "Google TPU",
        "AWS",
        "Oracle甲骨文",
        "LPU",
        "ASIC",
        "ASIC/IP矽智財",
        "矽智財IP",
        "3DIC聯盟",
        "AI伺服器",
        "輝達概念股",
        "機器人",
        "智慧型機器人/機械手臂",
        "無人機",
        "低軌衛星",
        "特用化學",
        "特用化學/光阻劑",
        "重電",
        "HVDC/直流電力",
        "光通訊/CPO",
    ],
    2026: [
        "GB300",
        "TPU",
        "Google TPU",
        "AWS",
        "Oracle甲骨文",
        "ASIC",
        "ASIC/IP矽智財",
        "矽智財IP",
        "HBM",
        "HBM 高頻寬記憶體",
        "CoWoS",
        "CoWoS先進封裝",
        "AI伺服器",
        "AI人工智慧",
        "輝達概念股",
        "AI PC",
        "光通訊",
        "光通訊/CPO",
        "矽光子",
        "記憶體",
        "軍工/國防",
        "無人機",
        "機器人",
        "低軌衛星",
        "特用化學",
        "特用化學/光阻劑",
        "重電",
        "HVDC/直流電力",
        "電源供應器/BBU",
        "PCB/銅箔基板",
        "玻璃基板 E-Core Sys.",
    ],
}

ALIASES = {
    "AI伺服器": ["AI人工智慧", "GB200", "GB300", "輝達概念股"],
    "輝達概念股": ["GB200", "GB300", "AI人工智慧"],
    "Google TPU": ["TPU"],
    "ASIC/IP矽智財": ["ASIC", "矽智財IP"],
    "光通訊/CPO": ["光通訊"],
    "低軌衛星": ["衛星/低軌衛星"],
    "機器人": ["智慧型機器人/機械手臂"],
    "軍工/國防": ["軍工/國防"],
    "PCB/銅箔基板": ["PCB", "銅箔基板", "PCB材料", "銅箔"],
    "電源供應器/BBU": ["電源供應器", "BBU"],
    "HBM 高頻寬記憶體": ["HBM", "記憶體"],
    "CoWoS先進封裝": ["CoWoS"],
    "AI PC/邊緣AI": ["AI PC"],
    "特用化學/光阻劑": ["特用化學"],
    "碳權/ESG": ["碳權"],
    "氫能/燃料電池": ["氫燃料電池"],
    "水資源/環保": ["水資源", "環境工程"],
}

TRUSTED_SEARCH_DOMAINS = (
    "moneydj.com",
    "cnyes.com",
    "money.udn.com",
    "ctee.com.tw",
    "technews.tw",
    "bnext.com.tw",
    "tw.stock.yahoo.com",
    "statementdog.com",
    "goodinfo.tw",
    "cmoney.tw",
)


@dataclass(frozen=True)
class ConceptLink:
    name: str
    url: str


def normalize_name(text: str) -> str:
    text = (text or "").strip().upper()
    text = text.replace("（", "(").replace("）", ")")
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"[概念股股票族群題材]", "", text)
    text = text.replace("/", "").replace("-", "")
    return text


def safe_filename(name: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name.strip())
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    return cleaned[:80] or "未命名概念"


def read_name_map() -> dict[str, str]:
    path = ROOT / "site" / ".cache_meta.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {str(k): str(v) for k, v in data.get("name_map", {}).items()}
    except Exception:
        return {}


def load_local_groups() -> dict[str, list[str]]:
    sys.path.insert(0, str(ROOT))
    try:
        from concept_groups import CONCEPT_GROUPS  # type: ignore

        return {str(k): [str(v) for v in values] for k, values in CONCEPT_GROUPS.items()}
    except Exception as exc:
        print(f"[warn] 無法載入 concept_groups.py：{exc}")
        return {}


def fetch_html(
    session: requests.Session,
    url: str,
    cache_path: Path,
    delay: float,
    refresh: bool = False,
) -> str:
    if cache_path.exists() and not refresh:
        return cache_path.read_text(encoding="utf-8", errors="ignore")

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    time.sleep(max(delay, 0))
    response = session.get(url, headers=HEADERS, timeout=25, verify=False)
    response.raise_for_status()
    response.encoding = response.encoding or "utf-8"
    html = response.text
    cache_path.write_text(html, encoding="utf-8")
    return html


def crawl_cmoney_index(
    session: requests.Session,
    delay: float,
    refresh: bool = False,
) -> list[ConceptLink]:
    html = fetch_html(session, CMONEY_INDEX, CACHE_DIR / "index.html", delay, refresh)
    soup = BeautifulSoup(html, "lxml")
    links: list[ConceptLink] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"]
        name = " ".join(anchor.get_text(" ", strip=True).split())
        if not name or not re.fullmatch(r"/forum/concept/C\d+", href):
            continue
        url = urljoin("https://www.cmoney.tw", href)
        key = f"{name}|{url}"
        if key in seen:
            continue
        seen.add(key)
        links.append(ConceptLink(name=name, url=url))
    return links


def parse_stock_name(raw_text: str, stock_id: str, name_map: dict[str, str]) -> str:
    text = " ".join(raw_text.split())
    text = re.sub(rf"^\s*{re.escape(stock_id)}\s*", "", text)
    text = re.sub(rf"\(?{re.escape(stock_id)}\)?", "", text).strip()
    text = re.sub(r"[+\-]\d+(\.\d+)?\s*%.*$", "", text).strip()
    return text or name_map.get(stock_id, "")


def has_table_ancestor(anchor) -> bool:
    parent = anchor
    for _ in range(8):
        parent = parent.parent
        if parent is None:
            return False
        classes = parent.get("class") or []
        if "table__plural--active" in classes:
            return True
        if "nav__container" in classes or "articleTags" in classes or "list" in classes:
            return False
    return False


def crawl_cmoney_detail(
    session: requests.Session,
    concept: ConceptLink,
    name_map: dict[str, str],
    delay: float,
    refresh: bool = False,
) -> list[dict[str, str]]:
    code = concept.url.rstrip("/").split("/")[-1]
    html = fetch_html(session, concept.url, CACHE_DIR / f"{code}.html", delay, refresh)
    soup = BeautifulSoup(html, "lxml")
    title = soup.title.get_text(strip=True) if soup.title else concept.name
    rows: list[dict[str, str]] = []
    seen: set[str] = set()

    for anchor in soup.find_all("a", href=True):
        href = anchor["href"]
        match = re.fullmatch(r"/forum/stock/(\d{4})", href)
        if not match or not has_table_ancestor(anchor):
            continue
        stock_id = match.group(1)
        if stock_id in seen:
            continue
        seen.add(stock_id)
        stock_name = parse_stock_name(anchor.get_text(" ", strip=True), stock_id, name_map)
        rows.append(
            {
                "stock_id": stock_id,
                "stock_name": stock_name,
                "source_platform": "CMoney",
                "source_type": "concept_detail",
                "source_url": concept.url,
                "source_title": title,
                "matched_by": "cmoney_detail_table",
                "confidence": "high",
                "evidence_text": f"CMoney 概念頁「{concept.name}」成分股表格",
                "notes": "",
            }
        )
    return rows


def make_indexes(
    cmoney_links: Iterable[ConceptLink],
    local_groups: dict[str, list[str]],
) -> tuple[dict[str, ConceptLink], dict[str, str]]:
    cmoney_index: dict[str, ConceptLink] = {}
    for link in cmoney_links:
        cmoney_index.setdefault(normalize_name(link.name), link)
    local_index = {normalize_name(name): name for name in local_groups}
    return cmoney_index, local_index


def concept_candidates(concept_name: str) -> list[str]:
    candidates = [concept_name]
    candidates.extend(ALIASES.get(concept_name, []))
    for key, values in ALIASES.items():
        if concept_name in values:
            candidates.append(key)
    out: list[str] = []
    for name in candidates:
        if name not in out:
            out.append(name)
    return out


def find_cmoney_link(
    concept_name: str,
    cmoney_index: dict[str, ConceptLink],
) -> tuple[ConceptLink | None, str]:
    for candidate in concept_candidates(concept_name):
        key = normalize_name(candidate)
        if key in cmoney_index:
            return cmoney_index[key], "cmoney_exact_or_alias"
    target = normalize_name(concept_name)
    for key, link in cmoney_index.items():
        if target and (target in key or key in target):
            return link, "cmoney_fuzzy"
    return None, ""


def find_local_group(
    concept_name: str,
    local_groups: dict[str, list[str]],
    local_index: dict[str, str],
) -> tuple[str | None, list[str], str]:
    for candidate in concept_candidates(concept_name):
        key = normalize_name(candidate)
        if key in local_index:
            name = local_index[key]
            return name, local_groups.get(name, []), "local_exact_or_alias"
    target = normalize_name(concept_name)
    for key, name in local_index.items():
        if target and (target in key or key in target):
            return name, local_groups.get(name, []), "local_fuzzy"
    return None, [], ""


def rows_from_local_group(
    group_name: str,
    stocks: list[str],
    name_map: dict[str, str],
    matched_by: str,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for stock_id in stocks:
        if not re.fullmatch(r"\d{4}", stock_id):
            continue
        rows.append(
            {
                "stock_id": stock_id,
                "stock_name": name_map.get(stock_id, ""),
                "source_platform": "local_concept_groups",
                "source_type": "project_taxonomy",
                "source_url": str(ROOT / "concept_groups.py"),
                "source_title": f"本機 concept_groups.py：{group_name}",
                "matched_by": matched_by,
                "confidence": "medium",
                "evidence_text": f"本專案既有族群字典「{group_name}」",
                "notes": "不是外部網頁即時爬取；用於補 CMoney 未收錄或名稱不一致的概念",
            }
        )
    return rows


def decode_ddg_url(url: str) -> str:
    if url.startswith("//"):
        url = "https:" + url
    parsed = urlparse(url)
    if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
        qs = parse_qs(parsed.query)
        if qs.get("uddg"):
            return unquote(qs["uddg"][0])
    return url


def domain_rank(url: str) -> int:
    host = urlparse(url).netloc.lower()
    for idx, domain in enumerate(TRUSTED_SEARCH_DOMAINS):
        if domain in host:
            return idx
    return len(TRUSTED_SEARCH_DOMAINS) + 1


def source_platform_from_url(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if "moneydj.com" in host:
        return "MoneyDJ"
    if "cnyes.com" in host:
        return "Anue鉅亨"
    if "money.udn.com" in host:
        return "經濟日報"
    if "ctee.com.tw" in host:
        return "工商時報"
    if "technews.tw" in host:
        return "科技新報"
    if "bnext.com.tw" in host:
        return "數位時代"
    if "yahoo.com" in host:
        return "Yahoo股市"
    if "statementdog.com" in host:
        return "財報狗"
    if "goodinfo.tw" in host:
        return "Goodinfo"
    if "cmoney.tw" in host:
        return "CMoney"
    return host or ""


def search_theme_source(
    session: requests.Session,
    year: int,
    concept_name: str,
    delay: float,
    refresh: bool = False,
) -> dict[str, str]:
    query = f"{year} 台股 {concept_name} 概念股"
    cache_name = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "_", query)[:120]
    cache_path = ROOT / "data" / ".cache" / "theme_search" / f"{cache_name}.html"
    url = "https://html.duckduckgo.com/html/?q=" + quote_plus(query) + "&kl=tw-tzh"

    try:
        html = fetch_html(session, url, cache_path, delay, refresh)
    except Exception as exc:
        return {
            "theme_source_title": "",
            "theme_source_url": "",
            "theme_source_platform": "",
            "theme_source_query": query,
            "theme_source_note": f"search_failed: {exc}",
        }

    soup = BeautifulSoup(html, "lxml")
    hits: list[dict[str, str]] = []
    for result in soup.select(".result"):
        anchor = result.select_one(".result__a")
        snippet = result.select_one(".result__snippet")
        if not anchor:
            continue
        hit_url = decode_ddg_url(anchor.get("href", ""))
        title = " ".join(anchor.get_text(" ", strip=True).split())
        text = " ".join(snippet.get_text(" ", strip=True).split()) if snippet else ""
        if not hit_url or not title:
            continue
        hits.append(
            {
                "theme_source_title": title,
                "theme_source_url": hit_url,
                "theme_source_platform": source_platform_from_url(hit_url),
                "theme_source_query": query,
                "theme_source_note": text[:180],
            }
        )

    if not hits:
        return {
            "theme_source_title": "",
            "theme_source_url": "",
            "theme_source_platform": "",
            "theme_source_query": query,
            "theme_source_note": "no_search_result",
        }

    hits.sort(key=lambda hit: domain_rank(hit["theme_source_url"]))
    return hits[0]


def build_concept_rows(
    session: requests.Session,
    concept_name: str,
    folder_year: int,
    cmoney_index: dict[str, ConceptLink],
    local_groups: dict[str, list[str]],
    local_index: dict[str, str],
    name_map: dict[str, str],
    delay: float,
    refresh: bool,
    discover_sources: bool,
) -> list[dict[str, str]]:
    theme_source = {
        "theme_source_title": "",
        "theme_source_url": "",
        "theme_source_platform": "",
        "theme_source_query": "",
        "theme_source_note": "",
    }
    if discover_sources:
        theme_source = search_theme_source(session, folder_year, concept_name, delay, refresh)

    cmoney_link, cmoney_match = find_cmoney_link(concept_name, cmoney_index)
    rows: list[dict[str, str]] = []
    resolved_concept = concept_name

    if cmoney_link:
        resolved_concept = cmoney_link.name
        rows = crawl_cmoney_detail(session, cmoney_link, name_map, delay, refresh)
        if cmoney_match == "cmoney_fuzzy":
            for row in rows:
                row["matched_by"] = "cmoney_fuzzy"
                row["confidence"] = "medium"
                row["notes"] = f"使用「{concept_name}」模糊匹配到 CMoney「{cmoney_link.name}」"

    if not rows:
        local_name, stocks, matched_by = find_local_group(concept_name, local_groups, local_index)
        if local_name and stocks:
            resolved_concept = local_name
            rows = rows_from_local_group(local_name, stocks, name_map, matched_by)

    output: list[dict[str, str]] = []
    for row in rows:
        normalized = normalize_name(resolved_concept)
        source_year = str(datetime.now().year) if row["source_platform"] == "CMoney" else ""
        notes = row.get("notes", "")
        if theme_source.get("theme_source_note"):
            notes = (notes + "；" if notes else "") + theme_source["theme_source_note"]
        output.append(
            {
                **{field: "" for field in CSV_FIELDS},
                **row,
                "concept_name": resolved_concept,
                "normalized_concept_name": normalized,
                "folder_year": str(folder_year),
                "source_year": source_year,
                "inferred_theme_year": str(folder_year),
                "theme_source_title": theme_source.get("theme_source_title", ""),
                "theme_source_url": theme_source.get("theme_source_url", ""),
                "theme_source_platform": theme_source.get("theme_source_platform", ""),
                "crawl_date": CRAWL_DATE,
                "notes": notes,
            }
        )
    return output


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def dedupe_rows(rows: Iterable[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str, str, str, str]] = set()
    out: list[dict[str, str]] = []
    for row in rows:
        key = (
            row.get("folder_year", ""),
            row.get("normalized_concept_name", ""),
            row.get("stock_id", ""),
            row.get("source_url", ""),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def iter_year_concepts(
    start_year: int,
    end_year: int,
    cmoney_links: list[ConceptLink],
    include_all_cmoney_current_year: bool,
) -> dict[int, list[str]]:
    selected: dict[int, list[str]] = {}
    for year in range(start_year, end_year + 1):
        concepts = list(YEAR_CONCEPT_SEEDS.get(year, []))
        if include_all_cmoney_current_year and year == end_year:
            concepts.extend(link.name for link in cmoney_links)
        deduped: list[str] = []
        for concept in concepts:
            if concept not in deduped:
                deduped.append(concept)
        selected[year] = deduped
    return selected


def main() -> int:
    parser = argparse.ArgumentParser(
        description="依年份資料夾輸出台股概念股 CSV，一個概念一個 CSV。"
    )
    parser.add_argument("--start-year", type=int, default=2020)
    parser.add_argument("--end-year", type=int, default=datetime.now().year)
    parser.add_argument("--output", type=Path, default=OUT_ROOT)
    parser.add_argument("--delay", type=float, default=0.25, help="每次網路請求間隔秒數")
    parser.add_argument("--refresh-cache", action="store_true")
    parser.add_argument(
        "--discover-sources",
        action="store_true",
        help="用 DuckDuckGo HTML 搜尋每個年份/概念的佐證來源，較慢",
    )
    parser.add_argument(
        "--all-cmoney-current-year",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="將 CMoney 目前總覽全部概念放進 end-year 資料夾",
    )
    parser.add_argument("--limit-concepts", type=int, default=0, help="除錯用，只跑每年 N 個概念")
    args = parser.parse_args()
    args.output = args.output if args.output.is_absolute() else ROOT / args.output
    args.output = args.output.resolve()

    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    session = requests.Session()
    name_map = read_name_map()
    local_groups = load_local_groups()

    print("[info] 抓取 CMoney 概念總覽")
    cmoney_links = crawl_cmoney_index(session, args.delay, args.refresh_cache)
    cmoney_index, local_index = make_indexes(cmoney_links, local_groups)
    print(f"[info] CMoney 概念數：{len(cmoney_links)}；本機族群數：{len(local_groups)}")

    year_concepts = iter_year_concepts(
        args.start_year,
        args.end_year,
        cmoney_links,
        args.all_cmoney_current_year,
    )

    all_rows: list[dict[str, str]] = []
    manifest_rows: list[dict[str, str]] = []
    written_concepts: set[tuple[int, str]] = set()

    for year, concepts in year_concepts.items():
        if args.limit_concepts:
            concepts = concepts[: args.limit_concepts]
        print(f"[info] {year}: 概念 {len(concepts)} 個")
        for idx, concept_name in enumerate(concepts, 1):
            print(f"  - ({idx}/{len(concepts)}) {concept_name}")
            rows = build_concept_rows(
                session=session,
                concept_name=concept_name,
                folder_year=year,
                cmoney_index=cmoney_index,
                local_groups=local_groups,
                local_index=local_index,
                name_map=name_map,
                delay=args.delay,
                refresh=args.refresh_cache,
                discover_sources=args.discover_sources,
            )
            rows = dedupe_rows(rows)
            if not rows:
                manifest_rows.append(
                    {
                        "year": str(year),
                        "concept_name": concept_name,
                        "file": "",
                        "stock_count": "0",
                        "status": "no_match",
                        "source_platforms": "",
                        "theme_source_platform": "",
                        "theme_source_title": "",
                        "theme_source_url": "",
                    }
                )
                continue

            concept_for_file = rows[0]["concept_name"]
            concept_key = (year, rows[0]["normalized_concept_name"])
            if concept_key in written_concepts:
                continue
            written_concepts.add(concept_key)

            file_path = args.output / str(year) / f"{safe_filename(concept_for_file)}.csv"
            write_csv(file_path, rows)
            all_rows.extend(rows)
            manifest_rows.append(
                {
                    "year": str(year),
                    "concept_name": concept_for_file,
                    "file": str(file_path.relative_to(ROOT)),
                    "stock_count": str(len(rows)),
                    "status": "ok",
                    "source_platforms": ",".join(sorted({row["source_platform"] for row in rows})),
                    "theme_source_platform": rows[0].get("theme_source_platform", ""),
                    "theme_source_title": rows[0].get("theme_source_title", ""),
                    "theme_source_url": rows[0].get("theme_source_url", ""),
                }
            )

    args.output.mkdir(parents=True, exist_ok=True)
    all_rows = dedupe_rows(all_rows)
    write_csv(args.output / "all_concept_stocks_2020_2026.csv", all_rows)

    with (args.output / "manifest.csv").open("w", newline="", encoding="utf-8-sig") as f:
        fields = [
            "year",
            "concept_name",
            "file",
            "stock_count",
            "status",
            "source_platforms",
            "theme_source_platform",
            "theme_source_title",
            "theme_source_url",
        ]
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(manifest_rows)

    print(f"[done] 輸出資料夾：{args.output}")
    print(f"[done] CSV 總列數：{len(all_rows)}")
    print(f"[done] manifest：{args.output / 'manifest.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
