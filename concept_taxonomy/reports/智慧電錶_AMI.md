# 智慧電錶/AMI — 驗證報告 v2

> 生成於 2026-04-25 17:07 UTC
> 三維 spec：allowed_segments=['POWER_GREEN', 'ELEC_COMP', 'NETCOM'] / allowed_positions=['ODM_SYS', 'IC_DESIGN', 'BRAND', 'END_USER'] / required_themes_any=['DATACENTER_POWER', 'HVDC_800V']

## 小結

| 判決 | 檔數 |
|---|---:|
| 🟢 core | 0 |
| 🟡 satellite | 2 |
| 🔴 remove | 2 |
| ⚪ skipped (profile 不完整) | 3 |
| **總計** | **7** |

平均信心：**0.25**

## 🟡 衛星成分股（2 檔）

- 2308 台達電 `pos=POWER_MOD` （信心 0.65；產業板塊匹配 (POWER_GREEN)；必要題材交集：['HVDC_800V']；位階「POWER_MOD」不在白名單...）
- 1611 中電 `pos=ODM_SYS` （信心 0.60；產業板塊匹配 (POWER_GREEN)；未命中任何必要題材（個股題材 ['LEO_SAT', 'ROBOTICS'] ...）

## 🔴 應移除（2 檔）

| 代號 | 公司 | 移除原因 | 信心 |
|---|---|---|---:|
| 6283 | 淳安 | 產業板塊匹配 (ELEC_COMP)；未命中任何必要題材（個股題材 ['ADAS'] vs 族群必要 ['DATACENTER_POWER', 'HVDC_80 | 0.25 |
| 3380 | 明泰 | 產業板塊匹配 (NETCOM)；未命中任何必要題材（個股題材 ['CPO_PHOTONIC', 'OPTIC_800G_1.6T', 'WIFI7'] vs 族 | 0.25 |

## ⚪ 跳過（profile 待補完）（3 檔）

- 1513 中興電：profile 缺 segment='' 或 position='BRAND'
- 1503 士電：profile 缺 segment='' 或 position='CHASSIS'
- 1519 華城：profile 缺 segment='' 或 position='END_USER'
