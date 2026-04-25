# PCB/銅箔基板 — 驗證報告 v2

> 生成於 2026-04-25 17:07 UTC
> 三維 spec：allowed_segments=['ELEC_COMP', 'MATERIALS'] / allowed_positions=['PCB_HDI', 'SUBSTRATE', 'MAT_CHEM'] / required_themes_any=['GB300_RUBIN', 'ASIC_TRAINIUM', 'ASIC_TPU', 'COWOS', 'DDR5_RISE', 'HBM3E_HBM4']

## 小結

| 判決 | 檔數 |
|---|---:|
| 🟢 core | 8 |
| 🟡 satellite | 4 |
| 🔴 remove | 9 |
| ⚪ skipped (profile 不完整) | 0 |
| **總計** | **21** |

平均信心：**0.65**

## 🟢 核心成分股（8 檔）

- **2313 華通** `pos=SUBSTRATE` `themes=['GB300_RUBIN', 'OPTIC_800G_1.6T', 'LEO_SAT']` （信心 1.00）
- **8046 南電** `pos=SUBSTRATE` `themes=['COWOS', 'GB300_RUBIN']` （信心 1.00）
- **3037 欣興** `pos=SUBSTRATE` `themes=['COWOS', 'GB300_RUBIN', 'ASIC_TPU']` （信心 1.00）
- **2383 台光電** `pos=PCB_HDI` `themes=['GB300_RUBIN', 'ASIC_TRAINIUM', 'ASIC_TPU']` （信心 1.00）
- **6274 台燿** `pos=PCB_HDI` `themes=['HBM3E_HBM4', 'GB300_RUBIN', 'CPO_PHOTONIC']` （信心 1.00）
- **2368 金像電** `pos=PCB_HDI` `themes=['GB300_RUBIN', 'ASIC_TPU', 'CPO_PHOTONIC']` （信心 1.00）
- **8358 金居** `pos=PCB_HDI` `themes=['GB300_RUBIN', 'ASIC_TRAINIUM', 'ASIC_TPU']` （信心 1.00）
- **5475 德宏** `pos=PCB_HDI` `themes=['GB300_RUBIN', 'LEO_SAT', 'ROBOTICS']` （信心 1.00）

## 🟡 衛星成分股（4 檔）

- 3189 景碩 `pos=SUBSTRATE` （信心 0.75；產業板塊不匹配（個股 AI_SEMI vs 族群允許 ['ELEC_COMP', 'MATERIALS']）；必要題材交...）
- 4577 達航科技 `pos=TEST_INTF` （信心 0.65；產業板塊匹配 (ELEC_COMP)；必要題材交集：['COWOS']；位階「TEST_INTF」不在白名單（族群 al...）
- 4989 榮科 `pos=PCB_HDI` （信心 0.60；產業板塊匹配 (ELEC_COMP)；未命中任何必要題材（個股題材 ['5G_6G', 'LEO_SAT', 'ROBO...）
- 3093 港建* `pos=SUBSTRATE` （信心 0.60；產業板塊匹配 (ELEC_COMP)；未命中任何必要題材（個股題材 ['LEO_SAT', 'ROBOTICS'] vs...）

## 🔴 應移除（9 檔）

| 代號 | 公司 | 移除原因 | 信心 |
|---|---|---|---:|
| 6213 | 聯茂 | C3: 位階「PCB_FPC」在禁區（族群 forbidden=['PCB_FPC', 'IC_DESIGN', 'FOUNDRY', 'OSAT_ADV', 'END_USER', 'ODM_SYS', 'BRAND', 'CONNECTOR']） | 0.45 |
| 6664 | 群翊 | C3: 位階「OSAT_ADV」在禁區（族群 forbidden=['PCB_FPC', 'IC_DESIGN', 'FOUNDRY', 'OSAT_ADV', 'END_USER', 'ODM_SYS', 'BRAND', 'CONNECTOR']） | 0.45 |
| 6438 | 迅得 | C3: 位階「FOUNDRY」在禁區（族群 forbidden=['PCB_FPC', 'IC_DESIGN', 'FOUNDRY', 'OSAT_ADV', 'END_USER', 'ODM_SYS', 'BRAND', 'CONNECTOR']） | 0.45 |
| 2493 | 揚博 | C3: 位階「FOUNDRY」在禁區（族群 forbidden=['PCB_FPC', 'IC_DESIGN', 'FOUNDRY', 'OSAT_ADV', 'END_USER', 'ODM_SYS', 'BRAND', 'CONNECTOR']） | 0.45 |
| 8215 | 明基材 | 產業板塊匹配 (ELEC_COMP)；未命中任何必要題材（個股題材 ['EV_BATTERY', 'LEO_SAT', 'ROBOTICS'] vs 族群必要  | 0.25 |
| 8213 | 志超 | 產業板塊匹配 (ELEC_COMP)；未命中任何必要題材（個股題材 ['LEO_SAT', 'ROBOTICS'] vs 族群必要 ['ASIC_TPU', ' | 0.25 |
| 5469 | 瀚宇博 | 產業板塊匹配 (ELEC_COMP)；未命中任何必要題材（個股題材 ['LEO_SAT', 'ROBOTICS'] vs 族群必要 ['ASIC_TPU', ' | 0.25 |
| 6141 | 柏承 | 產業板塊匹配 (ELEC_COMP)；未命中任何必要題材（個股題材 ['LEO_SAT', 'ROBOTICS'] vs 族群必要 ['ASIC_TPU', ' | 0.25 |
| 3229 | 晟鈦 | 產業板塊匹配 (ELEC_COMP)；未命中任何必要題材（個股題材 ['LEO_SAT', 'ROBOTICS'] vs 族群必要 ['ASIC_TPU', ' | 0.25 |
