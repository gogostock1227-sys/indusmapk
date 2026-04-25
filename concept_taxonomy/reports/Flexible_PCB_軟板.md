# Flexible PCB/軟板 — 驗證報告 v2

> 生成於 2026-04-25 21:54 UTC
> 三維 spec：allowed_segments=['AI_SEMI', 'ELEC_COMP'] / allowed_positions=['PCB_HDI', 'PCB_FPC', 'SUBSTRATE', 'MAT_CHEM'] / required_themes_any=['GB300_RUBIN', 'COWOS']

## 小結

| 判決 | 檔數 |
|---|---:|
| 🟢 core | 2 |
| 🟡 satellite | 0 |
| 🔴 remove | 5 |
| ⚪ skipped (profile 不完整) | 0 |
| **總計** | **7** |

平均信心：**0.54**

## 🟢 核心成分股（2 檔）

- **6269 台郡** `pos=PCB_HDI` `themes=['COWOS', 'GB300_RUBIN', 'CPO_PHOTONIC']` （信心 1.00）
- **2402 毅嘉** `pos=PCB_HDI` `themes=['GB300_RUBIN', 'CPO_PHOTONIC', 'OPTIC_800G_1.6T']` （信心 1.00）

## 🔴 應移除（5 檔）

| 代號 | 公司 | 移除原因 | 信心 |
|---|---|---|---:|
| 3044 | 健鼎 | 產業板塊匹配 (ELEC_COMP)；未命中任何必要題材（個股題材 ['ADAS', 'LEO_SAT', 'ROBOTICS'] vs 族群必要 ['COWO | 0.35 |
| 6153 | 嘉聯益 | 產業板塊匹配 (ELEC_COMP)；未命中任何必要題材（個股題材 ['CPO_PHOTONIC', 'LEO_SAT', 'ROBOTICS'] vs 族群必 | 0.35 |
| 3645 | 達邁 | 產業板塊匹配 (ELEC_COMP)；未命中任何必要題材（個股題材 ['LEO_SAT', 'ROBOTICS'] vs 族群必要 ['COWOS', 'GB3 | 0.35 |
| 3229 | 晟鈦 | 產業板塊匹配 (ELEC_COMP)；未命中任何必要題材（個股題材 ['LEO_SAT', 'ROBOTICS'] vs 族群必要 ['COWOS', 'GB3 | 0.35 |
| 3105 | 穩懋 | 產業板塊匹配 (AI_SEMI)；未命中任何必要題材（個股題材 ['CPO_PHOTONIC', 'OPTIC_800G_1.6T', 'VCSEL'] vs  | 0.35 |
