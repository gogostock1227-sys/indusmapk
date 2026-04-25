# OLED/Micro LED — 驗證報告 v2

> 生成於 2026-04-25 17:07 UTC
> 三維 spec：allowed_segments=['ELEC_COMP', 'AI_SEMI'] / allowed_positions=['OPTIC_COMP', 'IC_DESIGN', 'MAT_CHEM', 'FOUNDRY', 'EQUIP'] / required_themes_any=['VCSEL']

## 小結

| 判決 | 檔數 |
|---|---:|
| 🟢 core | 0 |
| 🟡 satellite | 1 |
| 🔴 remove | 7 |
| ⚪ skipped (profile 不完整) | 0 |
| **總計** | **8** |

平均信心：**0.14**

## 🟡 衛星成分股（1 檔）

- 3049 精金 `pos=MAT_CHEM` （信心 0.60；產業板塊匹配 (ELEC_COMP)；未命中任何必要題材（個股題材 ['GLASS_GCS', 'LEO_SAT', '...）

## 🔴 應移除（7 檔）

| 代號 | 公司 | 移除原因 | 信心 |
|---|---|---|---:|
| 3481 | 群創 | 產業板塊匹配 (ELEC_COMP)；未命中任何必要題材（個股題材 ['FOPLP', 'GB300_RUBIN', 'GLASS_GCS'] vs 族群必要  | 0.25 |
| 5245 | 智晶 | C3: 位階「BRAND」在禁區（族群 forbidden=['ODM_SYS', 'BRAND', 'END_USER', 'DISTRIB', 'SVC_SAAS', 'CONNECTOR', 'PASSIVE', 'SUBSTRATE', 'THERMAL']） | 0.05 |
| 6854 | 錼創科技-KY創 | C3: 位階「PASSIVE」在禁區（族群 forbidden=['ODM_SYS', 'BRAND', 'END_USER', 'DISTRIB', 'SVC_SAAS', 'CONNECTOR', 'PASSIVE', 'SUBSTRATE', 'THERMAL']） | 0.05 |
| 6116 | 彩晶 | C3: 位階「PASSIVE」在禁區（族群 forbidden=['ODM_SYS', 'BRAND', 'END_USER', 'DISTRIB', 'SVC_SAAS', 'CONNECTOR', 'PASSIVE', 'SUBSTRATE', 'THERMAL']） | 0.05 |
| 2409 | 友達 | C3: 位階「BRAND」在禁區（族群 forbidden=['ODM_SYS', 'BRAND', 'END_USER', 'DISTRIB', 'SVC_SAAS', 'CONNECTOR', 'PASSIVE', 'SUBSTRATE', 'THERMAL']） | 0.05 |
| 4960 | 誠美材 | C3: 位階「PASSIVE」在禁區（族群 forbidden=['ODM_SYS', 'BRAND', 'END_USER', 'DISTRIB', 'SVC_SAAS', 'CONNECTOR', 'PASSIVE', 'SUBSTRATE', 'THERMAL']） | 0.05 |
| 8069 | 元太 | C3: 位階「ODM_SYS」在禁區（族群 forbidden=['ODM_SYS', 'BRAND', 'END_USER', 'DISTRIB', 'SVC_SAAS', 'CONNECTOR', 'PASSIVE', 'SUBSTRATE', 'THERMAL']） | 0.05 |
