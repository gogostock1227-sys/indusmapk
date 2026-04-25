# VCSEL 雷射 — 驗證報告 v2

> 生成於 2026-04-25 21:54 UTC
> 三維 spec：allowed_segments=['AI_SEMI', 'ELEC_COMP', 'NETCOM'] / allowed_positions=['IC_DESIGN', 'FOUNDRY', 'OPTIC_COMP', 'MAT_WAFER', 'OSAT_ADV', 'TEST_INTF'] / required_themes_any=['VCSEL', 'CPO_PHOTONIC']

## 小結

| 判決 | 檔數 |
|---|---:|
| 🟢 core | 2 |
| 🟡 satellite | 2 |
| 🔴 remove | 2 |
| ⚪ skipped (profile 不完整) | 0 |
| **總計** | **6** |

平均信心：**0.69**

## 🟢 核心成分股（2 檔）

- **3450 聯鈞** `pos=OSAT_ADV` `themes=['GB300_RUBIN', 'CPO_PHOTONIC', 'OPTIC_800G_1.6T']` （信心 1.00）
- **3081 聯亞** `pos=OPTIC_COMP` `themes=['CPO_PHOTONIC', 'VCSEL']` （信心 1.00）

## 🟡 衛星成分股（2 檔）

- 6451 訊芯-KY `pos=OSAT_TRAD` （信心 0.75；產業板塊匹配 (AI_SEMI)；必要題材交集：['CPO_PHOTONIC']；位階「OSAT_TRAD」不在白名單（...）
- 3437 榮創 `pos=FOUNDRY` （信心 0.70；產業板塊匹配 (ELEC_COMP)；未命中任何必要題材（個股題材 ['COWOS', 'GB300_RUBIN', '...）

## 🔴 應移除（2 檔）

| 代號 | 公司 | 移除原因 | 信心 |
|---|---|---|---:|
| 2444 | 兆勁 | C3: 位階「ODM_SYS」在禁區（族群 forbidden=['ODM_SYS', 'BRAND', 'END_USER', 'DISTRIB', 'SVC_SAAS', 'CONNECTOR', 'PASSIVE', 'PCB_HDI', 'SUBSTRATE', 'THERMAL']） | 0.55 |
| 3234 | 光環 | C3: 位階「ODM_SYS」在禁區（族群 forbidden=['ODM_SYS', 'BRAND', 'END_USER', 'DISTRIB', 'SVC_SAAS', 'CONNECTOR', 'PASSIVE', 'PCB_HDI', 'SUBSTRATE', 'THERMAL']） | 0.15 |
