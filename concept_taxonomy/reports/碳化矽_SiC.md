# 碳化矽/SiC — 驗證報告 v2

> 生成於 2026-04-25 17:07 UTC
> 三維 spec：allowed_segments=['AI_SEMI', 'EV_AUTO', 'POWER_GREEN'] / allowed_positions=['FOUNDRY', 'IC_DESIGN', 'MAT_WAFER', 'IDM_DRAM', 'OSAT_ADV', 'TEST_INTF'] / required_themes_any=['EV_BATTERY', 'HVDC_800V']

## 小結

| 判決 | 檔數 |
|---|---:|
| 🟢 core | 0 |
| 🟡 satellite | 7 |
| 🔴 remove | 4 |
| ⚪ skipped (profile 不完整) | 1 |
| **總計** | **12** |

平均信心：**0.35**

## 🟡 衛星成分股（7 檔）

- 2308 台達電 `pos=POWER_MOD` （信心 0.65；產業板塊匹配 (POWER_GREEN)；必要題材交集：['HVDC_800V']；位階「POWER_MOD」不在白名單...）
- 3016 嘉晶 `pos=MAT_WAFER` （信心 0.60；產業板塊匹配 (AI_SEMI)；未命中任何必要題材（個股題材 ['COWOS', 'LEO_SAT', 'N2_2NM...）
- 3707 漢磊 `pos=FOUNDRY` （信心 0.60；產業板塊匹配 (AI_SEMI)；未命中任何必要題材（個股題材 ['GB300_RUBIN'] vs 族群必要 ['EV...）
- 6182 合晶 `pos=FOUNDRY` （信心 0.60；產業板塊匹配 (AI_SEMI)；未命中任何必要題材（個股題材 ['COWOS', 'LEO_SAT', 'N2_2NM...）
- 6488 環球晶 `pos=FOUNDRY` （信心 0.60；產業板塊匹配 (AI_SEMI)；未命中任何必要題材（個股題材 ['ASIC_TPU', 'GB300_RUBIN', ...）
- 8261 富鼎 `pos=FOUNDRY` （信心 0.60；產業板塊匹配 (AI_SEMI)；未命中任何必要題材（個股題材 ['COWOS', 'GB300_RUBIN', 'HB...）
- 2342 茂矽 `pos=FOUNDRY` （信心 0.60；產業板塊匹配 (AI_SEMI)；未命中任何必要題材（個股題材 [] vs 族群必要 ['EV_BATTERY', 'H...）

## 🔴 應移除（4 檔）

| 代號 | 公司 | 移除原因 | 信心 |
|---|---|---|---:|
| 2301 | 光寶科 | C3: 位階「PASSIVE」在禁區（族群 forbidden=['ODM_SYS', 'BRAND', 'END_USER', 'DISTRIB', 'SVC_SAAS', 'THERMAL', 'CONNECTOR', 'PASSIVE']） | 0.00 |
| 2457 | 飛宏 | C3: 位階「ODM_SYS」在禁區（族群 forbidden=['ODM_SYS', 'BRAND', 'END_USER', 'DISTRIB', 'SVC_SAAS', 'THERMAL', 'CONNECTOR', 'PASSIVE']） | 0.00 |
| 6282 | 康舒 | C3: 位階「PASSIVE」在禁區（族群 forbidden=['ODM_SYS', 'BRAND', 'END_USER', 'DISTRIB', 'SVC_SAAS', 'THERMAL', 'CONNECTOR', 'PASSIVE']） | 0.00 |
| 3332 | 幸康 | C3: 位階「PASSIVE」在禁區（族群 forbidden=['ODM_SYS', 'BRAND', 'END_USER', 'DISTRIB', 'SVC_SAAS', 'THERMAL', 'CONNECTOR', 'PASSIVE']） | 0.00 |

## ⚪ 跳過（profile 待補完）（1 檔）

- 6270 倍微：profile 缺 segment='' 或 position='FOUNDRY'
