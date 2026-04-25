"""
驗證系統的型別定義。

對應 _TAXONOMY_SCHEMA.md 的 13×27×30+ enum，並用 dataclass 嚴格保證三維完整性。
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional


# ─────────────────────────────────────────────────────────────────────────────
# Dim-1: 產業板塊 (對應 _TAXONOMY_SCHEMA.md L10-29)
# ─────────────────────────────────────────────────────────────────────────────
INDUSTRY_SEGMENTS = {
    "AI_SEMI": "AI / 半導體",
    "ELEC_COMP": "電子零組件",
    "NETCOM": "網通 / 通訊",
    "COMP_HW": "電腦及週邊",
    "POWER_GREEN": "電源 / 綠能",
    "EV_AUTO": "車用 / 電動車",
    "DEFENSE": "軍工 / 國防",
    "MED_BIO": "生技醫療",
    "FIN": "金融",
    "CONSUMER": "消費 / 民生",
    "MATERIALS": "塑化 / 原物料",
    "LOGISTICS": "航運 / 物流",
    "SOFTWARE": "軟體 / 服務",
}

# ─────────────────────────────────────────────────────────────────────────────
# Dim-2: 供應鏈位階 (對應 _TAXONOMY_SCHEMA.md L32-79)
# ─────────────────────────────────────────────────────────────────────────────
SUPPLY_CHAIN_POSITIONS = {
    # 半導體供應鏈 (14)
    "IP": "IP / 矽智財",
    "IC_DESIGN": "IC 設計 / Fabless",
    "ASIC_SVC": "ASIC 設計服務",
    "FOUNDRY": "晶圓代工",
    "IDM_DRAM": "DRAM 製造 / IDM",
    "IDM_NAND": "NAND Flash 製造",
    "OSAT_ADV": "先進封裝 (OSAT)",
    "OSAT_TRAD": "一般封測",
    "TEST_INTF": "測試介面 / 探針卡 / 測試座",
    "TEST_SVC": "測試代工",
    "EQUIP": "半導體設備",
    "MAT_WAFER": "矽晶圓 / 上游材料",
    "MAT_CHEM": "半導體化學品 / 特用氣體",
    "SUBSTRATE": "載板 / 基板",
    # 電子零組件 (6)
    "CONNECTOR": "連接器 / Socket",
    "PASSIVE": "被動元件",
    "PCB_HDI": "高階 PCB / HDI",
    "PCB_FPC": "軟板 FPC",
    "THERMAL": "散熱模組",
    "CHASSIS": "機構件 / 機殼",
    # 系統 / 應用 (4)
    "ODM_SYS": "系統組裝 / ODM",
    "BRAND": "品牌商 / OEM",
    "END_USER": "終端應用商",
    "DISTRIB": "通路 / 代理",
    # 電源 / 光通訊 / 其他 (4)
    "POWER_MOD": "電源模組 / BBU",
    "OPTIC_MOD": "光通訊模組",
    "OPTIC_COMP": "光通訊元件",
    "SVC_SAAS": "軟體 / SaaS",
}

# ─────────────────────────────────────────────────────────────────────────────
# Dim-3: 核心驅動題材 (對應 _TAXONOMY_SCHEMA.md L82-135)
# 完整 enum 集合，stock_profile.core_themes 必須是這個 set 的子集
# ─────────────────────────────────────────────────────────────────────────────
CORE_THEME_ENUMS = {
    # 記憶體類
    "HBM3E_HBM4", "DDR5_RISE", "NICHE_DRAM", "NAND_TIGHT", "aiDAPTIV", "SOCAMM2", "CUBE",
    # 先進封裝類
    "COWOS", "COWOP", "SOIC_3D", "FOPLP", "WOW",
    # AI 算力類
    "GB300_RUBIN", "ASIC_TRAINIUM", "ASIC_TPU", "ASIC_MTIA", "CSP_DEVERTICAL",
    # 光通訊 / 高速傳輸類
    "CPO_PHOTONIC", "OPTIC_800G_1.6T", "SERDES_224G", "VCSEL",
    # 系統 / 電源 / 散熱類
    "LIQUID_COOL", "HVDC_800V", "BBU",
    # 製程 / 材料類
    "N2_2NM", "N3_3NM", "EUV_RISE", "GLASS_GCS",
    # 測試類
    "AI_GPU_TEST", "HBM_TEST",
    # 其他熱門題材
    "EV_BATTERY", "LEO_SAT", "QUANTUM", "ROBOTICS", "MED_GLP1",
    # 新增（涵蓋更多族群）
    "WIFI7", "5G_6G", "CHIPLET", "ADAS", "CDMO_BIO", "GLP1_OBESITY",
    "DEFENSE_DRONE", "PETS_ECONOMY", "DATACENTER_POWER", "MILITARY_SAT",
}

# 使用者紅線：嚴禁混淆物理元件與抽象技術
# 這些「抽象詞」絕不可作為 core_themes
ABSTRACT_THEME_BLACKLIST = {
    "高速傳輸",        # 應拆為 SERDES_224G
    "AI",              # 過度抽象
    "半導體",          # 過度抽象
    "5G",              # 應為 5G_6G
    "電動車",          # 應為 EV_BATTERY 或 ADAS
    "智慧醫療",        # 應為 MED_GLP1 / CDMO_BIO
    "綠能",            # 應為 EV_BATTERY / DATACENTER_POWER
}


# ─────────────────────────────────────────────────────────────────────────────
# Verdict 分級
# ─────────────────────────────────────────────────────────────────────────────
class Verdict(str, Enum):
    CORE = "core"              # 三道全通 + 強題材交集 ≥ 2 + score ≥ 0.80
    SATELLITE = "satellite"    # 部分通過或下游應用商 (0.55 ≤ score < 0.80)
    REMOVE = "remove"          # 任一 hard_fail 或 score < 0.55


# ─────────────────────────────────────────────────────────────────────────────
# 資料結構
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class GroupSpec:
    """`group_specs.json` 中每群的規格。驅動驗證的真理來源。

    註：對於系統級族群（如 AI伺服器、輝達概念股），其成分股可橫跨多個產業板塊
    （COMP_HW + ELEC_COMP + POWER_GREEN）。因此 industry_segment 設為 list。
    對純粹半導體族群（如 HBM、CoWoS），list 通常只放一個 AI_SEMI。
    """
    group_name: str
    allowed_segments: list[str]                # INDUSTRY_SEGMENTS 子集 (1+ 個)
    allowed_positions: list[str]               # SUPPLY_CHAIN_POSITIONS 子集
    required_themes_any: list[str]             # CORE_THEME_ENUMS 子集; 交集 ≥ 1 才通過 C2
    required_themes_strong: list[str] = field(default_factory=list)  # 交集 ≥ 2 才升 core
    forbidden_positions: list[str] = field(default_factory=list)
    forbidden_themes: list[str] = field(default_factory=list)
    downstream_demote: list[str] = field(default_factory=list)       # 命中此位階自動降 satellite
    core_keywords: list[str] = field(default_factory=list)           # Coverage / Web 全文檢索 anchor
    exclusion_keywords: list[str] = field(default_factory=list)
    deprecated: bool = False
    deprecation_reason: str = ""
    merge_into: Optional[str] = None
    members_reclassify_to: list[str] = field(default_factory=list)
    owner_batch: str = ""
    rationale: str = ""

    @property
    def primary_segment(self) -> str:
        """list 第一項視為主要板塊（用於 C1 reason 顯示）。"""
        return self.allowed_segments[0] if self.allowed_segments else ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "GroupSpec":
        return cls(**d)


@dataclass
class CiteSource:
    """單一證據來源。"""
    type: str                  # "coverage" / "finlab" / "web"
    quote: str = ""            # 引用片段 ≤ 100 字
    path: str = ""             # 檔案路徑（coverage）
    section: str = ""          # 章節（coverage）
    url: str = ""              # URL（web）
    title: str = ""            # 標題（web）
    field: str = ""            # 欄位（finlab）
    value: str = ""            # 值（finlab）
    accessed: str = ""         # ISO 日期


@dataclass
class StockProfile:
    """`stock_profiles.json` 中每檔個股的三維畫像。跨族群複用。"""
    ticker: str
    name: str
    industry_segment: str                            # 13 enum 之一
    supply_chain_position: str                       # 27 enum 之一
    core_themes: list[str]                           # CORE_THEME_ENUMS 子集 (1-3 個)
    business_summary: str = ""
    twse_industry: str = ""                          # 來自 finlab 原始字串
    cite_sources: list[CiteSource] = field(default_factory=list)
    confidence: float = 0.0                          # 0-1
    last_validated: str = ""                         # ISO 日期
    human_reviewed: bool = False

    def is_complete(self) -> bool:
        """三維完整率 100% — 缺任一視為 fail。"""
        return bool(
            self.industry_segment
            and self.supply_chain_position
            and self.core_themes
        )

    def has_anti_pattern(self) -> tuple[bool, str]:
        """反模式零容忍：core_themes 不可含抽象詞；position 必須在 enum。"""
        for t in self.core_themes:
            if t in ABSTRACT_THEME_BLACKLIST:
                return True, f"core_themes 含抽象詞「{t}」（請拆為對應 enum）"
            if t not in CORE_THEME_ENUMS:
                return True, f"core_themes「{t}」不在 30+ enum 內"
        if self.supply_chain_position not in SUPPLY_CHAIN_POSITIONS:
            return True, f"supply_chain_position「{self.supply_chain_position}」不在 27 enum 內"
        if self.industry_segment not in INDUSTRY_SEGMENTS:
            return True, f"industry_segment「{self.industry_segment}」不在 13 enum 內"
        return False, ""


@dataclass
class CheckResult:
    """單一檢查的結果。"""
    name: str                   # "C1_industry" / "C2_themes" / "C3_position"
    ok: bool
    weight: float
    reason: str = ""
    hard_fail: bool = False     # 命中禁忌位階 / 禁忌題材 → 直接 REMOVE
    strong: bool = False        # C2 限定：交集 ≥ 2 → core 升級條件
    evidence: list[str] = field(default_factory=list)


@dataclass
class ValidationResult:
    """單一 (group, ticker) pair 的最終判定。"""
    group: str
    ticker: str
    name: str
    verdict: Verdict
    confidence: float           # 0-1
    c1: CheckResult
    c2: CheckResult
    c3: CheckResult
    coverage_present: bool = False
    web_recent_3m: bool = False
    downstream_demote_hit: bool = False
    hard_fail_reason: str = ""
    evidence_coverage: str = ""
    evidence_web: list[dict] = field(default_factory=list)
    rationale: str = ""
    validated_at: str = ""

    def to_row(self) -> dict:
        """攤平給 parquet：每欄都是基本型別。"""
        import json as _json
        return {
            "group": self.group,
            "ticker": self.ticker,
            "name": self.name,
            "verdict": self.verdict.value,
            "confidence": self.confidence,
            "c1_industry": self.c1.ok,
            "c2_themes": self.c2.ok,
            "c2_strong": self.c2.strong,
            "c3_position": self.c3.ok,
            "hard_fail_reason": self.hard_fail_reason,
            "coverage_present": self.coverage_present,
            "web_recent_3m": self.web_recent_3m,
            "downstream_demote": self.downstream_demote_hit,
            "evidence_coverage": self.evidence_coverage,
            "evidence_web": _json.dumps(self.evidence_web, ensure_ascii=False),
            "rationale": self.rationale,
            "validated_at": self.validated_at,
        }
