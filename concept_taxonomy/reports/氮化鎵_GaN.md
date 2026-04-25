# 氮化鎵/GaN — 驗證報告 v2

> 生成於 2026-04-25 17:07 UTC
> 三維 spec：allowed_segments=['AI_SEMI', 'POWER_GREEN', 'EV_AUTO'] / allowed_positions=['FOUNDRY', 'IC_DESIGN', 'MAT_WAFER', 'OSAT_ADV'] / required_themes_any=['HVDC_800V', 'EV_BATTERY', 'DATACENTER_POWER']

## 小結

| 判決 | 檔數 |
|---|---:|
| 🟢 core | 0 |
| 🟡 satellite | 6 |
| 🔴 remove | 5 |
| ⚪ skipped (profile 不完整) | 0 |
| **總計** | **11** |

平均信心：**0.41**

## 🟡 衛星成分股（6 檔）

- 3105 穩懋 `pos=FOUNDRY` （信心 0.60；產業板塊匹配 (AI_SEMI)；未命中任何必要題材（個股題材 ['CPO_PHOTONIC', 'OPTIC_800G...）
- 8086 宏捷科 `pos=FOUNDRY` （信心 0.60；產業板塊匹配 (AI_SEMI)；未命中任何必要題材（個股題材 ['COWOS', 'GB300_RUBIN', 'HB...）
- 6770 力積電 `pos=FOUNDRY` （信心 0.60；產業板塊匹配 (AI_SEMI)；未命中任何必要題材（個股題材 ['HBM3E_HBM4', 'WOW'] vs 族群必...）
- 3016 嘉晶 `pos=MAT_WAFER` （信心 0.60；產業板塊匹配 (AI_SEMI)；未命中任何必要題材（個股題材 ['COWOS', 'LEO_SAT', 'N2_2NM...）
- 3707 漢磊 `pos=FOUNDRY` （信心 0.60；產業板塊匹配 (AI_SEMI)；未命中任何必要題材（個股題材 ['GB300_RUBIN'] vs 族群必要 ['DA...）
- 6488 環球晶 `pos=FOUNDRY` （信心 0.60；產業板塊匹配 (AI_SEMI)；未命中任何必要題材（個股題材 ['ASIC_TPU', 'GB300_RUBIN', ...）

## 🔴 應移除（5 檔）

| 代號 | 公司 | 移除原因 | 信心 |
|---|---|---|---:|
| 2455 | 全新 | 產業板塊不匹配（個股 NETCOM vs 族群允許 ['AI_SEMI', 'POWER_GREEN', 'EV_AUTO']）；未命中任何必要題材（個股題材  | 0.35 |
| 8045 | 達運光電 | 產業板塊不匹配（個股 NETCOM vs 族群允許 ['AI_SEMI', 'POWER_GREEN', 'EV_AUTO']）；未命中任何必要題材（個股題材  | 0.35 |
| 5222 | 全訊 | 產業板塊匹配 (AI_SEMI)；未命中任何必要題材（個股題材 ['COWOS', 'LEO_SAT', 'N2_2NM'] vs 族群必要 ['DATACEN | 0.25 |
| 3714 | 富采 | C3: 位階「PASSIVE」在禁區（族群 forbidden=['ODM_SYS', 'BRAND', 'END_USER', 'DISTRIB', 'SVC_SAAS', 'THERMAL', 'CONNECTOR', 'PASSIVE', 'PCB_HDI']） | 0.00 |
| 8464 | 億豐 | C3: 位階「ODM_SYS」在禁區（族群 forbidden=['ODM_SYS', 'BRAND', 'END_USER', 'DISTRIB', 'SVC_SAAS', 'THERMAL', 'CONNECTOR', 'PASSIVE', 'PCB_HDI']） | 0.00 |
