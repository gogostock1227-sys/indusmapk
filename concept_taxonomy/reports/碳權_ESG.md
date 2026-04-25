# 碳權/ESG — 驗證報告 v2

> 生成於 2026-04-25 21:54 UTC
> 三維 spec：allowed_segments=['POWER_GREEN', 'FIN', 'SOFTWARE'] / allowed_positions=['SVC_SAAS', 'BRAND', 'END_USER'] / required_themes_any=[]

## 小結

| 判決 | 檔數 |
|---|---:|
| 🟢 core | 1 |
| 🟡 satellite | 2 |
| 🔴 remove | 4 |
| ⚪ skipped (profile 不完整) | 1 |
| **總計** | **8** |

平均信心：**0.54**

## 🟢 核心成分股（1 檔）

- **2002 中鋼** `pos=END_USER` `themes=['LEO_SAT', 'ROBOTICS']` （信心 0.85）

## 🟡 衛星成分股（2 檔）

- 2308 台達電 `pos=POWER_MOD` （信心 0.75；產業板塊匹配 (POWER_GREEN)；必要題材交集：[]；位階「POWER_MOD」不在白名單（族群 allowed...）
- 6806 森崴能源 `pos=ODM_SYS` （信心 0.75；產業板塊匹配 (POWER_GREEN)；必要題材交集：[]；位階「ODM_SYS」不在白名單（族群 allowed=[...）

## 🔴 應移除（4 檔）

| 代號 | 公司 | 移除原因 | 信心 |
|---|---|---|---:|
| 1101 | 台泥 | 產業板塊不匹配（個股 MATERIALS vs 族群允許 ['POWER_GREEN', 'FIN', 'SOFTWARE']）；必要題材交集：[]；位階「MA | 0.50 |
| 1102 | 亞泥 | 產業板塊不匹配（個股 MATERIALS vs 族群允許 ['POWER_GREEN', 'FIN', 'SOFTWARE']）；必要題材交集：[]；位階「MA | 0.50 |
| 1301 | 台塑 | 產業板塊不匹配（個股 MATERIALS vs 族群允許 ['POWER_GREEN', 'FIN', 'SOFTWARE']）；必要題材交集：[]；位階「PC | 0.50 |
| 1326 | 台化 | 產業板塊不匹配（個股 MATERIALS vs 族群允許 ['POWER_GREEN', 'FIN', 'SOFTWARE']）；必要題材交集：[]；位階「CH | 0.50 |

## ⚪ 跳過（profile 待補完）（1 檔）

- 1519 華城：profile 缺 segment='' 或 position='END_USER'
