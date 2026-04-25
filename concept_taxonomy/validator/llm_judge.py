"""
LLM 仲裁（邊界 0.50–0.70 + Coverage 缺失 + 證據衝突）。

設計同 web_search：「外部 populate / 內部讀取」雙階段。
Pipeline 偵測到邊界 case 時，主對話可呼叫 anthropic SDK 或 Claude Code 內建模型
產生判決，寫進 LLMJudgeCache；validator 跑時從快取讀。

API：
    cache = LLMJudgeCache()
    prompt = build_prompt(profile, spec, evidence)
    cached = cache.lookup(prompt)
    if not cached:
        # 主對話補上 judgement
        cache.populate(prompt, judgement)
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

CACHE_PATH = Path(__file__).resolve().parent / "cache" / "llm_cache.sqlite"
CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)


# ─────────────────────────────────────────────────────────────────────────────
# Prompt 模板
# ─────────────────────────────────────────────────────────────────────────────
PROMPT_TEMPLATE = """\
你是台股產業分析師。判定個股 {ticker} {name} 對「{group_name}」族群的關係。

## 證據
[Coverage 業務簡介摘錄]
{coverage_excerpt}

[finlab 產業類別]
{twse_industry}

[Web 最近 3 個月片段]
{web_snippets}

## 族群規格
- 產業板塊（必須屬一個）：{allowed_segments}
- 允許供應鏈位階：{allowed_positions}
- 必要題材（至少含一個）：{required_themes_any}
- 禁忌位階：{forbidden_positions}
- 禁忌題材：{forbidden_themes}

## 反模式（嚴禁）
- 不可把物理元件（如連接器）標成抽象技術（如「高速傳輸」）
- core_themes 必須是 30+ enum 之一，禁用「AI / 半導體 / 高速傳輸」這類抽象詞

## 任務
依嚴謹的三維分類體系，輸出 JSON：

{{
  "supply_chain_position": "<27 enum 之一>",
  "core_themes": ["<theme1>", "<theme2>"],
  "verdict": "core | satellite | remove",
  "confidence": <0.0-1.0>,
  "rationale": "一句話",
  "key_evidence_quote": "..."
}}
"""


def build_prompt(
    ticker: str,
    name: str,
    group_name: str,
    spec: dict,
    coverage_excerpt: str = "",
    twse_industry: str = "",
    web_snippets: str = "",
) -> str:
    return PROMPT_TEMPLATE.format(
        ticker=ticker,
        name=name,
        group_name=group_name,
        coverage_excerpt=coverage_excerpt or "(無 Coverage 資料)",
        twse_industry=twse_industry or "(查無)",
        web_snippets=web_snippets or "(無近期新聞)",
        allowed_segments=spec.get("allowed_segments", []),
        allowed_positions=spec.get("allowed_positions", []),
        required_themes_any=spec.get("required_themes_any", []),
        forbidden_positions=spec.get("forbidden_positions", []),
        forbidden_themes=spec.get("forbidden_themes", []),
    )


def _prompt_hash(prompt: str) -> str:
    return hashlib.sha256(prompt.encode()).hexdigest()[:16]


class LLMJudgeCache:
    """永久快取，key = sha256(prompt)。"""

    def __init__(self, path: Path = CACHE_PATH):
        self.path = path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS llm_judgements (
                    phash TEXT PRIMARY KEY,
                    ticker TEXT,
                    group_name TEXT,
                    prompt TEXT NOT NULL,
                    judgement_json TEXT NOT NULL,
                    populated_at TEXT NOT NULL
                )
            """)

    def populate(self, prompt: str, judgement: dict, ticker: str = "", group_name: str = ""):
        phash = _prompt_hash(prompt)
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO llm_judgements (phash, ticker, group_name, prompt, judgement_json, populated_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (phash, ticker, group_name, prompt, json.dumps(judgement, ensure_ascii=False), now),
            )

    def lookup(self, prompt: str) -> Optional[dict]:
        phash = _prompt_hash(prompt)
        with sqlite3.connect(self.path) as conn:
            row = conn.execute(
                "SELECT judgement_json FROM llm_judgements WHERE phash = ?",
                (phash,),
            ).fetchone()
        return json.loads(row[0]) if row else None

    def stats(self) -> dict:
        with sqlite3.connect(self.path) as conn:
            n = conn.execute("SELECT COUNT(*) FROM llm_judgements").fetchone()[0]
        return {"entries": n, "path": str(self.path)}


def parse_judgement(text: str) -> Optional[dict]:
    """LLM 回傳的可能是純 JSON 或夾在 markdown code block。容錯解析。"""
    import re
    # 找 ```json...``` 或純 JSON
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        text = m.group(1)
    else:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            text = m.group(0)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None
