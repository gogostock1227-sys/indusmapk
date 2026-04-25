"""
Web 搜尋封裝（WebSearch + WebFetch + sqlite 快取）。

設計：Python 模組無法直接呼叫 Claude Code 內建 WebSearch / WebFetch 工具，
因此採用「外部 populate / 內部讀取」雙階段：

  - 外部 populate：執行階段由 Claude Code 主對話呼叫 WebSearch/WebFetch，
    把結果以 `web_search.populate(query, results)` 寫進 sqlite 快取
  - 內部讀取：validator pipeline 跑 `WebCache.lookup(query)` 從快取取結果；
    沒命中則回 None，由 caller 決定是否觸發 LLM 回退

API：
    cache = WebCache()
    cache.populate("嘉澤 法說會 2026Q1", results=[{...}])
    hits = cache.lookup("嘉澤 法說會 2026Q1")
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

CACHE_PATH = Path(__file__).resolve().parent / "cache" / "web_cache.sqlite"
CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
TTL_DAYS = 7


def _query_hash(query: str, date_bucket: str = "") -> str:
    raw = f"{query}|{date_bucket or datetime.now(timezone.utc).strftime('%Y-%m-%d')}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


class WebCache:
    """Sqlite 快取，key = sha256(query + date_bucket)，TTL 7 天。"""

    def __init__(self, path: Path = CACHE_PATH):
        self.path = path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS web_results (
                    qhash TEXT PRIMARY KEY,
                    query TEXT NOT NULL,
                    date_bucket TEXT NOT NULL,
                    results_json TEXT NOT NULL,
                    populated_at TEXT NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_query ON web_results(query)")

    def populate(self, query: str, results: list[dict], date_bucket: str = ""):
        """寫入或覆蓋。results 標準格式：[{'url','title','snippet','published'}]。"""
        bucket = date_bucket or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        qhash = _query_hash(query, bucket)
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO web_results (qhash, query, date_bucket, results_json, populated_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (qhash, query, bucket, json.dumps(results, ensure_ascii=False), now),
            )

    def lookup(self, query: str, date_bucket: str = "") -> Optional[list[dict]]:
        """命中回 list；未命中 / 過期回 None。"""
        bucket = date_bucket or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        qhash = _query_hash(query, bucket)
        with sqlite3.connect(self.path) as conn:
            row = conn.execute(
                "SELECT results_json, populated_at FROM web_results WHERE qhash = ?",
                (qhash,),
            ).fetchone()
        if not row:
            return None
        results_json, populated_at = row
        # TTL 檢查
        try:
            populated_dt = datetime.fromisoformat(populated_at)
            if (datetime.now(timezone.utc) - populated_dt).days > TTL_DAYS:
                return None
        except Exception:
            pass
        return json.loads(results_json)

    def stats(self) -> dict:
        with sqlite3.connect(self.path) as conn:
            n = conn.execute("SELECT COUNT(*) FROM web_results").fetchone()[0]
        return {"entries": n, "path": str(self.path)}


# ─────────────────────────────────────────────────────────────────────────────
# 標準 query 模板
# ─────────────────────────────────────────────────────────────────────────────
QUERY_TEMPLATES = {
    "ir":      "{ticker} {name} 法說會 {year}",
    "supply":  "{name} 供應鏈 客戶 {theme}",
    "ir_en":   "{name} investor day {year}",
    "negative": "{name} {forbidden_keyword}",
}


def build_query(template_key: str, **kwargs) -> str:
    """格式化 query。kwargs 缺值用 ''。"""
    template = QUERY_TEMPLATES[template_key]
    safe_kwargs = {k: kwargs.get(k, "") for k in ("ticker", "name", "year", "theme", "forbidden_keyword")}
    return template.format(**safe_kwargs).strip()
