# 智慧家庭/Matter — 驗證報告 v2

> 生成於 2026-04-25 17:07 UTC
> 三維 spec：allowed_segments=['NETCOM', 'COMP_HW', 'AI_SEMI'] / allowed_positions=['IC_DESIGN', 'ODM_SYS', 'BRAND'] / required_themes_any=['WIFI7', '5G_6G']

## 小結

| 判決 | 檔數 |
|---|---:|
| 🟢 core | 1 |
| 🟡 satellite | 2 |
| 🔴 remove | 4 |
| ⚪ skipped (profile 不完整) | 0 |
| **總計** | **7** |

平均信心：**0.46**

## 🟢 核心成分股（1 檔）

- **3596 智易** `pos=ODM_SYS` `themes=['WIFI7', '5G_6G']` （信心 1.00）

## 🟡 衛星成分股（2 檔）

- 3380 明泰 `pos=IP` （信心 0.65；產業板塊匹配 (NETCOM)；必要題材交集：['WIFI7']；位階「IP」不在白名單（族群 allowed=['IC...）
- 2332 友訊 `pos=ODM_SYS` （信心 0.60；產業板塊匹配 (NETCOM)；未命中任何必要題材（個股題材 ['LEO_SAT', 'OPTIC_800G_1.6T'...）

## 🔴 應移除（4 檔）

| 代號 | 公司 | 移除原因 | 信心 |
|---|---|---|---:|
| 6285 | 啟碁 | C3: 位階「PASSIVE」在禁區（族群 forbidden=['FOUNDRY', 'OSAT_ADV', 'DISTRIB', 'CONNECTOR', 'PASSIVE', 'PCB_HDI', 'SUBSTRATE', 'THERMAL', 'SVC_SAAS']） | 0.45 |
| 5388 | 中磊 | C3: 位階「PCB_HDI」在禁區（族群 forbidden=['FOUNDRY', 'OSAT_ADV', 'DISTRIB', 'CONNECTOR', 'PASSIVE', 'PCB_HDI', 'SUBSTRATE', 'THERMAL', 'SVC_SAAS']） | 0.45 |
| 2357 | 華碩 | C3: 位階「THERMAL」在禁區（族群 forbidden=['FOUNDRY', 'OSAT_ADV', 'DISTRIB', 'CONNECTOR', 'PASSIVE', 'PCB_HDI', 'SUBSTRATE', 'THERMAL', 'SVC_SAAS']） | 0.05 |
| 2458 | 義隆 | C3: 位階「FOUNDRY」在禁區（族群 forbidden=['FOUNDRY', 'OSAT_ADV', 'DISTRIB', 'CONNECTOR', 'PASSIVE', 'PCB_HDI', 'SUBSTRATE', 'THERMAL', 'SVC_SAAS']） | 0.05 |
