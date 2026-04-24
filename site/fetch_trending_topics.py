"""
抓取當日熱門題材
================

邏輯（每日自動更新，取代 index.html 寫死的 6 個熱門題材）:

  1. 爬 Yahoo 股市排行榜（成交金額 / 成交量 / 漲幅）→ 當日熱股清單
  2. 用 CONCEPT_GROUPS 做「股 → 題材」反查投票，排行越前權重越高
  3. 爬鉅亨網新聞標題關鍵字，對命中題材做語意加權
  4. 輸出 site/.cache_trending.json，供 build_site.py 讀取

失敗降級：
  - 任一來源失敗不中斷，只印警告
  - 若全部失敗但 cache 存在 → 保留前次資料
  - 若完全沒 cache → build_site.py 端再 fallback 到預設題材

用法:
  python site/fetch_trending_topics.py            # 預設
  python site/fetch_trending_topics.py --top 8    # 取 top 8 題材
  python site/fetch_trending_topics.py --dry-run  # 只印不寫檔
"""
from __future__ import annotations
import argparse
import json
import re
import ssl
import sys
import urllib.request
from collections import Counter
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = HERE / ".cache_trending.json"

sys.path.insert(0, str(ROOT))
from concept_groups import CONCEPT_GROUPS  # noqa: E402


_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/123.0.0.0 Safari/537.36"
)

# Yahoo 股市排行（實測 2026/04 可用）
YAHOO_SOURCES = [
    ("turnover", "https://tw.stock.yahoo.com/rank/turnover"),  # 成交金額
    ("volume",   "https://tw.stock.yahoo.com/rank/volume"),    # 成交量
]

CNYES_URL = "https://news.cnyes.com/news/cat/tw_stock_news"

# 鉅亨/市場常用關鍵字 → 本站題材（語意加權映射）
# 題材名稱必須精確匹配 CONCEPT_GROUPS 的 key
KEYWORD_TO_TOPICS = {
    "CPO":        ["矽光子"],
    "矽光子":     ["矽光子"],
    "光通訊":     ["矽光子"],
    "記憶體":     ["記憶體"],
    "DRAM":       ["記憶體", "DDR5/LPDDR5 記憶體"],
    "DDR5":       ["DDR5/LPDDR5 記憶體"],
    "HBM":        ["HBM 高頻寬記憶體", "CoWoS先進封裝"],
    "NAND":       ["記憶體"],
    "量子":       ["量子電腦"],
    "2奈米":      ["2奈米先進製程"],
    "先進封裝":   ["CoWoS先進封裝"],
    "CoWoS":      ["CoWoS先進封裝"],
    "Chiplet":    ["Chiplet 小晶片"],
    "ABF":        ["ABF載板"],
    "載板":       ["ABF載板"],
    "PCB":        ["高階 PCB/HDI", "PCB/銅箔基板"],
    "銅箔基板":   ["PCB/銅箔基板"],
    "CCL":        ["PCB/銅箔基板"],
    "散熱":       ["散熱/液冷"],
    "液冷":       ["散熱/液冷"],
    "機器人":     ["機器人"],
    "人形":       ["機器人"],
    "AI 伺服器":  ["AI伺服器"],
    "AI伺服器":   ["AI伺服器"],
    "GB300":      ["AI伺服器", "輝達概念股"],
    "GB200":      ["AI伺服器", "輝達概念股"],
    "Rubin":      ["輝達概念股"],
    "TPU":        ["Google TPU"],
    "ASIC":       ["ASIC/IP矽智財"],
    "電動車":     ["電動車"],
    "低軌衛星":   ["低軌衛星"],
    "Starlink":   ["低軌衛星"],
    "被動元件":   ["被動元件"],
    "軍工":       ["軍工/國防"],
    "國防":       ["軍工/國防"],
    "生技":       ["生技醫療"],
    "GLP-1":      ["減重新藥/GLP-1"],
    "減重":       ["減重新藥/GLP-1"],
    "減肥":       ["減重新藥/GLP-1"],
}


# ═══════════════════════════════════════════
#   工具
# ═══════════════════════════════════════════

def _fetch(url: str, timeout: int = 20) -> str:
    """抓 HTML，失敗回空字串（不 raise，讓外層降級）。"""
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": _UA,
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX) as r:
            raw = r.read()
            # Yahoo 用 UTF-8，鉅亨也是，統一 decode
            return raw.decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"[warn] fetch {url}: {e}")
        return ""


def build_reverse_map() -> dict:
    """每檔股 → 所屬題材 list（來自本站 CONCEPT_GROUPS）。"""
    rev: dict = {}
    for topic, members in CONCEPT_GROUPS.items():
        for sym in members:
            rev.setdefault(sym, []).append(topic)
    return rev


def validate_keyword_map() -> list[str]:
    """校驗 KEYWORD_TO_TOPICS 的 topic 全部存在於 CONCEPT_GROUPS。
    回傳不合法的 topic 列表（若有），呼叫端自行決定要警告還是中斷。"""
    known = set(CONCEPT_GROUPS.keys())
    missing: list[str] = []
    for _, topics in KEYWORD_TO_TOPICS.items():
        for t in topics:
            if t not in known and t not in missing:
                missing.append(t)
    return missing


def extract_yahoo_symbols(html: str, limit: int = 30) -> list[str]:
    """從 Yahoo 排行頁 HTML 抽出個股代號（過濾 ETF / 複委託）。

    Yahoo 的 quote 連結格式：/quote/2330.TW、/quote/3105.TWO、/quote/00631L.TW
    個股：4 位數字
    ETF：00 開頭 5-6 位（含英文字母後綴如 L/R/K）
    """
    pat = re.compile(r'/quote/(\d{4,6}[A-Z]?)\.(TW|TWO)')
    seen: set = set()
    out: list[str] = []
    for m in pat.finditer(html):
        sym = m.group(1)
        # 過濾條件：
        #   只留 4 位純數字（個股）
        #   ETF 通常 5-6 位或帶字母後綴，排除
        if len(sym) != 4 or not sym.isdigit():
            continue
        if sym in seen:
            continue
        seen.add(sym)
        out.append(sym)
        if len(out) >= limit:
            break
    return out


def vote_from_symbols(
    symbols: list[str],
    reverse_map: dict,
    rank_weight_decay: float = 0.03,
) -> Counter:
    """熱股反查題材投票：排行第 i（0-based）權重 = max(1.0, 2.0 - i*0.03)。

    例：rank 1 → 2.0，rank 10 → 1.7，rank 30 → 1.1。
    """
    counter: Counter = Counter()
    for i, sym in enumerate(symbols):
        weight = max(1.0, 2.0 - i * rank_weight_decay)
        for topic in reverse_map.get(sym, []):
            counter[topic] += weight
    return counter


def vote_from_keywords(html: str, per_hit: float = 2.0) -> Counter:
    """從新聞 HTML 抓關鍵字，每命中一次對應題材 +per_hit 分。

    權重設計哲學：
      個股熱度是主旋律（最高約 15 分），關鍵字只做語意微調。
      單關鍵字對單題最多 +4 分（per_hit=2.0 * min(hits,2)）。
    """
    counter: Counter = Counter()
    if not html:
        return counter
    # 粗暴 strip tag，保留純文字
    text = re.sub(r"<[^>]+>", " ", html)
    # 只驗證「不在 CONCEPT_GROUPS 的 topic」有校準問題時才篩掉
    # （此處假設呼叫端已保證 KEYWORD_TO_TOPICS 的 topic 全部存在）
    for kw, topics in KEYWORD_TO_TOPICS.items():
        hits = text.count(kw)
        if hits <= 0:
            continue
        bump = per_hit * min(hits, 2)  # 單關鍵字最多 2 次加權
        for topic in topics:
            counter[topic] += bump
    return counter


def load_prev_cache() -> dict | None:
    if not OUT.exists():
        return None
    try:
        return json.loads(OUT.read_text(encoding="utf-8"))
    except Exception:
        return None


# ═══════════════════════════════════════════
#   主流程
# ═══════════════════════════════════════════

def fetch_trending(top_n: int = 8, debug: bool = False) -> dict:
    """抓當日熱門題材，回傳 dict。"""
    # Step 0: 啟動校驗 KEYWORD map
    missing = validate_keyword_map()
    if missing:
        print(f"[warn] KEYWORD_TO_TOPICS 有 {len(missing)} 個 topic 不在 CONCEPT_GROUPS:")
        for t in missing:
            print(f"       - {t!r}")
        print("       （這些關鍵字的加權會失效，但不中斷）")

    # Step 1: Yahoo 熱股
    hot_symbols: list[str] = []
    per_source_symbols: dict = {}
    for tag, url in YAHOO_SOURCES:
        html = _fetch(url)
        syms = extract_yahoo_symbols(html, limit=30)
        per_source_symbols[tag] = syms
        if debug:
            print(f"[yahoo:{tag}] {len(syms)} 檔 → {syms[:10]}")
        # 合併（首次出現保序，排名高的權重就高）
        for s in syms:
            if s not in hot_symbols:
                hot_symbols.append(s)

    if not hot_symbols:
        prev = load_prev_cache()
        if prev:
            print("[降級] Yahoo 全部失敗，沿用前次 cache")
            return prev
        raise RuntimeError("Yahoo 爬蟲全部失敗且無 cache")

    # Step 2: 反查投票
    rev = build_reverse_map()
    vote_stock = vote_from_symbols(hot_symbols, rev)

    # Step 3: 鉅亨關鍵字語意加權
    cnyes_html = _fetch(CNYES_URL)
    vote_kw = vote_from_keywords(cnyes_html)

    # Step 4: 合分
    merged: Counter = Counter()
    for k, v in vote_stock.items():
        merged[k] += v
    for k, v in vote_kw.items():
        merged[k] += v

    if debug:
        print(f"[投票] 股票投票 top 10: {vote_stock.most_common(10)}")
        print(f"[投票] 關鍵字加權: {vote_kw.most_common(10)}")
        print(f"[投票] 合併 top 10: {merged.most_common(10)}")

    ranked = merged.most_common(top_n)

    out = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source": {
            "yahoo": {k: len(v) for k, v in per_source_symbols.items()},
            "cnyes_bytes": len(cnyes_html),
        },
        "hot_symbols": hot_symbols[:50],
        "topics": [
            {"name": name, "score": round(score, 2)}
            for name, score in ranked
        ],
    }
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--top", type=int, default=8, help="取 top N 題材（預設 8）")
    ap.add_argument("--dry-run", action="store_true", help="只印不寫檔")
    ap.add_argument("--debug", action="store_true", help="列印投票細節")
    args = ap.parse_args()

    print(f"[fetch_trending] 抓取當日熱門題材 top {args.top}...")
    try:
        out = fetch_trending(top_n=args.top, debug=args.debug)
    except Exception as e:
        print(f"[error] {e}")
        sys.exit(1)

    print(f"\n[OK] 熱門題材 top {len(out['topics'])} @ {out['generated_at']}:")
    for i, t in enumerate(out["topics"], 1):
        print(f"  {i:>2}. {t['name']:<24} {t['score']:>5.1f}")

    if args.dry_run:
        print("\n[dry-run] 未寫入 cache")
        return

    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[寫入] {OUT}")


if __name__ == "__main__":
    main()
