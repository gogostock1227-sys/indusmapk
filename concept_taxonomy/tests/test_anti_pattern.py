"""
反模式零容忍測試。

使用者紅線：
  1. core_themes 不可含抽象詞（高速傳輸 / AI / 半導體 / 5G / ...）
     必須拆為 30+ enum 之一（SERDES_224G / ASIC_xxx / 5G_6G / ...）
  2. supply_chain_position 必須是 27 enum 之一
  3. industry_segment 必須是 13 enum 之一
"""
from __future__ import annotations

import json

from validator.schema import (
    ABSTRACT_THEME_BLACKLIST,
    CORE_THEME_ENUMS,
    INDUSTRY_SEGMENTS,
    SUPPLY_CHAIN_POSITIONS,
    StockProfile,
)


def test_industry_segments_count():
    """13 大產業板塊（_TAXONOMY_SCHEMA.md L12 鎖定）。"""
    assert len(INDUSTRY_SEGMENTS) == 13


def test_supply_chain_positions_count():
    """28 個供應鏈位階（_TAXONOMY_SCHEMA.md 表格實際列出 28 項；該文件標題寫 27 為筆誤）。

    分類：半導體 14 + 電子零組件 6 + 系統 4 + 電源/光通訊/其他 4 = 28
    """
    assert len(SUPPLY_CHAIN_POSITIONS) == 28, (
        f"位階數量改變請同步更新 _TAXONOMY_SCHEMA.md；目前 {len(SUPPLY_CHAIN_POSITIONS)}"
    )


def test_abstract_blacklist_includes_user_redline():
    """使用者紅線：高速傳輸 必須在黑名單。"""
    assert "高速傳輸" in ABSTRACT_THEME_BLACKLIST
    assert "AI" in ABSTRACT_THEME_BLACKLIST
    assert "半導體" in ABSTRACT_THEME_BLACKLIST


def test_blacklist_disjoint_with_enums():
    """抽象詞絕不可與 enum 重疊（避免歧義）。"""
    overlap = ABSTRACT_THEME_BLACKLIST & CORE_THEME_ENUMS
    assert not overlap, f"抽象黑名單與 enum 重疊：{overlap}"


def test_profile_with_abstract_theme_rejected():
    """個股 profile 含「高速傳輸」必被反模式檢查抓出。"""
    bad = StockProfile(
        ticker="3533",
        name="嘉澤",
        industry_segment="ELEC_COMP",
        supply_chain_position="CONNECTOR",
        core_themes=["高速傳輸"],  # 反模式
    )
    has_anti, reason = bad.has_anti_pattern()
    assert has_anti
    assert "高速傳輸" in reason


def test_profile_with_correct_themes_passes():
    """正確 profile：嘉澤 themes=[GB300_RUBIN, LIQUID_COOL, SERDES_224G]。"""
    good = StockProfile(
        ticker="3533",
        name="嘉澤",
        industry_segment="ELEC_COMP",
        supply_chain_position="CONNECTOR",
        core_themes=["GB300_RUBIN", "LIQUID_COOL", "SERDES_224G"],
    )
    has_anti, reason = good.has_anti_pattern()
    assert not has_anti, f"預期通過反模式檢查但失敗：{reason}"


def test_profile_complete_check():
    """三維完整率：缺任一視為 fail。"""
    incomplete = StockProfile(
        ticker="0001",
        name="測試",
        industry_segment="AI_SEMI",
        supply_chain_position="",  # 缺
        core_themes=["HBM3E_HBM4"],
    )
    assert not incomplete.is_complete()


def test_profile_invalid_position_caught():
    """位階亂填必抓。"""
    bad = StockProfile(
        ticker="0002",
        name="假位階",
        industry_segment="AI_SEMI",
        supply_chain_position="WAFER_GROUNDING",  # 不在 27 enum
        core_themes=["HBM3E_HBM4"],
    )
    has_anti, reason = bad.has_anti_pattern()
    assert has_anti
    assert "supply_chain_position" in reason


def test_profile_invalid_segment_caught():
    """板塊亂填必抓。"""
    bad = StockProfile(
        ticker="0003",
        name="假板塊",
        industry_segment="MAGIC_INDUSTRY",  # 不在 13 enum
        supply_chain_position="CONNECTOR",
        core_themes=["GB300_RUBIN"],
    )
    has_anti, reason = bad.has_anti_pattern()
    assert has_anti


def test_all_test_profiles_pass_anti_pattern(profiles: dict):
    """fixtures/test_profiles.json 的每筆 profile 必須通過反模式檢查。"""
    failures = []
    for sym, p in profiles.items():
        if sym.startswith("_"):
            continue
        prof = StockProfile(
            ticker=p["ticker"],
            name=p["name"],
            industry_segment=p["industry_segment"],
            supply_chain_position=p["supply_chain_position"],
            core_themes=p.get("core_themes", []),
        )
        has_anti, reason = prof.has_anti_pattern()
        if has_anti:
            failures.append(f"{sym} {p['name']}: {reason}")
    assert not failures, "fixture 內含反模式 profile：\n" + "\n".join(failures)


def test_specs_use_only_valid_positions(specs: dict):
    """group_specs.json 中所有 allowed_positions / forbidden_positions 必須在 27 enum。"""
    invalid = []
    for name, s in specs.items():
        if name.startswith("_"):
            continue
        for pos in s.get("allowed_positions", []) + s.get("forbidden_positions", []):
            if pos not in SUPPLY_CHAIN_POSITIONS:
                invalid.append(f"{name}: {pos}")
    assert not invalid, "specs 含非法位階：\n" + "\n".join(invalid)


def test_specs_use_only_valid_segments(specs: dict):
    """group_specs.json 中 allowed_segments 必須在 13 enum。"""
    invalid = []
    for name, s in specs.items():
        if name.startswith("_"):
            continue
        for seg in s.get("allowed_segments", []):
            if seg not in INDUSTRY_SEGMENTS:
                invalid.append(f"{name}: {seg}")
    assert not invalid, "specs 含非法板塊：\n" + "\n".join(invalid)


def test_specs_use_only_valid_themes(specs: dict):
    """group_specs.json 中 required_themes_any/strong + forbidden_themes 必須在 enum。"""
    invalid = []
    for name, s in specs.items():
        if name.startswith("_"):
            continue
        for theme in (
            s.get("required_themes_any", [])
            + s.get("required_themes_strong", [])
            + s.get("forbidden_themes", [])
        ):
            if theme not in CORE_THEME_ENUMS:
                invalid.append(f"{name}: {theme}")
    assert not invalid, "specs 含非 enum 題材：\n" + "\n".join(invalid)
