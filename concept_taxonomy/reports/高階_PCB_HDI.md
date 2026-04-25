# 高階 PCB/HDI — 驗證報告 v2

> 生成於 2026-04-25 21:54 UTC
> 三維 spec：allowed_segments=['ELEC_COMP'] / allowed_positions=['PCB_HDI', 'PCB_FPC', 'SUBSTRATE', 'MAT_CHEM'] / required_themes_any=['GB300_RUBIN', 'COWOS']

## 小結

| 判決 | 檔數 |
|---|---:|
| 🟢 core | 9 |
| 🟡 satellite | 0 |
| 🔴 remove | 3 |
| ⚪ skipped (profile 不完整) | 0 |
| **總計** | **12** |

平均信心：**0.82**

## 🟢 核心成分股（9 檔）

- **2313 華通** `pos=SUBSTRATE` `themes=['GB300_RUBIN', 'OPTIC_800G_1.6T', 'LEO_SAT']` （信心 1.00）
- **8046 南電** `pos=SUBSTRATE` `themes=['COWOS', 'GB300_RUBIN']` （信心 1.00）
- **3037 欣興** `pos=SUBSTRATE` `themes=['COWOS', 'GB300_RUBIN', 'ASIC_TPU']` （信心 1.00）
- **6213 聯茂** `pos=PCB_FPC` `themes=['GB300_RUBIN', 'DDR5_RISE']` （信心 1.00）
- **6274 台燿** `pos=PCB_HDI` `themes=['HBM3E_HBM4', 'GB300_RUBIN', 'CPO_PHOTONIC']` （信心 1.00）
- **2368 金像電** `pos=PCB_HDI` `themes=['GB300_RUBIN', 'ASIC_TPU', 'CPO_PHOTONIC']` （信心 1.00）
- **2383 台光電** `pos=PCB_HDI` `themes=['GB300_RUBIN', 'ASIC_TRAINIUM', 'ASIC_TPU']` （信心 1.00）
- **5469 瀚宇博** `pos=PCB_HDI` `themes=['GB300_RUBIN', 'ASIC_TRAINIUM', 'ASIC_TPU']` （信心 1.00）
- **3189 景碩** `pos=SUBSTRATE` `themes=['COWOS', 'GB300_RUBIN']` （信心 0.85）

## 🔴 應移除（3 檔）

| 代號 | 公司 | 移除原因 | 信心 |
|---|---|---|---:|
| 3044 | 健鼎 | 產業板塊匹配 (ELEC_COMP)；未命中任何必要題材（個股題材 ['ADAS', 'LEO_SAT', 'ROBOTICS'] vs 族群必要 ['COWO | 0.35 |
| 8213 | 志超 | 產業板塊匹配 (ELEC_COMP)；未命中任何必要題材（個股題材 ['LEO_SAT', 'ROBOTICS'] vs 族群必要 ['COWOS', 'GB3 | 0.35 |
| 6153 | 嘉聯益 | 產業板塊匹配 (ELEC_COMP)；未命中任何必要題材（個股題材 ['CPO_PHOTONIC', 'LEO_SAT', 'ROBOTICS'] vs 族群必 | 0.35 |
