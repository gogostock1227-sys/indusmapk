# 智慧城市/V2X — 驗證報告 v2

> 生成於 2026-04-25 21:54 UTC
> 三維 spec：allowed_segments=['AI_SEMI', 'NETCOM', 'EV_AUTO'] / allowed_positions=['IC_DESIGN', 'ODM_SYS', 'BRAND'] / required_themes_any=['ADAS', '5G_6G', 'WIFI7']

## 小結

| 判決 | 檔數 |
|---|---:|
| 🟢 core | 0 |
| 🟡 satellite | 1 |
| 🔴 remove | 4 |
| ⚪ skipped (profile 不完整) | 1 |
| **總計** | **6** |

平均信心：**0.39**

## 🟡 衛星成分股（1 檔）

- 2345 智邦 `pos=ODM_SYS` （信心 0.70；產業板塊匹配 (NETCOM)；未命中任何必要題材（個股題材 ['LEO_SAT', 'OPTIC_800G_1.6T'...）

## 🔴 應移除（4 檔）

| 代號 | 公司 | 移除原因 | 信心 |
|---|---|---|---:|
| 5388 | 中磊 | C3: 位階「PCB_HDI」在禁區（族群 forbidden=['FOUNDRY', 'OSAT_ADV', 'CONNECTOR', 'PASSIVE', 'PCB_HDI', 'SUBSTRATE', 'THERMAL', 'SVC_SAAS']） | 0.55 |
| 6285 | 啟碁 | C3: 位階「PASSIVE」在禁區（族群 forbidden=['FOUNDRY', 'OSAT_ADV', 'CONNECTOR', 'PASSIVE', 'PCB_HDI', 'SUBSTRATE', 'THERMAL', 'SVC_SAAS']） | 0.55 |
| 1513 | 中興電 | 產業板塊不匹配（個股 ELEC_COMP vs 族群允許 ['AI_SEMI', 'NETCOM', 'EV_AUTO']）；未命中任何必要題材（個股題材 [' | 0.45 |
| 2308 | 台達電 | 產業板塊不匹配（個股 POWER_GREEN vs 族群允許 ['AI_SEMI', 'NETCOM', 'EV_AUTO']）；未命中任何必要題材（個股題材  | 0.10 |

## ⚪ 跳過（profile 待補完）（1 檔）

- 1503 士電：profile 缺 segment='' 或 position='CHASSIS'
