# 儲能系統/BESS — 驗證報告 v2

> 生成於 2026-04-25 21:54 UTC
> 三維 spec：allowed_segments=['POWER_GREEN', 'COMP_HW', 'ELEC_COMP'] / allowed_positions=['POWER_MOD', 'PASSIVE'] / required_themes_any=['EV_BATTERY', 'DATACENTER_POWER']

## 小結

| 判決 | 檔數 |
|---|---:|
| 🟢 core | 0 |
| 🟡 satellite | 3 |
| 🔴 remove | 5 |
| ⚪ skipped (profile 不完整) | 1 |
| **總計** | **9** |

平均信心：**0.43**

## 🟡 衛星成分股（3 檔）

- 2308 台達電 `pos=POWER_MOD` （信心 0.70；產業板塊匹配 (POWER_GREEN)；未命中任何必要題材（個股題材 ['BBU', 'GB300_RUBIN', '...）
- 3015 全漢 `pos=PASSIVE` （信心 0.70；產業板塊匹配 (ELEC_COMP)；未命中任何必要題材（個股題材 ['LEO_SAT', 'ROBOTICS'] vs...）
- 2312 金寶 `pos=PASSIVE` （信心 0.70；產業板塊匹配 (ELEC_COMP)；未命中任何必要題材（個股題材 ['GB300_RUBIN', 'LEO_SAT',...）

## 🔴 應移除（5 檔）

| 代號 | 公司 | 移除原因 | 信心 |
|---|---|---|---:|
| 1513 | 中興電 | 產業板塊匹配 (ELEC_COMP)；未命中任何必要題材（個股題材 ['GB300_RUBIN', 'LEO_SAT', 'ROBOTICS'] vs 族群必要 | 0.35 |
| 6409 | 旭隼 | 產業板塊匹配 (ELEC_COMP)；未命中任何必要題材（個股題材 ['BBU', 'GB300_RUBIN'] vs 族群必要 ['DATACENTER_PO | 0.35 |
| 6121 | 新普 | 產業板塊匹配 (COMP_HW)；未命中任何必要題材（個股題材 ['BBU', 'GB300_RUBIN', 'LIQUID_COOL'] vs 族群必要 [' | 0.35 |
| 6806 | 森崴能源 | 產業板塊匹配 (POWER_GREEN)；未命中任何必要題材（個股題材 ['LEO_SAT', 'ROBOTICS'] vs 族群必要 ['DATACENTER | 0.35 |
| 3211 | 順達 | 產業板塊匹配 (COMP_HW)；未命中任何必要題材（個股題材 ['BBU', 'LEO_SAT', 'ROBOTICS'] vs 族群必要 ['DATACEN | 0.35 |

## ⚪ 跳過（profile 待補完）（1 檔）

- 1519 華城：profile 缺 segment='' 或 position='END_USER'
