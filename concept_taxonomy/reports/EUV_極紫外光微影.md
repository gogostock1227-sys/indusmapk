# EUV 極紫外光微影 — 驗證報告 v2

> 生成於 2026-04-25 17:07 UTC
> 三維 spec：allowed_segments=['AI_SEMI'] / allowed_positions=['EQUIP', 'MAT_CHEM', 'FOUNDRY'] / required_themes_any=['EUV_RISE', 'N2_2NM', 'N3_3NM']

## 小結

| 判決 | 檔數 |
|---|---:|
| 🟢 core | 3 |
| 🟡 satellite | 1 |
| 🔴 remove | 1 |
| ⚪ skipped (profile 不完整) | 0 |
| **總計** | **5** |

平均信心：**0.84**

## 🟢 核心成分股（3 檔）

- **2330 台積電** `pos=FOUNDRY` `themes=['N2_2NM', 'COWOS', 'CPO_PHOTONIC']` （信心 1.00）
- **3680 家登** `pos=FOUNDRY` `themes=['COWOS', 'SOIC_3D', 'N2_2NM']` （信心 1.00）
- **6823 濾能** `pos=FOUNDRY` `themes=['N2_2NM', 'N3_3NM', 'EUV_RISE']` （信心 1.00）

## 🟡 衛星成分股（1 檔）

- 6517 保勝光學 `pos=EQUIP` （信心 0.75；產業板塊不匹配（個股 ELEC_COMP vs 族群允許 ['AI_SEMI']）；必要題材交集：['EUV_RISE'...）

## 🔴 應移除（1 檔）

| 代號 | 公司 | 移除原因 | 信心 |
|---|---|---|---:|
| 6909 | 創控 | C3: 位階「ODM_SYS」在禁區（族群 forbidden=['IC_DESIGN', 'ODM_SYS', 'BRAND', 'END_USER', 'DISTRIB', 'SVC_SAAS', 'CONNECTOR', 'PASSIVE', 'PCB_HDI', 'SUBSTRATE', 'THERMAL']） | 0.45 |
