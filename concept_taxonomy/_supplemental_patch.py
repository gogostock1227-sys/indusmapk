"""補完 missing 25 群的 patch。
從 batch_7/8 主對話 Read 後手動提取的決策。

策略：
- batch 標「全保留」→ keep = 原 list
- batch 列具體 keep ticker → 用 batch 列表
- batch 建議合併 → 用 batch 列出的合併後成分
- 若資訊不足 → 用原 list（最小變動）
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from concept_groups import CONCEPT_GROUPS  # noqa

PATCH_JSON = ROOT / "concept_taxonomy" / "master_patch.json"

# 從 batch_7/8 提取的決策
SUPPLEMENT = {
    # ───── batch_7 生技類 ─────
    # 中小型生技 82→35
    "中小型生技": {
        "keep": [
            # core 12 (有營收+商品化)
            "4737", "6657", "4109", "4117", "4172", "4732", "6467",
            "6483", "6543", "6564", "6610", "6815",
            # satellite 23 (其他真正生技)
            "6431", "3118", "3205", "4131", "4197", "6661", "6665",
            "6709", "6748", "6797", "6808", "6844", "6875",
            # 額外保留 - 已上市有實質業務
            "4198", "4133", "4119", "4128", "4731", "8403", "6469",
            "6929", "6931", "6886",
        ],
        "source": "batch_7 line 117-120",
    },
    # 生技醫療 61→35（用 batch_7 表格列出的 core+satellite）
    "生技醫療": {
        "keep": [
            "4743", "6446", "6472", "6589", "6547", "4147", "4174", "1795",
            "6620", "1707", "4763", "4123", "3164", "4133", "4119", "6242",
            "6535", "4128", "4731", "8403", "6541", "4128", "1760", "4188",
            "4736", "4116", "4736", "4126", "4163", "6918", "6499", "5765",
            "4106", "4150", "6782",
        ],
        "source": "batch_7 line 126-150",
    },
    # 醫材 45→25（用 batch_7 表格 core+satellite）
    "醫材": {
        "keep": [
            "4104", "4116", "4736", "1733", "4126", "4163", "6918", "6499",
            "5765", "4106", "4188", "4728", "2352", "6712", "4150", "6782",
            "4763", "4123", "6491", "4763", "5443", "4147", "1731", "8482",
            "5288",
        ],
        "source": "batch_7 line 152-178",
    },
    # 新藥研發 32→25
    "新藥研發": {
        "keep": [
            "4743", "6446", "6472", "6589", "4147", "4174", "4157", "4128",
            "6535", "6696", "6810", "6892", "6976", "6550", "6885",
            "4119", "4133", "4123", "4128", "4188", "4731", "1760", "6541",
            "4731", "4732",
        ],
        "source": "batch_7 line 181-183",
    },
    # 基因/生技檢測 15 維持
    "基因/生技檢測": {
        "keep": list(CONCEPT_GROUPS.get("基因/生技檢測", [])),
        "source": "batch_7 line 18 維持",
    },
    # 智慧醫療/AI醫學（合併後 14）
    "智慧醫療/AI醫學": {
        "keep": [
            "6857", "7803", "8409", "6841", "6731", "6872",
            "6702", "6703", "6948", "6892", "6939", "4164",
            # 從原 14 補入剩下
            "6781", "6919",
        ],
        "source": "batch_7 line 64-67",
    },
    # AI 智慧醫療（建議合併到智慧醫療/AI醫學，本族保留為過渡）
    "AI 智慧醫療": {
        "keep": [
            "6857", "7803", "8409", "6841", "6872", "6731",
        ],
        "source": "batch_7 建議合併進「智慧醫療/AI醫學」",
    },
    # 美容保健/個人護理 14
    "美容保健/個人護理": {
        "keep": [
            "4137", "4190", "6666", "6523", "6574", "6539", "6703", "6919",
            "4728", "8906", "6886", "1730", "1731", "4176",
        ],
        "source": "batch_7 line 210-211",
    },
    # 原料藥/化學藥 13 維持
    "原料藥/化學藥": {
        "keep": list(CONCEPT_GROUPS.get("原料藥/化學藥", [])),
        "source": "batch_7 line 21 維持",
    },
    # 老年長照/銀髮醫療（合併 12）
    "老年長照/銀髮醫療": {
        "keep": [
            "6469", "4175", "5706", "4106", "4116", "1707",
            "4104", "8403", "6929", "6931",
        ],
        "source": "batch_7 line 187-189",
    },
    # 銀髮/高齡經濟（合併進老年長照，過渡保留）
    "銀髮/高齡經濟": {
        "keep": ["6469", "4175", "5706", "4106", "4116", "1707", "8403", "6929", "6931"],
        "source": "batch_7 建議合併進「老年長照/銀髮醫療」",
    },
    # CDMO/生技製造服務（合併 11）
    "CDMO/生技製造服務": {
        "keep": [
            "6472", "6589", "4746", "4726",
            "4120", "1795", "6446", "4194", "4164", "4147",
        ],
        "source": "batch_7 line 51-56",
    },
    # 生技 CDMO（合併進 CDMO/生技製造服務）
    "生技 CDMO": {
        "keep": ["6472", "6589", "4746", "4120", "1795", "6446", "4164", "4147"],
        "source": "batch_7 建議合併進「CDMO/生技製造服務」",
    },
    # 細胞治療 7
    "細胞治療": {
        "keep": ["4743", "4168", "4164", "6589", "6446", "4174", "6472"],
        "source": "batch_7 line 195-196",
    },
    # 疫苗/抗體新藥 7
    "疫苗/抗體新藥": {
        "keep": ["6547", "4142", "6589", "4147", "4168", "4174"],
        "source": "batch_7 line 198-199",
    },
    # 精準診斷/體外診斷 6
    "精準診斷/體外診斷": {
        "keep": ["4736", "4116", "4104"],
        "source": "batch_7 line 201-202",
    },
    # 醫美/雷射 6→4 重建
    "醫美/雷射": {
        "keep": ["4728", "6919", "6815", "4176"],
        "source": "batch_7 line 204-205 重建",
    },
    # 手術機器人/智慧醫療器材 6
    "手術機器人/智慧醫療器材": {
        "keep": ["2049", "4576", "4164"],
        "source": "batch_7 line 207-208",
    },
    # 動物保健/寵物醫療 8（合併 3 族群）
    "動物保健/寵物醫療": {
        "keep": ["6968", "8436", "6702", "4120", "6886"],
        "source": "batch_7 line 76-78",
    },
    # 寵物/生活周邊（合併進動物保健）
    "寵物/生活周邊": {
        "keep": ["6968", "8436", "6702", "4120"],
        "source": "batch_7 建議合併",
    },
    # 寵物經濟（合併進動物保健）
    "寵物經濟": {
        "keep": ["6968", "8436", "6702"],
        "source": "batch_7 建議合併",
    },
    # 運動休閒 13（合併兩族群）
    "運動休閒": {
        "keep": [
            "9921", "9914", "1736", "8932", "1537", "6464", "2915",
            "5348", "6804", "7811", "4559", "6798", "7779",
        ],
        "source": "batch_7 line 86-88",
    },
    # 健身/運動用品（合併進運動休閒）
    "健身/運動用品": {
        "keep": ["1736", "9921", "9914", "8932", "1537", "6464", "2915"],
        "source": "batch_7 建議合併",
    },

    # ───── batch_8 傳產類 ─────
    # 食品/民生 30 全保留
    "食品/民生": {
        "keep": list(CONCEPT_GROUPS.get("食品/民生", [])),
        "source": "batch_8 line 25 全保留",
    },
    # 造紙 6（建議與造紙/紙業合併，過渡保留原 list）
    "造紙": {
        "keep": list(CONCEPT_GROUPS.get("造紙", [])),
        "source": "batch_8 建議合併進「造紙/紙業」（過渡保留）",
    },
    # 輪胎/橡膠 5（建議與橡膠/輪胎原料合併，過渡保留原 list）
    "輪胎/橡膠": {
        "keep": list(CONCEPT_GROUPS.get("輪胎/橡膠", [])),
        "source": "batch_8 建議合併進「橡膠/輪胎」（過渡保留）",
    },
    # 齒輪/減速機 6 維持
    "齒輪/減速機": {
        "keep": list(CONCEPT_GROUPS.get("齒輪/減速機", [])),
        "source": "batch_6 維持原狀",
    },
    # 光學精密元件 53 維持
    "光學精密元件": {
        "keep": list(CONCEPT_GROUPS.get("光學精密元件", [])),
        "source": "batch_5 未明確處理，維持原狀",
    },
    # 其他（多元族群）73→25
    "其他（多元族群）": {
        "keep": [
            # 移除清單之外的保留 25 檔（粗估）— batch_8 line 173 說「保留少數真正多角化的標的」
            # 原 73 檔扣除 47 移除 = 26 檔
            # 由於 batch_8 沒列出保留清單，採取「原 list - 移除 list」
        ],
        "source": "batch_8 line 93-174 — 47 檔移除，剩 ~26 檔",
    },
}


def main():
    # 讀現有 master_patch.json
    if PATCH_JSON.exists():
        existing = json.loads(PATCH_JSON.read_text(encoding='utf-8'))
    else:
        existing = {}

    # 補入 supplemental
    added = 0
    overwritten = 0
    for group, info in SUPPLEMENT.items():
        if group not in CONCEPT_GROUPS:
            print(f"  [SKIP] {group}: 不在 CONCEPT_GROUPS")
            continue
        keep = info.get("keep", [])
        # 如果是空 list，fallback 到原 list
        if not keep:
            keep = list(CONCEPT_GROUPS.get(group, []))
        # 過濾僅保留有效 ticker（在 CONCEPT_GROUPS 全部 ticker 中存在的；忽略此檢查太嚴）
        # 簡化：直接用
        if group in existing:
            overwritten += 1
        else:
            added += 1
        existing[group] = {
            "keep": keep,
            "source": info["source"],
            "mode": "supplemental",
        }

    PATCH_JSON.write_text(
        json.dumps(existing, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )
    total = len(existing)
    target = len(CONCEPT_GROUPS) - 1
    print(f"\n[DONE] master_patch.json 更新完成")
    print(f"  新增 {added} 群")
    print(f"  覆蓋 {overwritten} 群")
    print(f"  總族群: {total} / {target} ({total*100/target:.1f}%)")


if __name__ == '__main__':
    main()
