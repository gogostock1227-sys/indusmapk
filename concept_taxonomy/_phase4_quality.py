"""Phase 4 品質精修 — 一次性處理：
1. 從 .bak 還原 ticker→中文名映射，修復當前 concept_groups.py 的「# XXXX」純 ticker 註解
2. 合併 7 組重複族群
3. 刪除 4 個過時族群（標註為已合併/已棄用）
4. 修正 2 個命名筆誤（\\ → /）
5. Sanity check 載入正常
"""
from __future__ import annotations
import re
import sys
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "concept_groups.py"
BAK = ROOT / "concept_groups.py.bak"  # 最早備份（4/24，含中文名）
PHASE4_BAK = ROOT / "concept_groups.py.bak3_pre_phase4"  # phase4 前備份


# ────────────────────────────────────────────
# Step 0: 備份
# ────────────────────────────────────────────
shutil.copy(TARGET, PHASE4_BAK)
print(f"[BACKUP] {TARGET} → {PHASE4_BAK}")


# ────────────────────────────────────────────
# Step 1: 從 .bak 抽 ticker→中文名
# ────────────────────────────────────────────
bak_text = BAK.read_text(encoding='utf-8')
ticker2name: dict[str, str] = {}
for m in re.finditer(r'"(\d{4,6}[A-Z]?)"\s*,\s*#\s*(.+?)$', bak_text, re.MULTILINE):
    tk = m.group(1)
    name = m.group(2).strip()
    # 去括號內 extra
    name = re.split(r'[（(]', name)[0].strip()
    if tk not in ticker2name and name and len(name) < 25:
        ticker2name[tk] = name
print(f"[NAMES] 從 .bak 抽出 {len(ticker2name)} 筆 ticker→中文名")


# ────────────────────────────────────────────
# Step 2: 修復當前 concept_groups.py 的純 ticker 註解
# 把 `"XXXX",  # XXXX` 替換為 `"XXXX",  # 中文名`
# ────────────────────────────────────────────
content = TARGET.read_text(encoding='utf-8')
fixed = 0
def replace_comment(m):
    global fixed
    tk = m.group(1)
    current_comment = m.group(2).strip()
    # 若 current_comment 是純 ticker（無中文）且我們有中文名，替換
    if re.fullmatch(r'\d{4,6}[A-Z]?', current_comment):
        if tk in ticker2name:
            fixed += 1
            return f'"{tk}",  # {ticker2name[tk]}'
    return m.group(0)

content = re.sub(
    r'"(\d{4,6}[A-Z]?)"\s*,\s*#\s*([^\n]+)',
    replace_comment,
    content,
)
print(f"[FIX] 修復 {fixed} 個純 ticker 註解 → 中文名")


# ────────────────────────────────────────────
# Step 3: 合併 7 組重複族群
# 策略：保留主族群（成分股取兩者聯集），副族群清空 list 並標 # MERGED_TO 註解
# ────────────────────────────────────────────
DUPLICATES = [
    ("造紙/紙業", ["造紙"]),
    ("橡膠/輪胎原料", ["輪胎/橡膠"]),
    ("CDMO/生技製造服務", ["生技 CDMO"]),
    ("智慧醫療/AI醫學", ["AI 智慧醫療"]),
    ("動物保健/寵物醫療", ["寵物經濟", "寵物/生活周邊"]),
    ("運動休閒", ["健身/運動用品"]),
    ("散熱/液冷", ["熱交換器/散熱器"]),
    # 銀髮類
    ("老年長照/銀髮醫療", ["銀髮/高齡經濟"]),
]

# Re-import 確認當前 list
import sys
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
# 強制 re-import
for mod in list(sys.modules.keys()):
    if mod == 'concept_groups':
        del sys.modules[mod]

# 用當前文本動態 exec 取出最新 CONCEPT_GROUPS
ns = {}
exec(content, ns)
current_groups = ns['CONCEPT_GROUPS']

merged_count = 0
for main, dups in DUPLICATES:
    if main not in current_groups:
        continue
    main_set = list(current_groups[main])
    main_seen = set(main_set)
    for d in dups:
        if d not in current_groups:
            continue
        # 把 d 的 ticker append 到 main（去重）
        for tk in current_groups[d]:
            if tk not in main_seen:
                main_set.append(tk)
                main_seen.add(tk)
        # 清空 d，標 MERGED_TO
        # 在 content 中找 "d": [...] 替換為 [], 加 MERGED_TO 註解
        d_escaped = re.escape(f'"{d}":')
        pat = re.compile(rf'    {d_escaped}\s*\[(?:.*?)\n    \],', re.DOTALL)
        replacement = f'    "{d}": [\n        # MERGED_TO: "{main}" — 此族群已合併，保留為空殼避免 break\n    ],'
        new_content, n = pat.subn(replacement, content)
        if n > 0:
            content = new_content
            merged_count += 1
            print(f"  [MERGE] {d} → {main} (+{len(current_groups[d])} ticker)")
    # 更新 main 族群成分（用合併後 main_set）
    main_escaped = re.escape(f'"{main}":')
    pat = re.compile(rf'    {main_escaped}\s*\[(?:.*?)\n    \],', re.DOTALL)
    new_block_lines = [f'    "{main}": [']
    new_block_lines.append(f'        # ── 合併後成分股（含 {", ".join(dups)} 並去重）──')
    for tk in main_set:
        nm = ticker2name.get(tk, tk)
        new_block_lines.append(f'        "{tk}",  # {nm}')
    new_block_lines.append('    ],')
    new_block = '\n'.join(new_block_lines)
    content, n = pat.subn(new_block, content)
    if n > 0:
        print(f"  [UPDATE] {main}: {len(main_set)} 檔（合併後）")

print(f"[MERGE] 合併 {merged_count} 個副族群")


# ────────────────────────────────────────────
# Step 4: 標註過時族群（不刪除，加 DEPRECATED 註解避免 break）
# ────────────────────────────────────────────
DEPRECATED = [
    ("防疫/口罩", "疫情題材已過時 4 年，2026 年無實質意義"),
    ("宅經濟/遠距", "疫情題材已過時，原成分多轉型為 AI 伺服器"),
    ("龍年受惠/文創遊戲", "年度短線題材已過，建議併入文化傳媒/遊戲股"),
    ("植物肉/替代蛋白", "5 檔皆食品大廠，建議降為標記而非獨立族群"),
]

deprecated_count = 0
for group, reason in DEPRECATED:
    g_esc = re.escape(f'"{group}":')
    pat = re.compile(rf'    {g_esc}\s*\[(.*?)\n    \],', re.DOTALL)
    m = pat.search(content)
    if not m:
        continue
    body = m.group(1)
    # 在 list 開頭加 DEPRECATED 註解
    new_body = f'\n        # DEPRECATED ({reason})' + body
    new_block = f'    "{group}": [{new_body}\n    ],'
    content = pat.sub(new_block, content)
    deprecated_count += 1
    print(f"  [DEPRECATED] {group}")
print(f"[DEPRECATED] 標註 {deprecated_count} 個過時族群")


# ────────────────────────────────────────────
# Step 5: 命名筆誤修正（\ → /）
# 注意：直接改 key 會 break，所以先確認影響
# ────────────────────────────────────────────
NAMING_FIX = [
    ('DDR5\\LPDDR5 記憶體', 'DDR5/LPDDR5 記憶體'),
    ('NAND Flash\\SSD 控制', 'NAND Flash/SSD 控制'),
]
naming_count = 0
for old, new in NAMING_FIX:
    if f'"{old}"' in content:
        content = content.replace(f'"{old}":', f'"{new}":')
        naming_count += 1
        print(f"  [RENAME] {old!r} → {new!r}")
print(f"[RENAME] 修正 {naming_count} 個命名筆誤")


# ────────────────────────────────────────────
# Step 6: 寫回 + Sanity Check
# ────────────────────────────────────────────
TARGET.write_text(content, encoding='utf-8')
print(f"\n[WRITE] {TARGET}")

# Re-import
for mod in list(sys.modules.keys()):
    if mod == 'concept_groups':
        del sys.modules[mod]
try:
    from concept_groups import CONCEPT_GROUPS as cg
    print(f"\n[SANITY] 載入成功，總族群數: {len(cg)}")
    # 檢查 HBM
    hbm = cg.get('HBM 高頻寬記憶體', [])
    print(f"  HBM: {len(hbm)} 檔 → {hbm[:5]}...")
    # 檢查命名修正
    if 'DDR5/LPDDR5 記憶體' in cg:
        print(f"  ✓ DDR5/LPDDR5 記憶體（修正後）: {len(cg['DDR5/LPDDR5 記憶體'])} 檔")
    if 'NAND Flash/SSD 控制' in cg:
        print(f"  ✓ NAND Flash/SSD 控制（修正後）: {len(cg['NAND Flash/SSD 控制'])} 檔")
    # 檢查合併
    for main, dups in DUPLICATES:
        for d in dups:
            if d in cg:
                d_count = len(cg[d])
                print(f"  ✓ {d}（已合併到 {main}）: {d_count} 檔（應為 0 或保留空殼）")
except Exception as e:
    print(f"\n[ERROR] 載入失敗: {e}")
    print(f"還原: cp {PHASE4_BAK} {TARGET}")
