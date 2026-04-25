# AI伺服器 — 驗證報告 v2

> 生成於 2026-04-25 17:07 UTC
> 三維 spec：allowed_segments=['COMP_HW', 'ELEC_COMP', 'POWER_GREEN', 'AI_SEMI', 'NETCOM'] / allowed_positions=['ODM_SYS', 'BRAND', 'CHASSIS', 'THERMAL', 'POWER_MOD', 'PCB_HDI', 'PASSIVE', 'CONNECTOR', 'MAT_CHEM', 'FOUNDRY', 'OSAT_ADV', 'END_USER'] / required_themes_any=['GB300_RUBIN', 'ASIC_TRAINIUM', 'ASIC_TPU', 'LIQUID_COOL', 'HVDC_800V']

## 小結

| 判決 | 檔數 |
|---|---:|
| 🟢 core | 27 |
| 🟡 satellite | 9 |
| 🔴 remove | 1 |
| ⚪ skipped (profile 不完整) | 1 |
| **總計** | **38** |

平均信心：**0.86**

## 🟢 核心成分股（27 檔）

- **2317 鴻海** `pos=ODM_SYS` `themes=['GB300_RUBIN', 'ASIC_TRAINIUM']` （信心 1.00）
- **2382 廣達** `pos=ODM_SYS` `themes=['GB300_RUBIN', 'ASIC_TPU']` （信心 1.00）
- **2356 英業達** `pos=THERMAL` `themes=['GB300_RUBIN', 'LIQUID_COOL', 'LEO_SAT']` （信心 1.00）
- **6669 緯穎** `pos=THERMAL` `themes=['GB300_RUBIN', 'ASIC_TRAINIUM', 'ASIC_TPU']` （信心 1.00）
- **2376 技嘉** `pos=THERMAL` `themes=['COWOS', 'GB300_RUBIN', 'LIQUID_COOL']` （信心 1.00）
- **3017 奇鋐** `pos=THERMAL` `themes=['LIQUID_COOL', 'GB300_RUBIN']` （信心 1.00）
- **6414 樺漢** `pos=THERMAL` `themes=['GB300_RUBIN', 'LIQUID_COOL', 'LEO_SAT']` （信心 1.00）
- **3013 晟銘電** `pos=CONNECTOR` `themes=['GB300_RUBIN', 'LIQUID_COOL']` （信心 1.00）
- **2324 仁寶** `pos=THERMAL` `themes=['GB300_RUBIN', 'LIQUID_COOL', 'LEO_SAT']` （信心 1.00）
- **4938 和碩** `pos=THERMAL` `themes=['GB300_RUBIN', 'LIQUID_COOL', 'LEO_SAT']` （信心 1.00）
- **3693 營邦** `pos=THERMAL` `themes=['GB300_RUBIN', 'LIQUID_COOL', 'LEO_SAT']` （信心 1.00）
- **2368 金像電** `pos=PCB_HDI` `themes=['GB300_RUBIN', 'ASIC_TPU', 'CPO_PHOTONIC']` （信心 1.00）
- **8210 勤誠** `pos=THERMAL` `themes=['COWOS', 'GB300_RUBIN', 'LIQUID_COOL']` （信心 1.00）
- **3515 華擎** `pos=PASSIVE` `themes=['GB300_RUBIN', 'LIQUID_COOL', 'LEO_SAT']` （信心 1.00）
- **6125 廣運** `pos=THERMAL` `themes=['GB300_RUBIN', 'LIQUID_COOL', 'N2_2NM']` （信心 1.00）
- **2357 華碩** `pos=THERMAL` `themes=['GB300_RUBIN', 'LIQUID_COOL', 'LEO_SAT']` （信心 1.00）
- **2377 微星** `pos=THERMAL` `themes=['COWOS', 'GB300_RUBIN', 'LIQUID_COOL']` （信心 1.00）
- **6190 萬泰科** `pos=CONNECTOR` `themes=['GB300_RUBIN', 'CPO_PHOTONIC', 'LEO_SAT']` （信心 1.00）
- **2301 光寶科** `pos=PASSIVE` `themes=['GB300_RUBIN', 'LIQUID_COOL', 'BBU']` （信心 1.00）
- **2308 台達電** `pos=POWER_MOD` `themes=['HVDC_800V', 'GB300_RUBIN', 'BBU']` （信心 1.00）
- **2421 建準** `pos=THERMAL` `themes=['GB300_RUBIN', 'LIQUID_COOL', 'WIFI7']` （信心 1.00）
- **2059 川湖** `pos=THERMAL` `themes=['LIQUID_COOL', 'LEO_SAT', 'ROBOTICS']` （信心 1.00）
- **2383 台光電** `pos=PCB_HDI` `themes=['GB300_RUBIN', 'ASIC_TRAINIUM', 'ASIC_TPU']` （信心 1.00）
- **2492 華新科** `pos=PASSIVE` `themes=['GB300_RUBIN', 'LIQUID_COOL', 'LEO_SAT']` （信心 1.00）
- **8358 金居** `pos=PCB_HDI` `themes=['GB300_RUBIN', 'ASIC_TRAINIUM', 'ASIC_TPU']` （信心 1.00）
- **3653 健策** `pos=CONNECTOR` `themes=['GB300_RUBIN', 'ASIC_TRAINIUM', 'ASIC_TPU']` （信心 1.00）
- **3338 泰碩** `pos=CONNECTOR` `themes=['LIQUID_COOL', 'LEO_SAT', 'ROBOTICS']` （信心 1.00）

## 🟡 衛星成分股（9 檔）

- 3231 緯創 `pos=SUBSTRATE` （信心 0.65；產業板塊匹配 (COMP_HW)；必要題材交集：['ASIC_TRAINIUM', 'GB300_RUBIN']（強：[...）
- 6933 AMAX-KY `pos=EQUIP` （信心 0.65；產業板塊匹配 (COMP_HW)；必要題材交集：['GB300_RUBIN', 'LIQUID_COOL']；位階「EQ...）
- 2327 國巨* `pos=IC_DESIGN` （信心 0.65；產業板塊匹配 (ELEC_COMP)；必要題材交集：['ASIC_TPU', 'ASIC_TRAINIUM', 'GB3...）
- 6245 立端 `pos=ODM_SYS` （信心 0.60；產業板塊匹配 (NETCOM)；未命中任何必要題材（個股題材 ['5G_6G'] vs 族群必要 ['ASIC_TPU'...）
- 2345 智邦 `pos=ODM_SYS` （信心 0.60；產業板塊匹配 (NETCOM)；未命中任何必要題材（個股題材 ['LEO_SAT', 'OPTIC_800G_1.6T'...）
- 3044 健鼎 `pos=PASSIVE` （信心 0.60；產業板塊匹配 (ELEC_COMP)；未命中任何必要題材（個股題材 ['ADAS', 'LEO_SAT', 'ROBOT...）
- 3322 建舜電 `pos=CONNECTOR` （信心 0.60；產業板塊匹配 (ELEC_COMP)；未命中任何必要題材（個股題材 ['LEO_SAT', 'ROBOTICS'] vs...）
- 4927 泰鼎-KY `pos=PASSIVE` （信心 0.60；產業板塊匹配 (ELEC_COMP)；未命中任何必要題材（個股題材 ['LEO_SAT', 'ROBOTICS'] vs...）
- 6155 鈞寶 `pos=PASSIVE` （信心 0.60；產業板塊匹配 (ELEC_COMP)；未命中任何必要題材（個股題材 ['LEO_SAT', 'ROBOTICS'] vs...）

## 🔴 應移除（1 檔）

| 代號 | 公司 | 移除原因 | 信心 |
|---|---|---|---:|
| 6698 | 旭暉應材 | 產業板塊匹配 (ELEC_COMP)；未命中任何必要題材（個股題材 ['FOPLP', 'LEO_SAT', 'ROBOTICS'] vs 族群必要 ['ASI | 0.25 |

## ⚪ 跳過（profile 待補完）（1 檔）

- 8996 高力：profile 缺 segment='' 或 position='THERMAL'
