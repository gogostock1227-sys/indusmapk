# 電源供應器/BBU — 驗證報告 v2

> 生成於 2026-04-25 17:07 UTC
> 三維 spec：allowed_segments=['POWER_GREEN', 'ELEC_COMP'] / allowed_positions=['POWER_MOD'] / required_themes_any=['HVDC_800V', 'BBU', 'GB300_RUBIN']

## 小結

| 判決 | 檔數 |
|---|---:|
| 🟢 core | 1 |
| 🟡 satellite | 2 |
| 🔴 remove | 14 |
| ⚪ skipped (profile 不完整) | 0 |
| **總計** | **17** |

平均信心：**0.33**

## 🟢 核心成分股（1 檔）

- **2308 台達電** `pos=POWER_MOD` `themes=['HVDC_800V', 'GB300_RUBIN', 'BBU']` （信心 1.00）

## 🟡 衛星成分股（2 檔）

- 6409 旭隼 `pos=ODM_SYS` （信心 0.65；產業板塊匹配 (ELEC_COMP)；必要題材交集：['BBU', 'GB300_RUBIN']；位階「ODM_SYS」...）
- 6203 海韻電 `pos=CONNECTOR` （信心 0.65；產業板塊匹配 (ELEC_COMP)；必要題材交集：['GB300_RUBIN']；位階「CONNECTOR」不在白名單...）

## 🔴 應移除（14 檔）

| 代號 | 公司 | 移除原因 | 信心 |
|---|---|---|---:|
| 2301 | 光寶科 | 產業板塊不匹配（個股 COMP_HW vs 族群允許 ['POWER_GREEN', 'ELEC_COMP']）；必要題材交集：['BBU', 'GB300_R | 0.40 |
| 6121 | 新普 | 產業板塊不匹配（個股 COMP_HW vs 族群允許 ['POWER_GREEN', 'ELEC_COMP']）；必要題材交集：['BBU', 'GB300_R | 0.40 |
| 3015 | 全漢 | 產業板塊匹配 (ELEC_COMP)；未命中任何必要題材（個股題材 ['LEO_SAT', 'ROBOTICS'] vs 族群必要 ['BBU', 'GB300 | 0.25 |
| 6282 | 康舒 | 產業板塊匹配 (ELEC_COMP)；未命中任何必要題材（個股題材 ['LEO_SAT', 'ROBOTICS'] vs 族群必要 ['BBU', 'GB300 | 0.25 |
| 6412 | 群電 | 產業板塊匹配 (ELEC_COMP)；未命中任何必要題材（個股題材 ['LEO_SAT', 'ROBOTICS'] vs 族群必要 ['BBU', 'GB300 | 0.25 |
| 3617 | 碩天 | 產業板塊匹配 (ELEC_COMP)；未命中任何必要題材（個股題材 ['LEO_SAT', 'ROBOTICS'] vs 族群必要 ['BBU', 'GB300 | 0.25 |
| 2457 | 飛宏 | 產業板塊匹配 (ELEC_COMP)；未命中任何必要題材（個股題材 ['LEO_SAT', 'ROBOTICS'] vs 族群必要 ['BBU', 'GB300 | 0.25 |
| 3078 | 僑威 | 產業板塊匹配 (ELEC_COMP)；未命中任何必要題材（個股題材 ['LEO_SAT', 'ROBOTICS'] vs 族群必要 ['BBU', 'GB300 | 0.25 |
| 6419 | 京晨科 | 產業板塊匹配 (ELEC_COMP)；未命中任何必要題材（個股題材 ['GLP1_OBESITY', 'LEO_SAT', 'ROBOTICS'] vs 族群必 | 0.25 |
| 3518 | 柏騰 | 產業板塊匹配 (ELEC_COMP)；未命中任何必要題材（個股題材 ['5G_6G', 'COWOS', 'GLASS_GCS'] vs 族群必要 ['BBU' | 0.25 |
| 6558 | 興能高 | 產業板塊匹配 (ELEC_COMP)；未命中任何必要題材（個股題材 ['LEO_SAT', 'ROBOTICS'] vs 族群必要 ['BBU', 'GB300 | 0.25 |
| 8109 | 博大 | 產業板塊匹配 (ELEC_COMP)；未命中任何必要題材（個股題材 ['LEO_SAT', 'ROBOTICS'] vs 族群必要 ['BBU', 'GB300 | 0.25 |
| 3664 | 安瑞-KY | 產業板塊不匹配（個股 NETCOM vs 族群允許 ['POWER_GREEN', 'ELEC_COMP']）；未命中任何必要題材（個股題材 ['LEO_SAT | 0.00 |
| 3094 | 聯傑 | 產業板塊不匹配（個股 AI_SEMI vs 族群允許 ['POWER_GREEN', 'ELEC_COMP']）；未命中任何必要題材（個股題材 [] vs 族群 | 0.00 |
