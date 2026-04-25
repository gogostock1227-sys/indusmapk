# AI PC/邊緣AI — 驗證報告 v2

> 生成於 2026-04-25 21:54 UTC
> 三維 spec：allowed_segments=['COMP_HW'] / allowed_positions=['ODM_SYS', 'BRAND'] / required_themes_any=[]

## 小結

| 判決 | 檔數 |
|---|---:|
| 🟢 core | 2 |
| 🟡 satellite | 8 |
| 🔴 remove | 1 |
| ⚪ skipped (profile 不完整) | 0 |
| **總計** | **11** |

平均信心：**0.77**

## 🟢 核心成分股（2 檔）

- **2382 廣達** `pos=ODM_SYS` `themes=['GB300_RUBIN', 'ASIC_TPU']` （信心 1.00）
- **2353 宏碁** `pos=ODM_SYS` `themes=['GB300_RUBIN', 'LEO_SAT', 'ROBOTICS']` （信心 1.00）

## 🟡 衛星成分股（8 檔）

- 3231 緯創 `pos=SUBSTRATE` （信心 0.75；產業板塊匹配 (COMP_HW)；必要題材交集：[]；位階「SUBSTRATE」不在白名單（族群 allowed=['O...）
- 2356 英業達 `pos=THERMAL` （信心 0.75；產業板塊匹配 (COMP_HW)；必要題材交集：[]；位階「THERMAL」不在白名單（族群 allowed=['ODM...）
- 2324 仁寶 `pos=THERMAL` （信心 0.75；產業板塊匹配 (COMP_HW)；必要題材交集：[]；位階「THERMAL」不在白名單（族群 allowed=['ODM...）
- 4938 和碩 `pos=THERMAL` （信心 0.75；產業板塊匹配 (COMP_HW)；必要題材交集：[]；位階「THERMAL」不在白名單（族群 allowed=['ODM...）
- 2357 華碩 `pos=THERMAL` （信心 0.75；產業板塊匹配 (COMP_HW)；必要題材交集：[]；位階「THERMAL」不在白名單（族群 allowed=['ODM...）
- 2376 技嘉 `pos=THERMAL` （信心 0.75；產業板塊匹配 (COMP_HW)；必要題材交集：[]；位階「THERMAL」不在白名單（族群 allowed=['ODM...）
- 6414 樺漢 `pos=CHASSIS` （信心 0.75；產業板塊匹配 (COMP_HW)；必要題材交集：[]；位階「CHASSIS」不在白名單（族群 allowed=['ODM...）
- 6206 飛捷 `pos=END_USER` （信心 0.75；產業板塊匹配 (COMP_HW)；必要題材交集：[]；位階「END_USER」不在白名單（族群 allowed=['OD...）

## 🔴 應移除（1 檔）

| 代號 | 公司 | 移除原因 | 信心 |
|---|---|---|---:|
| 2454 | 聯發科 | 產業板塊不匹配（個股 AI_SEMI vs 族群允許 ['COMP_HW']）；必要題材交集：[]；位階「FOUNDRY」不在白名單（族群 allowed=[' | 0.50 |
