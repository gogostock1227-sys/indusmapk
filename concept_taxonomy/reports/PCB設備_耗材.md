# PCB設備/耗材 — 驗證報告 v2

> 生成於 2026-04-25 17:07 UTC
> 三維 spec：allowed_segments=['ELEC_COMP'] / allowed_positions=['PCB_HDI', 'PCB_FPC', 'SUBSTRATE', 'MAT_CHEM'] / required_themes_any=['GB300_RUBIN', 'COWOS']

## 小結

| 判決 | 檔數 |
|---|---:|
| 🟢 core | 2 |
| 🟡 satellite | 5 |
| 🔴 remove | 0 |
| ⚪ skipped (profile 不完整) | 1 |
| **總計** | **8** |

平均信心：**0.66**

## 🟢 核心成分股（2 檔）

- **4760 勤凱科技** `pos=SUBSTRATE` `themes=['COWOS', 'N2_2NM', 'LEO_SAT']` （信心 1.00）
- **6667 信紘科** `pos=MAT_CHEM` `themes=['COWOS', 'LEO_SAT', 'ROBOTICS']` （信心 1.00）

## 🟡 衛星成分股（5 檔）

- 6438 迅得 `pos=FOUNDRY` （信心 0.65；產業板塊匹配 (ELEC_COMP)；必要題材交集：['COWOS', 'GB300_RUBIN']（強：['COWOS...）
- 6664 群翊 `pos=OSAT_ADV` （信心 0.65；產業板塊匹配 (ELEC_COMP)；必要題材交集：['COWOS', 'GB300_RUBIN']（強：['COWOS...）
- 4577 達航科技 `pos=TEST_INTF` （信心 0.65；產業板塊匹配 (ELEC_COMP)；必要題材交集：['COWOS']；位階「TEST_INTF」不在白名單（族群 al...）
- 6196 帆宣 `pos=FOUNDRY` （信心 0.65；產業板塊匹配 (ELEC_COMP)；必要題材交集：['COWOS', 'GB300_RUBIN']（強：['COWOS...）
- 3563 牧德 `pos=OSAT_ADV` （信心 0.65；產業板塊匹配 (ELEC_COMP)；必要題材交集：['COWOS']；位階「OSAT_ADV」不在白名單（族群 all...）

## ⚪ 跳過（profile 待補完）（1 檔）

- 3167 大量：profile 缺 segment='' 或 position='OSAT_ADV'
