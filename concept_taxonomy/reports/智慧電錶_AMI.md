# 智慧電錶/AMI — 驗證報告 v2

> 生成於 2026-04-25 21:54 UTC
> 三維 spec：allowed_segments=['POWER_GREEN', 'ELEC_COMP', 'NETCOM'] / allowed_positions=['ODM_SYS', 'IC_DESIGN', 'BRAND', 'END_USER'] / required_themes_any=['DATACENTER_POWER', 'HVDC_800V']

## 小結

| 判決 | 檔數 |
|---|---:|
| 🟢 core | 0 |
| 🟡 satellite | 4 |
| 🔴 remove | 1 |
| ⚪ skipped (profile 不完整) | 2 |
| **總計** | **7** |

平均信心：**0.46**

## 🟡 衛星成分股（4 檔）

- 2308 台達電 `pos=POWER_MOD` （信心 0.75；產業板塊匹配 (POWER_GREEN)；必要題材交集：['HVDC_800V']；位階「POWER_MOD」不在白名單...）
- 1513 中興電 `pos=BRAND` （信心 0.70；產業板塊匹配 (ELEC_COMP)；未命中任何必要題材（個股題材 ['GB300_RUBIN', 'LEO_SAT',...）
- 6283 淳安 `pos=END_USER` （信心 0.70；產業板塊匹配 (ELEC_COMP)；未命中任何必要題材（個股題材 ['ADAS'] vs 族群必要 ['DATACEN...）
- 1611 中電 `pos=ODM_SYS` （信心 0.70；產業板塊匹配 (POWER_GREEN)；未命中任何必要題材（個股題材 ['LEO_SAT', 'ROBOTICS'] ...）

## 🔴 應移除（1 檔）

| 代號 | 公司 | 移除原因 | 信心 |
|---|---|---|---:|
| 3380 | 明泰 | 產業板塊匹配 (NETCOM)；未命中任何必要題材（個股題材 ['CPO_PHOTONIC', 'OPTIC_800G_1.6T', 'WIFI7'] vs 族 | 0.35 |

## ⚪ 跳過（profile 待補完）（2 檔）

- 1503 士電：profile 缺 segment='' 或 position='CHASSIS'
- 1519 華城：profile 缺 segment='' 或 position='END_USER'
