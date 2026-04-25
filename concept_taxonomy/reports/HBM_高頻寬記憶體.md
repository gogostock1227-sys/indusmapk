# HBM 高頻寬記憶體 — 驗證報告 v2

> 生成於 2026-04-25 17:07 UTC
> 三維 spec：allowed_segments=['AI_SEMI'] / allowed_positions=['IDM_DRAM', 'OSAT_ADV', 'TEST_INTF', 'MAT_WAFER', 'DISTRIB', 'ASIC_SVC', 'FOUNDRY'] / required_themes_any=['HBM3E_HBM4']

## 小結

| 判決 | 檔數 |
|---|---:|
| 🟢 core | 6 |
| 🟡 satellite | 3 |
| 🔴 remove | 0 |
| ⚪ skipped (profile 不完整) | 1 |
| **總計** | **10** |

平均信心：**0.82**

## 🟢 核心成分股（6 檔）

- **6239 力成** `pos=OSAT_ADV` `themes=['HBM3E_HBM4', 'FOPLP', 'DDR5_RISE']` （信心 1.00）
- **6770 力積電** `pos=FOUNDRY` `themes=['HBM3E_HBM4', 'WOW']` （信心 1.00）
- **3532 台勝科** `pos=FOUNDRY` `themes=['HBM3E_HBM4', 'DDR5_RISE', 'COWOS']` （信心 1.00）
- **6515 穎崴** `pos=FOUNDRY` `themes=['HBM3E_HBM4', 'COWOS', 'GB300_RUBIN']` （信心 1.00）
- **6510 精測** `pos=FOUNDRY` `themes=['HBM3E_HBM4', 'COWOS', 'GB300_RUBIN']` （信心 1.00）
- **3661 世芯-KY** `pos=ASIC_SVC` `themes=['HBM3E_HBM4', 'COWOS', 'ASIC_TRAINIUM']` （信心 1.00）

## 🟡 衛星成分股（3 檔）

- 2408 南亞科 `pos=IDM_DRAM` （信心 0.90；產業板塊匹配 (AI_SEMI)；必要題材交集：['HBM3E_HBM4']；位階「IDM_DRAM」在允許白名單內；位...）
- 3443 創意 `pos=IP` （信心 0.65；產業板塊匹配 (AI_SEMI)；必要題材交集：['HBM3E_HBM4']（強：['COWOS', 'HBM3E_HB...）
- 3711 日月光投控 `pos=FOUNDRY` （信心 0.60；產業板塊匹配 (AI_SEMI)；未命中任何必要題材（個股題材 ['COWOP', 'COWOS', 'GB300_RU...）

## ⚪ 跳過（profile 待補完）（1 檔）

- 8096 擎亞：profile 缺 segment='' 或 position='FOUNDRY'
