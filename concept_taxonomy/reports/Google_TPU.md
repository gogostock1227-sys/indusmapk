# Google TPU — 驗證報告 v2

> 生成於 2026-04-25 21:54 UTC
> 三維 spec：allowed_segments=['AI_SEMI', 'ELEC_COMP'] / allowed_positions=['ASIC_SVC', 'FOUNDRY', 'IC_DESIGN', 'TEST_INTF', 'OSAT_ADV', 'SUBSTRATE', 'OPTIC_MOD'] / required_themes_any=['ASIC_TPU', 'COWOS', 'AI_GPU_TEST', 'CPO_PHOTONIC']

## 小結

| 判決 | 檔數 |
|---|---:|
| 🟢 core | 6 |
| 🟡 satellite | 3 |
| 🔴 remove | 1 |
| ⚪ skipped (profile 不完整) | 0 |
| **總計** | **10** |

平均信心：**0.82**

## 🟢 核心成分股（6 檔）

- **2330 台積電** `pos=FOUNDRY` `themes=['N2_2NM', 'COWOS', 'CPO_PHOTONIC']` （信心 1.00）
- **2454 聯發科** `pos=FOUNDRY` `themes=['DDR5_RISE', 'COWOS', 'GB300_RUBIN']` （信心 1.00）
- **3037 欣興** `pos=SUBSTRATE` `themes=['COWOS', 'GB300_RUBIN', 'ASIC_TPU']` （信心 1.00）
- **6515 穎崴** `pos=FOUNDRY` `themes=['HBM3E_HBM4', 'COWOS', 'GB300_RUBIN']` （信心 1.00）
- **6223 旺矽** `pos=FOUNDRY` `themes=['HBM3E_HBM4', 'COWOS', 'GB300_RUBIN']` （信心 1.00）
- **3363 上詮** `pos=FOUNDRY` `themes=['GB300_RUBIN', 'CPO_PHOTONIC', 'OPTIC_800G_1.6T']` （信心 0.85）

## 🟡 衛星成分股（3 檔）

- 3443 創意 `pos=IP` （信心 0.75；產業板塊匹配 (AI_SEMI)；必要題材交集：['COWOS']；位階「IP」不在白名單（族群 allowed=['A...）
- 6510 精測 `pos=MAT_WAFER` （信心 0.75；產業板塊匹配 (AI_SEMI)；必要題材交集：['COWOS']；位階「MAT_WAFER」不在白名單（族群 allo...）
- 3081 聯亞 `pos=OPTIC_COMP` （信心 0.75；產業板塊匹配 (AI_SEMI)；必要題材交集：['CPO_PHOTONIC']；位階「OPTIC_COMP」不在白名單...）

## 🔴 應移除（1 檔）

| 代號 | 公司 | 移除原因 | 信心 |
|---|---|---|---:|
| 2356 | 英業達 | 產業板塊不匹配（個股 COMP_HW vs 族群允許 ['AI_SEMI', 'ELEC_COMP']）；未命中任何必要題材（個股題材 ['GB300_RUBI | 0.10 |
