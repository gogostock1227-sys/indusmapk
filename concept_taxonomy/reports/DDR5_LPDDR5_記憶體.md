# DDR5/LPDDR5 記憶體 — 驗證報告 v2

> 生成於 2026-04-25 21:54 UTC
> 三維 spec：allowed_segments=['AI_SEMI'] / allowed_positions=['IDM_DRAM', 'IC_DESIGN', 'DISTRIB', 'TEST_INTF'] / required_themes_any=['DDR5_RISE', 'NICHE_DRAM']

## 小結

| 判決 | 檔數 |
|---|---:|
| 🟢 core | 1 |
| 🟡 satellite | 2 |
| 🔴 remove | 2 |
| ⚪ skipped (profile 不完整) | 0 |
| **總計** | **5** |

平均信心：**0.64**

## 🟢 核心成分股（1 檔）

- **2408 南亞科** `pos=IDM_DRAM` `themes=['DDR5_RISE', 'NICHE_DRAM', 'HBM3E_HBM4']` （信心 1.00）

## 🟡 衛星成分股（2 檔）

- 2344 華邦電 `pos=MAT_WAFER` （信心 0.75；產業板塊匹配 (AI_SEMI)；必要題材交集：['NICHE_DRAM']；位階「MAT_WAFER」不在白名單（族群...）
- 3260 威剛 `pos=ODM_SYS` （信心 0.75；產業板塊匹配 (AI_SEMI)；必要題材交集：['DDR5_RISE', 'NICHE_DRAM']（強：['DDR5...）

## 🔴 應移除（2 檔）

| 代號 | 公司 | 移除原因 | 信心 |
|---|---|---|---:|
| 3006 | 晶豪科 | 產業板塊匹配 (AI_SEMI)；未命中任何必要題材（個股題材 ['GB300_RUBIN', 'HBM3E_HBM4', 'NAND_TIGHT'] vs 族 | 0.35 |
| 4967 | 十銓 | 產業板塊匹配 (AI_SEMI)；未命中任何必要題材（個股題材 ['GB300_RUBIN', 'LIQUID_COOL', 'NAND_TIGHT'] vs  | 0.35 |
