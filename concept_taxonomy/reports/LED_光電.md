# LED/光電 — 驗證報告 v2

> 生成於 2026-04-25 17:07 UTC
> 三維 spec：allowed_segments=['ELEC_COMP', 'AI_SEMI'] / allowed_positions=['OPTIC_COMP', 'IC_DESIGN', 'FOUNDRY', 'MAT_WAFER'] / required_themes_any=['VCSEL']

## 小結

| 判決 | 檔數 |
|---|---:|
| 🟢 core | 0 |
| 🟡 satellite | 3 |
| 🔴 remove | 16 |
| ⚪ skipped (profile 不完整) | 0 |
| **總計** | **19** |

平均信心：**0.18**

## 🟡 衛星成分股（3 檔）

- 3437 榮創 `pos=FOUNDRY` （信心 0.60；產業板塊匹配 (ELEC_COMP)；未命中任何必要題材（個股題材 ['COWOS', 'GB300_RUBIN', '...）
- 3066 李洲 `pos=IC_DESIGN` （信心 0.60；產業板塊匹配 (ELEC_COMP)；未命中任何必要題材（個股題材 ['LEO_SAT', 'ROBOTICS'] vs...）
- 3535 晶彩科 `pos=FOUNDRY` （信心 0.60；產業板塊匹配 (ELEC_COMP)；未命中任何必要題材（個股題材 ['COWOS', 'GB300_RUBIN', '...）

## 🔴 應移除（16 檔）

| 代號 | 公司 | 移除原因 | 信心 |
|---|---|---|---:|
| 4956 | 光鋐 | C3: 位階「BRAND」在禁區（族群 forbidden=['ODM_SYS', 'BRAND', 'END_USER', 'SVC_SAAS', 'DISTRIB', 'CONNECTOR', 'PASSIVE']） | 0.45 |
| 5484 | 慧友 | 產業板塊匹配 (ELEC_COMP)；未命中任何必要題材（個股題材 ['LEO_SAT', 'ROBOTICS'] vs 族群必要 ['VCSEL']）；位階「 | 0.25 |
| 2486 | 一詮 | 產業板塊匹配 (ELEC_COMP)；未命中任何必要題材（個股題材 ['COWOS', 'GB300_RUBIN', 'SOIC_3D'] vs 族群必要 [' | 0.25 |
| 3714 | 富采 | C3: 位階「PASSIVE」在禁區（族群 forbidden=['ODM_SYS', 'BRAND', 'END_USER', 'SVC_SAAS', 'DISTRIB', 'CONNECTOR', 'PASSIVE']） | 0.05 |
| 6226 | 光鼎 | C3: 位階「PASSIVE」在禁區（族群 forbidden=['ODM_SYS', 'BRAND', 'END_USER', 'SVC_SAAS', 'DISTRIB', 'CONNECTOR', 'PASSIVE']） | 0.05 |
| 2393 | 億光 | C3: 位階「PASSIVE」在禁區（族群 forbidden=['ODM_SYS', 'BRAND', 'END_USER', 'SVC_SAAS', 'DISTRIB', 'CONNECTOR', 'PASSIVE']） | 0.05 |
| 3339 | 泰谷 | C3: 位階「ODM_SYS」在禁區（族群 forbidden=['ODM_SYS', 'BRAND', 'END_USER', 'SVC_SAAS', 'DISTRIB', 'CONNECTOR', 'PASSIVE']） | 0.05 |
| 2426 | 鼎元 | C3: 位階「ODM_SYS」在禁區（族群 forbidden=['ODM_SYS', 'BRAND', 'END_USER', 'SVC_SAAS', 'DISTRIB', 'CONNECTOR', 'PASSIVE']） | 0.05 |
| 3591 | 艾笛森 | C3: 位階「PASSIVE」在禁區（族群 forbidden=['ODM_SYS', 'BRAND', 'END_USER', 'SVC_SAAS', 'DISTRIB', 'CONNECTOR', 'PASSIVE']） | 0.05 |
| 6168 | 宏齊 | C3: 位階「BRAND」在禁區（族群 forbidden=['ODM_SYS', 'BRAND', 'END_USER', 'SVC_SAAS', 'DISTRIB', 'CONNECTOR', 'PASSIVE']） | 0.05 |
| 6164 | 華興 | C3: 位階「ODM_SYS」在禁區（族群 forbidden=['ODM_SYS', 'BRAND', 'END_USER', 'SVC_SAAS', 'DISTRIB', 'CONNECTOR', 'PASSIVE']） | 0.05 |
| 5244 | 弘凱 | C3: 位階「PASSIVE」在禁區（族群 forbidden=['ODM_SYS', 'BRAND', 'END_USER', 'SVC_SAAS', 'DISTRIB', 'CONNECTOR', 'PASSIVE']） | 0.05 |
| 3031 | 佰鴻 | C3: 位階「PASSIVE」在禁區（族群 forbidden=['ODM_SYS', 'BRAND', 'END_USER', 'SVC_SAAS', 'DISTRIB', 'CONNECTOR', 'PASSIVE']） | 0.05 |
| 6854 | 錼創科技-KY創 | C3: 位階「PASSIVE」在禁區（族群 forbidden=['ODM_SYS', 'BRAND', 'END_USER', 'SVC_SAAS', 'DISTRIB', 'CONNECTOR', 'PASSIVE']） | 0.05 |
| 3441 | 聯一光電 | C3: 位階「ODM_SYS」在禁區（族群 forbidden=['ODM_SYS', 'BRAND', 'END_USER', 'SVC_SAAS', 'DISTRIB', 'CONNECTOR', 'PASSIVE']） | 0.05 |
| 2466 | 冠西電 | C3: 位階「PASSIVE」在禁區（族群 forbidden=['ODM_SYS', 'BRAND', 'END_USER', 'SVC_SAAS', 'DISTRIB', 'CONNECTOR', 'PASSIVE']） | 0.05 |
