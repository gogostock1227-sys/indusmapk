# AI 眼鏡 / Meta Ray-Ban — 驗證報告 v2

> 生成於 2026-04-25 21:54 UTC
> 三維 spec：allowed_segments=['COMP_HW', 'ELEC_COMP', 'AI_SEMI'] / allowed_positions=['ODM_SYS', 'BRAND', 'IC_DESIGN', 'OPTIC_COMP', 'CHASSIS', 'PCB_FPC', 'PASSIVE'] / required_themes_any=['VCSEL', 'WIFI7']

## 小結

| 判決 | 檔數 |
|---|---:|
| 🟢 core | 0 |
| 🟡 satellite | 4 |
| 🔴 remove | 3 |
| ⚪ skipped (profile 不完整) | 0 |
| **總計** | **7** |

平均信心：**0.57**

## 🟡 衛星成分股（4 檔）

- 3105 穩懋 `pos=FOUNDRY` （信心 0.75；產業板塊匹配 (AI_SEMI)；必要題材交集：['VCSEL']；位階「FOUNDRY」不在白名單（族群 allowe...）
- 3008 大立光 `pos=PASSIVE` （信心 0.70；產業板塊匹配 (ELEC_COMP)；未命中任何必要題材（個股題材 ['ADAS', 'LEO_SAT', 'ROBOT...）
- 3376 新日興 `pos=BRAND` （信心 0.70；產業板塊匹配 (ELEC_COMP)；未命中任何必要題材（個股題材 ['GB300_RUBIN', 'ROBOTICS'...）
- 2317 鴻海 `pos=ODM_SYS` （信心 0.70；產業板塊匹配 (COMP_HW)；未命中任何必要題材（個股題材 ['ASIC_TRAINIUM', 'GB300_RUB...）

## 🔴 應移除（3 檔）

| 代號 | 公司 | 移除原因 | 信心 |
|---|---|---|---:|
| 8464 | 億豐 | 產業板塊不匹配（個股 CONSUMER vs 族群允許 ['COMP_HW', 'ELEC_COMP', 'AI_SEMI']）；未命中任何必要題材（個股題材  | 0.45 |
| 2385 | 群光 | 產業板塊匹配 (ELEC_COMP)；未命中任何必要題材（個股題材 ['COWOS', 'GB300_RUBIN', 'LIQUID_COOL'] vs 族群必 | 0.35 |
| 2454 | 聯發科 | 產業板塊匹配 (AI_SEMI)；未命中任何必要題材（個股題材 ['COWOS', 'DDR5_RISE', 'GB300_RUBIN'] vs 族群必要 [' | 0.35 |
