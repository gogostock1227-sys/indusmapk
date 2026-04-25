# 族群三維分類重檢工程 — INDEX

> 對 `concept_groups.py` 中 190 個族群進行三維分類拆解（產業板塊 / 供應鏈位階 / 核心驅動題材）+ 重新驗證成分股歸屬。
>
> 啟動：2026-04-25
> 最後更新：2026-04-25

---

## 工程動機

### 問題診斷
1. **`concept_groups.py` 自動化合併失準**：`patch_concept_groups.py` 把 `My-TW-Coverage/themes/*.md` 的「上中下游 + 相關公司」無腦 append，沒有人工驗證關聯度
2. **`themes/*.md` 自身位階分類錯誤**：`scripts/build_themes.py` 自動生成的「上游/中游/下游」常顛倒（例如把伺服器主機板列為 HBM 上游、晶圓代工列為下游）
3. **原始族群定義粗糙**：早期人工編輯時把「凡是和某題材相關的個股」都塞進去，包含 NAND 控制器（8299 群聯）、POS 系統商（6206 飛捷）等明顯誤分類

### 目標
- 對所有 190 個族群套用統一的三維分類體系
- 移除誤分類的成分股，重分類至更精確的族群
- 每檔個股給出明確的「資金邏輯（Trading Logic）」
- 同步修正 `My-TW-Coverage/themes/*.md` 的位階分類

---

## 目錄結構

```
concept_taxonomy/
├── INDEX.md                  ← 本檔
├── _TAXONOMY_SCHEMA.md       ← 三維分類體系字典（13 板塊 / 27 位階 / 30+ 題材）
├── HBM.md                    ← HBM 樣本（已完成、已套用）
├── batch_1.md                ← AI 算力 12 群
├── batch_2.md                ← 半導體記憶體+材料+第三代 13 群
├── batch_3.md                ← 封測+設備+電子零組件+PCB 17 群
├── batch_4.md                ← 光通訊+網通+散熱電源+綠能 21 群
├── batch_5.md                ← 應用+消費電子+面板+軟體 25 群
├── batch_6.md                ← 車用機器人+國防+政策+利基零組件 30 群
├── batch_7.md                ← 生技醫療+寵物+運動 24 群
├── batch_8.md                ← 傳產+建材+觀光+食品民生 25 群
└── batch_9.md                ← 金融+電子通路+綠能環保+化工+航運 22 群
```

**Total: 1 樣本 + 9 batches = 190 個族群（含 HBM）**

---

## 三維分類體系摘要

### 維度 1：產業板塊 (Industry Segment) — 13 大類
`AI_SEMI` / `ELEC_COMP` / `NETCOM` / `COMP_HW` / `POWER_GREEN` / `EV_AUTO` / `DEFENSE` / `MED_BIO` / `FIN` / `CONSUMER` / `MATERIALS` / `LOGISTICS` / `SOFTWARE`

### 維度 2：供應鏈位階 (Supply Chain Position) — 27 細類
- 半導體：`IP` / `IC_DESIGN` / `ASIC_SVC` / `FOUNDRY` / `IDM_DRAM` / `IDM_NAND` / `OSAT_ADV` / `OSAT_TRAD` / `TEST_INTF` / `TEST_SVC` / `EQUIP` / `MAT_WAFER` / `MAT_CHEM` / `SUBSTRATE`
- 電子零組件：`CONNECTOR` / `PASSIVE` / `PCB_HDI` / `PCB_FPC` / `THERMAL` / `CHASSIS`
- 系統/應用：`ODM_SYS` / `BRAND` / `END_USER` / `DISTRIB`
- 電源/光通訊：`POWER_MOD` / `OPTIC_MOD` / `OPTIC_COMP` / `SVC_SAAS`

### 維度 3：核心驅動題材 (Core Driver Theme) — 30+ enums
記憶體、先進封裝、AI 算力、光通訊、系統電源散熱、製程材料、測試 等類別。詳見 `_TAXONOMY_SCHEMA.md`。

---

## 執行進度

| 階段 | 狀態 | 說明 |
|---|---|---|
| Phase 0 — 三維分類體系設計 | ✅ 完成 | 詳見 `_TAXONOMY_SCHEMA.md` |
| Phase 1 — HBM 樣本完整閉環 | ✅ 完成 | concept_groups.py + themes/HBM.md + concept_taxonomy/HBM.md 三檔同步修正 |
| Phase 2 — 9 個 P7 agent 平行拆解 189 群 | 🔄 執行中 | 每個 agent 寫 `batch_{N}.md`，預估 60-90 分鐘 |
| Phase 3 — 主對話整合 patch | ⏸️ 待 Phase 2 | 從 batch_*.md 提取 Python list 修正 concept_groups.py |
| Phase 4 — 修正 themes/*.md | ⏸️ 待 Phase 3 | CoWoS、AI 伺服器、ABF 載板、矽光子等 21 個主題檔同步修正 |
| Phase 5 — Sanity check + 完成報告 | ⏸️ 待 Phase 4 | python -c 載入驗證、site/build_site.py 重建驗證 |

---

## 整合 Phase 3 的策略

每個 `batch_{N}.md` 包含「修正後 concept_groups.py 的 list」Python 區塊，主對話的整合步驟：

1. **逐 batch 讀取**：依序 Read `batch_1.md` 到 `batch_9.md`
2. **提取 patch**：用正則或手動找出每個族群的 Python list 區塊
3. **應用 Edit**：用 Edit 工具替換 `concept_groups.py` 中對應的族群定義
4. **逐族群驗證**：每改 5-10 個族群執行 `python -c "from concept_groups import CONCEPT_GROUPS"` 確認載入正常
5. **記錄 changelog**：在 `concept_taxonomy/CHANGELOG.md` 紀錄每個族群的修改歷程

## 整合 Phase 4 的策略

`themes/*.md` 修正只針對「成分股有變動的主題」（例如 CoWoS、AI 伺服器、ABF 載板等與 batch 結果有衝突的）：

1. 列出 21 個 themes/*.md
2. 對每個對應到 concept_groups 的主題，按修正後的清單重組「上中下游」
3. 確保位階分類符合實際業務流（不要再出現「伺服器主機板列為 HBM 上游」的錯誤）

---

## 關鍵原則（從 HBM 樣本萃取）

1. **避免「物理元件」與「抽象技術」混淆**：例如「高速傳輸」不能直接標到嘉澤（連接器），要拆成 `supply_chain_position: CONNECTOR` + `core_themes: [SERDES_224G]`
2. **誠實判定 HBM/CoWoS 等熱門題材的關聯度**：不為了塞進熱門族群而美化（例如群聯不是 HBM 概念股）
3. **抽象詞禁用**：不能用「AI」「半導體」這種抽象詞當核心題材
4. **資金邏輯可操作**：trading_logic 必須具體（例如「Micron HBM 產能售罄至 2026 底」優於「AI 受惠」）

---

## 已知議題

### 重複族群（待合併）
- `造紙` vs `造紙/紙業`
- `輪胎/橡膠` vs `橡膠/輪胎原料`
- `CDMO/生技製造服務` vs `生技 CDMO`
- `智慧醫療/AI醫學` vs `AI 智慧醫療`
- `寵物/生活周邊` vs `寵物經濟` vs `動物保健/寵物醫療`
- `運動休閒` vs `健身/運動用品`

### 過時族群（建議刪除或合併）
- `防疫/口罩`（疫情題材已過時）
- `宅經濟/遠距`（疫情題材已過時）
- `龍年受惠/文創遊戲`（年度短線題材，可併入「文化傳媒/出版」或「遊戲股」）

### 雜類大族群（必須大幅瘦身）
- `其他（多元族群）` 73 檔 — 應該大量 reclassify
- `電子零組件/一般` 125 檔 — 屬於 PCB/連接器/被動的應移出
- `其他電子/工控` 45 檔 — 同上
- `中小型生技` 82 檔 — 區分「真正生技 vs 跨足生技的傳產轉投資」
- `電腦週邊/配件` 65 檔 — 屬於 PCB/連接器/散熱的應移出

### 命名議題
- `"DDR5\LPDDR5 記憶體"` 含反斜線（疑似筆誤，應為斜線）
- `"NAND Flash\SSD 控制"` 含反斜線（疑似筆誤）
- 修正命名會 break Backwards Compatibility，待用戶決定

---

## 引用 / 相關檔案

- `concept_groups.py` — 族群定義主檔（4130 行）
- `site/stock_highlights.py` — 個股人工標註（1068 行，含 ranking/tech/moat）
- `site/industry_meta.py` — 族群元資料（1941 行，含 category/desc/cagr）
- `site/build_site.py` — 網站建置主腳本（2631 行）
- `My-TW-Coverage/themes/*.md` — 主題供應鏈圖譜（21 檔）
- `My-TW-Coverage/Pilot_Reports/*/*_*.md` — 個股 coverage（1735+ 檔）
- `My-TW-Coverage/scripts/discover.py` — 反向搜尋工具
- `patch_concept_groups.py` — 原合併腳本（已知失準）
- `DIFF_MyTWC_vs_concept_groups.md` — 原差異盤點報告
