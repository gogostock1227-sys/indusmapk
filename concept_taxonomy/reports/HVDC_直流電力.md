# HVDC/直流電力 — 驗證報告 v2

> 生成於 2026-04-25 17:07 UTC
> 三維 spec：allowed_segments=['AI_SEMI', 'POWER_GREEN', 'ELEC_COMP'] / allowed_positions=['POWER_MOD'] / required_themes_any=['HVDC_800V', 'DATACENTER_POWER']

## 小結

| 判決 | 檔數 |
|---|---:|
| 🟢 core | 1 |
| 🟡 satellite | 0 |
| 🔴 remove | 3 |
| ⚪ skipped (profile 不完整) | 2 |
| **總計** | **6** |

平均信心：**0.29**

## 🟢 核心成分股（1 檔）

- **2308 台達電** `pos=POWER_MOD` `themes=['HVDC_800V', 'GB300_RUBIN', 'BBU']` （信心 1.00）

## 🔴 應移除（3 檔）

| 代號 | 公司 | 移除原因 | 信心 |
|---|---|---|---:|
| 6409 | 旭隼 | 產業板塊匹配 (ELEC_COMP)；未命中任何必要題材（個股題材 ['BBU', 'GB300_RUBIN'] vs 族群必要 ['DATACENTER_PO | 0.25 |
| 3015 | 全漢 | 產業板塊匹配 (ELEC_COMP)；未命中任何必要題材（個股題材 ['LEO_SAT', 'ROBOTICS'] vs 族群必要 ['DATACENTER_P | 0.25 |
| 8261 | 富鼎 | 產業板塊匹配 (AI_SEMI)；未命中任何必要題材（個股題材 ['COWOS', 'GB300_RUBIN', 'HBM3E_HBM4'] vs 族群必要 [ | 0.25 |

## ⚪ 跳過（profile 待補完）（2 檔）

- 1503 士電：profile 缺 segment='' 或 position='CHASSIS'
- 1504 東元：profile 缺 segment='' 或 position='THERMAL'
