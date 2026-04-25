# AI基礎設施/資料中心 — 驗證報告 v2

> 生成於 2026-04-25 17:07 UTC
> 三維 spec：allowed_segments=['COMP_HW', 'NETCOM', 'POWER_GREEN', 'ELEC_COMP'] / allowed_positions=['ODM_SYS', 'BRAND', 'CHASSIS', 'THERMAL', 'POWER_MOD', 'OPTIC_MOD'] / required_themes_any=['GB300_RUBIN', 'HVDC_800V', 'LIQUID_COOL', 'DATACENTER_POWER']

## 小結

| 判決 | 檔數 |
|---|---:|
| 🟢 core | 11 |
| 🟡 satellite | 8 |
| 🔴 remove | 0 |
| ⚪ skipped (profile 不完整) | 0 |
| **總計** | **19** |

平均信心：**0.85**

## 🟢 核心成分股（11 檔）

- **2382 廣達** `pos=ODM_SYS` `themes=['GB300_RUBIN', 'ASIC_TPU']` （信心 1.00）
- **2356 英業達** `pos=THERMAL` `themes=['GB300_RUBIN', 'LIQUID_COOL', 'LEO_SAT']` （信心 1.00）
- **6669 緯穎** `pos=THERMAL` `themes=['GB300_RUBIN', 'ASIC_TRAINIUM', 'ASIC_TPU']` （信心 1.00）
- **2376 技嘉** `pos=THERMAL` `themes=['COWOS', 'GB300_RUBIN', 'LIQUID_COOL']` （信心 1.00）
- **3017 奇鋐** `pos=THERMAL` `themes=['LIQUID_COOL', 'GB300_RUBIN']` （信心 1.00）
- **3324 雙鴻** `pos=THERMAL` `themes=['LIQUID_COOL', 'GB300_RUBIN']` （信心 1.00）
- **2308 台達電** `pos=POWER_MOD` `themes=['HVDC_800V', 'GB300_RUBIN', 'BBU']` （信心 1.00）
- **6414 樺漢** `pos=THERMAL` `themes=['GB300_RUBIN', 'LIQUID_COOL', 'LEO_SAT']` （信心 1.00）
- **3693 營邦** `pos=THERMAL` `themes=['GB300_RUBIN', 'LIQUID_COOL', 'LEO_SAT']` （信心 1.00）
- **8210 勤誠** `pos=THERMAL` `themes=['COWOS', 'GB300_RUBIN', 'LIQUID_COOL']` （信心 1.00）
- **6125 廣運** `pos=THERMAL` `themes=['GB300_RUBIN', 'LIQUID_COOL', 'N2_2NM']` （信心 1.00）

## 🟡 衛星成分股（8 檔）

- 3231 緯創 `pos=SUBSTRATE` （信心 0.65；產業板塊匹配 (COMP_HW)；必要題材交集：['GB300_RUBIN']；位階「SUBSTRATE」不在白名單（族...）
- 2301 光寶科 `pos=PASSIVE` （信心 0.65；產業板塊匹配 (COMP_HW)；必要題材交集：['GB300_RUBIN', 'LIQUID_COOL']；位階「PA...）
- 2368 金像電 `pos=PCB_HDI` （信心 0.65；產業板塊匹配 (ELEC_COMP)；必要題材交集：['GB300_RUBIN']；位階「PCB_HDI」不在白名單（族...）
- 3515 華擎 `pos=PASSIVE` （信心 0.65；產業板塊匹配 (COMP_HW)；必要題材交集：['GB300_RUBIN', 'LIQUID_COOL']；位階「PA...）
- 3013 晟銘電 `pos=CONNECTOR` （信心 0.65；產業板塊匹配 (COMP_HW)；必要題材交集：['GB300_RUBIN', 'LIQUID_COOL']；位階「CO...）
- 6933 AMAX-KY `pos=EQUIP` （信心 0.65；產業板塊匹配 (COMP_HW)；必要題材交集：['GB300_RUBIN', 'LIQUID_COOL']；位階「EQ...）
- 2345 智邦 `pos=ODM_SYS` （信心 0.60；產業板塊匹配 (NETCOM)；未命中任何必要題材（個股題材 ['LEO_SAT', 'OPTIC_800G_1.6T'...）
- 6419 京晨科 `pos=ODM_SYS` （信心 0.60；產業板塊匹配 (ELEC_COMP)；未命中任何必要題材（個股題材 ['GLP1_OBESITY', 'LEO_SAT'...）
