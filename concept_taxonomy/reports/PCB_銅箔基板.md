# PCB/銅箔基板 — 驗證報告 v2

> 生成於 2026-04-25 21:54 UTC
> 三維 spec：allowed_segments=['ELEC_COMP', 'MATERIALS'] / allowed_positions=['PCB_HDI', 'SUBSTRATE', 'MAT_CHEM'] / required_themes_any=['GB300_RUBIN', 'ASIC_TRAINIUM', 'ASIC_TPU', 'COWOS', 'DDR5_RISE', 'HBM3E_HBM4']

## 小結

| 判決 | 檔數 |
|---|---:|
| 🟢 core | 10 |
| 🟡 satellite | 3 |
| 🔴 remove | 8 |
| ⚪ skipped (profile 不完整) | 0 |
| **總計** | **21** |

平均信心：**0.74**

## 🟢 核心成分股（10 檔）

- **2313 華通** `pos=SUBSTRATE` `themes=['GB300_RUBIN', 'OPTIC_800G_1.6T', 'LEO_SAT']` （信心 1.00）
- **8046 南電** `pos=SUBSTRATE` `themes=['COWOS', 'GB300_RUBIN']` （信心 1.00）
- **3037 欣興** `pos=SUBSTRATE` `themes=['COWOS', 'GB300_RUBIN', 'ASIC_TPU']` （信心 1.00）
- **2383 台光電** `pos=PCB_HDI` `themes=['GB300_RUBIN', 'ASIC_TRAINIUM', 'ASIC_TPU']` （信心 1.00）
- **6274 台燿** `pos=PCB_HDI` `themes=['HBM3E_HBM4', 'GB300_RUBIN', 'CPO_PHOTONIC']` （信心 1.00）
- **2368 金像電** `pos=PCB_HDI` `themes=['GB300_RUBIN', 'ASIC_TPU', 'CPO_PHOTONIC']` （信心 1.00）
- **5475 德宏** `pos=PCB_HDI` `themes=['GB300_RUBIN', 'ASIC_TPU', 'ASIC_MTIA']` （信心 1.00）
- **8358 金居** `pos=PCB_HDI` `themes=['GB300_RUBIN', 'ASIC_TRAINIUM', 'ASIC_TPU']` （信心 1.00）
- **5469 瀚宇博** `pos=PCB_HDI` `themes=['GB300_RUBIN', 'ASIC_TRAINIUM', 'ASIC_TPU']` （信心 1.00）
- **3189 景碩** `pos=SUBSTRATE` `themes=['COWOS', 'GB300_RUBIN']` （信心 0.85）

## 🟡 衛星成分股（3 檔）

- 4577 達航科技 `pos=TEST_INTF` （信心 0.75；產業板塊匹配 (ELEC_COMP)；必要題材交集：['COWOS']；位階「TEST_INTF」不在白名單（族群 al...）
- 4989 榮科 `pos=PCB_HDI` （信心 0.70；產業板塊匹配 (ELEC_COMP)；未命中任何必要題材（個股題材 ['5G_6G', 'LEO_SAT', 'ROBO...）
- 3093 港建* `pos=SUBSTRATE` （信心 0.70；產業板塊匹配 (ELEC_COMP)；未命中任何必要題材（個股題材 ['LEO_SAT', 'ROBOTICS'] vs...）

## 🔴 應移除（8 檔）

| 代號 | 公司 | 移除原因 | 信心 |
|---|---|---|---:|
| 6213 | 聯茂 | C3: 位階「PCB_FPC」在禁區（族群 forbidden=['PCB_FPC', 'IC_DESIGN', 'FOUNDRY', 'OSAT_ADV', 'END_USER', 'ODM_SYS', 'BRAND', 'CONNECTOR']） | 0.55 |
| 6438 | 迅得 | C3: 位階「FOUNDRY」在禁區（族群 forbidden=['PCB_FPC', 'IC_DESIGN', 'FOUNDRY', 'OSAT_ADV', 'END_USER', 'ODM_SYS', 'BRAND', 'CONNECTOR']） | 0.55 |
| 6664 | 群翊 | C3: 位階「OSAT_ADV」在禁區（族群 forbidden=['PCB_FPC', 'IC_DESIGN', 'FOUNDRY', 'OSAT_ADV', 'END_USER', 'ODM_SYS', 'BRAND', 'CONNECTOR']） | 0.55 |
| 2493 | 揚博 | C3: 位階「FOUNDRY」在禁區（族群 forbidden=['PCB_FPC', 'IC_DESIGN', 'FOUNDRY', 'OSAT_ADV', 'END_USER', 'ODM_SYS', 'BRAND', 'CONNECTOR']） | 0.55 |
| 8213 | 志超 | 產業板塊匹配 (ELEC_COMP)；未命中任何必要題材（個股題材 ['LEO_SAT', 'ROBOTICS'] vs 族群必要 ['ASIC_TPU', ' | 0.35 |
| 6141 | 柏承 | 產業板塊匹配 (ELEC_COMP)；未命中任何必要題材（個股題材 ['LEO_SAT', 'ROBOTICS'] vs 族群必要 ['ASIC_TPU', ' | 0.35 |
| 8215 | 明基材 | 產業板塊匹配 (ELEC_COMP)；未命中任何必要題材（個股題材 ['EV_BATTERY', 'LEO_SAT', 'ROBOTICS'] vs 族群必要  | 0.35 |
| 3229 | 晟鈦 | 產業板塊匹配 (ELEC_COMP)；未命中任何必要題材（個股題材 ['LEO_SAT', 'ROBOTICS'] vs 族群必要 ['ASIC_TPU', ' | 0.35 |
