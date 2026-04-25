# HVDC/直流電力 — 驗證報告 v2

> 生成於 2026-04-25 21:54 UTC
> 三維 spec：allowed_segments=['AI_SEMI', 'POWER_GREEN', 'ELEC_COMP'] / allowed_positions=['POWER_MOD'] / required_themes_any=['HVDC_800V', 'DATACENTER_POWER']

## 小結

| 判決 | 檔數 |
|---|---:|
| 🟢 core | 1 |
| 🟡 satellite | 0 |
| 🔴 remove | 4 |
| ⚪ skipped (profile 不完整) | 1 |
| **總計** | **6** |

平均信心：**0.40**

## 🟢 核心成分股（1 檔）

- **2308 台達電** `pos=POWER_MOD` `themes=['HVDC_800V', 'GB300_RUBIN', 'BBU']` （信心 1.00）

## 🔴 應移除（4 檔）

| 代號 | 公司 | 移除原因 | 信心 |
|---|---|---|---:|
| 6409 | 旭隼 | 產業板塊匹配 (ELEC_COMP)；未命中任何必要題材（個股題材 ['BBU', 'GB300_RUBIN'] vs 族群必要 ['DATACENTER_PO | 0.35 |
| 3015 | 全漢 | 產業板塊匹配 (ELEC_COMP)；未命中任何必要題材（個股題材 ['LEO_SAT', 'ROBOTICS'] vs 族群必要 ['DATACENTER_P | 0.35 |
| 1504 | 東元 | 產業板塊匹配 (ELEC_COMP)；未命中任何必要題材（個股題材 ['GB300_RUBIN', 'LEO_SAT', 'LIQUID_COOL'] vs 族 | 0.35 |
| 8261 | 富鼎 | 產業板塊匹配 (AI_SEMI)；未命中任何必要題材（個股題材 ['COWOS', 'GB300_RUBIN', 'HBM3E_HBM4'] vs 族群必要 [ | 0.35 |

## ⚪ 跳過（profile 待補完）（1 檔）

- 1503 士電：profile 缺 segment='' 或 position='CHASSIS'
