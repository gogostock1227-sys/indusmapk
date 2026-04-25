# 光通訊/CPO — 驗證報告 v2

> 生成於 2026-04-25 17:07 UTC
> 三維 spec：allowed_segments=['NETCOM', 'AI_SEMI'] / allowed_positions=['OPTIC_MOD', 'OPTIC_COMP', 'IC_DESIGN'] / required_themes_any=['CPO_PHOTONIC', 'OPTIC_800G_1.6T']

## 小結

| 判決 | 檔數 |
|---|---:|
| 🟢 core | 2 |
| 🟡 satellite | 6 |
| 🔴 remove | 5 |
| ⚪ skipped (profile 不完整) | 0 |
| **總計** | **13** |

平均信心：**0.56**

## 🟢 核心成分股（2 檔）

- **3081 聯亞** `pos=OPTIC_COMP` `themes=['CPO_PHOTONIC', 'VCSEL']` （信心 1.00）
- **4971 IET-KY** `pos=OPTIC_MOD` `themes=['CPO_PHOTONIC', 'OPTIC_800G_1.6T', 'VCSEL']` （信心 1.00）

## 🟡 衛星成分股（6 檔）

- 2455 全新 `pos=FOUNDRY` （信心 0.65；產業板塊匹配 (NETCOM)；必要題材交集：['CPO_PHOTONIC', 'OPTIC_800G_1.6T']（強...）
- 3105 穩懋 `pos=FOUNDRY` （信心 0.65；產業板塊匹配 (AI_SEMI)；必要題材交集：['CPO_PHOTONIC', 'OPTIC_800G_1.6T']（...）
- 4979 華星光 `pos=FOUNDRY` （信心 0.65；產業板塊匹配 (NETCOM)；必要題材交集：['CPO_PHOTONIC']；位階「FOUNDRY」不在白名單（族群 ...）
- 4977 眾達-KY `pos=THERMAL` （信心 0.65；產業板塊匹配 (NETCOM)；必要題材交集：['CPO_PHOTONIC', 'OPTIC_800G_1.6T']（強...）
- 3363 上詮 `pos=FOUNDRY` （信心 0.65；產業板塊匹配 (NETCOM)；必要題材交集：['CPO_PHOTONIC', 'OPTIC_800G_1.6T']（強...）
- 6426 統新 `pos=PASSIVE` （信心 0.65；產業板塊匹配 (NETCOM)；必要題材交集：['OPTIC_800G_1.6T']；位階「PASSIVE」不在白名單（...）

## 🔴 應移除（5 檔）

| 代號 | 公司 | 移除原因 | 信心 |
|---|---|---|---:|
| 3714 | 富采 | 產業板塊不匹配（個股 ELEC_COMP vs 族群允許 ['NETCOM', 'AI_SEMI']）；必要題材交集：['CPO_PHOTONIC', 'OPT | 0.40 |
| 3163 | 波若威 | 產業板塊匹配 (NETCOM)；未命中任何必要題材（個股題材 ['ASIC_TPU', 'GB300_RUBIN', 'HBM3E_HBM4'] vs 族群必要 | 0.25 |
| 6442 | 光聖 | 產業板塊匹配 (NETCOM)；未命中任何必要題材（個股題材 ['ASIC_TPU', 'ASIC_TRAINIUM', 'GB300_RUBIN'] vs 族 | 0.25 |
| 3491 | 昇達科 | 產業板塊匹配 (NETCOM)；未命中任何必要題材（個股題材 ['FOPLP', 'LEO_SAT'] vs 族群必要 ['CPO_PHOTONIC', 'OP | 0.25 |
| 6451 | 訊芯-KY | 產業板塊匹配 (AI_SEMI)；未命中任何必要題材（個股題材 ['COWOS', 'GB300_RUBIN', 'HBM3E_HBM4'] vs 族群必要 [ | 0.25 |
