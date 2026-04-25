# NAND Flash/SSD 控制 — 驗證報告 v2

> 生成於 2026-04-25 21:54 UTC
> 三維 spec：allowed_segments=['AI_SEMI', 'COMP_HW'] / allowed_positions=['IDM_NAND', 'IC_DESIGN', 'DISTRIB', 'OSAT_TRAD'] / required_themes_any=['NAND_TIGHT', 'aiDAPTIV']

## 小結

| 判決 | 檔數 |
|---|---:|
| 🟢 core | 2 |
| 🟡 satellite | 3 |
| 🔴 remove | 1 |
| ⚪ skipped (profile 不完整) | 0 |
| **總計** | **6** |

平均信心：**0.77**

## 🟢 核心成分股（2 檔）

- **8299 群聯** `pos=IC_DESIGN` `themes=['aiDAPTIV', 'NAND_TIGHT']` （信心 1.00）
- **5289 宜鼎** `pos=OSAT_TRAD` `themes=['DDR5_RISE', 'NAND_TIGHT', 'GB300_RUBIN']` （信心 1.00）

## 🟡 衛星成分股（3 檔）

- 2337 旺宏 `pos=MAT_WAFER` （信心 0.75；產業板塊匹配 (AI_SEMI)；必要題材交集：['NAND_TIGHT']；位階「MAT_WAFER」不在白名單（族群...）
- 8271 宇瞻 `pos=BRAND` （信心 0.75；產業板塊匹配 (AI_SEMI)；必要題材交集：['NAND_TIGHT']；位階「BRAND」不在白名單（族群 all...）
- 4967 十銓 `pos=THERMAL` （信心 0.75；產業板塊匹配 (AI_SEMI)；必要題材交集：['NAND_TIGHT']；位階「THERMAL」不在白名單（族群 a...）

## 🔴 應移除（1 檔）

| 代號 | 公司 | 移除原因 | 信心 |
|---|---|---|---:|
| 3260 | 威剛 | 產業板塊匹配 (AI_SEMI)；未命中任何必要題材（個股題材 ['DDR5_RISE', 'HBM3E_HBM4', 'NICHE_DRAM'] vs 族群必 | 0.35 |
