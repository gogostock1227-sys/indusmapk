# HBM 高頻寬記憶體 — 三維拆解與成分股重新驗證

> **樣本族群**，方法論示範。完成後可批量套用到其餘 189 個族群。
> 最後更新：2026-04-25

---

## 一、執行摘要 (Diagnosis)

### 現狀問題
| 項目 | 數值 |
|---|---:|
| 當前 `concept_groups.py` 列入檔數 | 16 |
| 真正核心 HBM 受惠標的 | 5 |
| 衛星受惠標的（間接） | 5 |
| **應移除（誤分類）** | **6** |

### 根因分析
1. **`patch_concept_groups.py` 無腦合併**：把 `My-TW-Coverage/themes/HBM.md` 的「上中下游」+「相關公司」直接 append 到 `concept_groups.py`，沒有人工驗證關聯度。
2. **HBM.md 自身位階分類錯誤**：把伺服器主機板廠（7711 永擎）列為「上游」、把晶圓代工廠（6770 力積電）列為「下游」，把網通代工廠（2444 兆勁）列為「下游」— 位階完全顛倒。
3. **原始 10 檔湊數**：早期人工編輯時，把「凡是和記憶體 / 測試 / 伺服器有關的個股」都塞進 HBM，包含 NAND 控制器（8299 群聯）、POS 系統商（6206 飛捷）等明顯無關標的。

### 整改方向
- 將 HBM 族群成分股從 16 檔精煉為 **10 檔**（5 核心 + 5 衛星）
- 移除的 6 檔重新分類到更精確的族群
- 同步修正 `My-TW-Coverage/themes/HBM.md` 的位階分類

---

## 二、16 檔三維拆解（完整表格）

| 代號 | 公司 | 板塊 | 供應鏈位階 | 核心題材 | HBM 關聯度 | 決策 |
|---|---|---|---|---|---|---|
| **2408** | 南亞科 | AI_SEMI | IDM_DRAM | DDR5_RISE / NICHE_DRAM / HBM3E_HBM4 | 中度 | 衛星保留 |
| **2344** | 華邦電 | AI_SEMI | IDM_DRAM | NICHE_DRAM / NOR Flash | 弱 | **移除→記憶體** |
| **8299** | 群聯 | AI_SEMI | IC_DESIGN | aiDAPTIV / NAND_TIGHT | 無關（競品） | **移除→NAND 控制** |
| **6770** | 力積電 | AI_SEMI | FOUNDRY | HBM3E_HBM4 / WOW / DRAM 代工 | 中度 | 核心保留 |
| **6239** | 力成 | AI_SEMI | OSAT_ADV | HBM3E_HBM4 / FOPLP / DDR5_RISE | 強 | 核心保留 |
| **3711** | 日月光 | AI_SEMI | OSAT_ADV | COWOS / COWOP / CPO_PHOTONIC | 中度 | 核心保留 |
| **3443** | 創意 | AI_SEMI | ASIC_SVC | ASIC_TRAINIUM / ASIC_TPU / COWOS | 弱 | 衛星保留（邊緣） |
| **3661** | 世芯-KY | AI_SEMI | ASIC_SVC | ASIC_TRAINIUM / N2_2NM / HBM3E_HBM4 | 弱 | 衛星保留 |
| **3532** | 台勝科 | AI_SEMI | MAT_WAFER | HBM3E_HBM4 / DDR5_RISE / 矽晶圓 | 強 | 核心保留 |
| **6510** | 精測 | AI_SEMI | TEST_INTF | AI_GPU_TEST / N3_3NM | 中度 | 衛星保留 |
| **6515** | 穎崴 | AI_SEMI | TEST_INTF | AI_GPU_TEST / HBM_TEST / LIQUID_COOL | 中度 | 衛星保留 |
| **8096** | 擎亞 | AI_SEMI | DISTRIB | HBM3E_HBM4 / SOCAMM2 | 強 | 核心保留 |
| **7711** | 永擎 | COMP_HW | END_USER | GB300_RUBIN / ASIC_TRAINIUM | 弱 | **移除→AI 伺服器** |
| **6206** | 飛捷 | COMP_HW | END_USER | POS 零售 / Berry AI | 無關 | **移除→另立族群** |
| **2444** | 兆勁 | NETCOM | ODM_SYS | Wi-Fi 7 / DRAM 模組 / VCSEL | 弱 | **移除→網通** |
| **3533** | 嘉澤 | ELEC_COMP | CONNECTOR | GB300_RUBIN / LIQUID_COOL / SERDES_224G | 弱 | **移除→連接器** |

---

## 三、核心 5 檔詳細拆解

### 6239 力成
- **產業板塊**：AI / 半導體
- **供應鏈位階**：先進封裝 / OSAT (`OSAT_ADV`)
- **核心題材**：HBM3E_HBM4、FOPLP、DDR5_RISE
- **資金邏輯**：Micron HBM 產能售罄至 2026 底，獨家封測訂單 + FOPLP 量產雙引擎，HPC/AI/ADAS 訂單能見度至 2027

### 8096 擎亞
- **產業板塊**：AI / 半導體
- **供應鏈位階**：通路 / 代理 (`DISTRIB`)
- **核心題材**：HBM3E_HBM4、SOCAMM2
- **資金邏輯**：Samsung 2026 HBM 位元出貨量 3 倍成長至 112 億 Gb，擎亞為台灣區獨家代理；SoCAMM2 切入 AI PC，法人估 EPS 回升至 2.5-3.5 元

### 6770 力積電
- **產業板塊**：AI / 半導體
- **供應鏈位階**：晶圓代工 (`FOUNDRY`)
- **核心題材**：HBM3E_HBM4、WOW、DRAM 代工
- **資金邏輯**：銅鑼 P5 廠以 18 億美元售予 Micron，竹科 P3 廠展開 HBM 後段製造合作；一次性出售獲利 142.3 億元 + 本業轉虧為盈

### 3711 日月光投控
- **產業板塊**：AI / 半導體
- **供應鏈位階**：先進封裝 / OSAT (`OSAT_ADV`)
- **核心題材**：COWOS、COWOP、CPO_PHOTONIC
- **資金邏輯**：台積電 CoWoS 外包 30%+ 由日月光承接，2026 LEAP 先進封裝營收上修至 32 億美元（年增 100%），HBM 與 GPU 共封受惠

### 3532 台勝科
- **產業板塊**：AI / 半導體
- **供應鏈位階**：矽晶圓 / 上游材料 (`MAT_WAFER`)
- **核心題材**：HBM3E_HBM4、DDR5_RISE、矽晶圓
- **資金邏輯**：HBM 與 DDR5 高階 DRAM 製造拉動 12 吋拋光晶圓需求，與 SUMCO 合資導入先進技術切入 HBM 認證

---

## 四、衛星 5 檔詳細拆解

### 2408 南亞科
- **板塊**：AI / 半導體 → **位階**：DRAM 製造 (`IDM_DRAM`)
- **核心題材**：DDR5_RISE、NICHE_DRAM、HBM3E_HBM4 (評估)
- **資金邏輯**：DDR5 季增 70% 直接受惠，HBM/CUBE 客製化記憶體為長期選項

### 6515 穎崴
- **板塊**：AI / 半導體 → **位階**：測試介面 (`TEST_INTF`)
- **核心題材**：AI_GPU_TEST、HBM_TEST、LIQUID_COOL
- **資金邏輯**：液冷測試座支援 3,500W@100°C，對應 HBM/SoIC 大封裝散熱挑戰；NVIDIA B300/Rubin 平台高功耗測試需求倍增

### 6510 精測
- **板塊**：AI / 半導體 → **位階**：測試介面 (`TEST_INTF`)
- **核心題材**：AI_GPU_TEST、N3_3NM
- **資金邏輯**：MEMS 探針卡為 NVIDIA、AMD、聯發科指定供應，AI 晶片測試複雜度推升 ASP

### 3661 世芯-KY
- **板塊**：AI / 半導體 → **位階**：ASIC 設計服務 (`ASIC_SVC`)
- **核心題材**：ASIC_TRAINIUM、N2_2NM、HBM3E_HBM4 (整合驗證)
- **資金邏輯**：Trainium 3 Q2 量產出貨 800-1000 萬顆，與 SK Hynix/Micron/Samsung HBM 團隊 2.5D 整合驗證；2028 年營收 1500 億目標

### 3443 創意 (邊緣)
- **板塊**：AI / 半導體 → **位階**：ASIC 設計服務 (`ASIC_SVC`)
- **核心題材**：ASIC_TRAINIUM、ASIC_TPU、COWOS
- **資金邏輯**：AWS Trainium 3 Q2 量產 + Google TPU v7e 設計案件，2026 營收成長 35-40%（HBM 為間接連動）

---

## 五、應移除的 6 檔（誤分類）

### 8299 群聯
- **誤分類原因**：NAND Flash 控制器廠，業務與 HBM 在技術上**對立而非互補**
- **重分類至**：`NAND Flash/SSD 控制` 族群（已存在）
- **核心題材**：aiDAPTIV (NAND 模擬 DRAM 替代 HBM)、NAND_TIGHT、Enterprise SSD
- **Coverage 驗證**：HBM 在報告中**完全未提及**

### 2344 華邦電
- **誤分類原因**：Niche DRAM/NOR Flash 廠，CUBE 客製化記憶體**定位介於 DRAM 與 HBM 之間**，主打 Edge AI 而非伺服器 HBM
- **重分類至**：`記憶體` 族群（已存在）+ 標 NICHE_DRAM
- **核心題材**：NICHE_DRAM、NOR Flash 短缺、CUBE 客製記憶體
- **資金邏輯**：路竹廠 DDR4 訂單能見度至 2028，缺口大到「不知道怎麼補」

### 7711 永擎
- **誤分類原因**：AI 伺服器主機板/整機廠，HBM 僅為**上游採購規格**，非核心競爭點。HBM.md 把它列為「上游」是分類顛倒。
- **重分類至**：`AI伺服器` 或 `伺服器準系統` 族群（兩者都已存在）
- **核心題材**：GB300_RUBIN、ASIC_TRAINIUM、輕資產 ODM Direct
- **資金邏輯**：B300 HGX 出貨超越 B200，ASIC 專案放量推升單季營收成長 20-26%

### 6206 飛捷
- **誤分類原因**：POS/Kiosk 系統廠，與 HBM **零關聯**。Coverage 完全未提及 HBM。
- **重分類至**：建議新增「智慧零售/POS」族群，或保留在「電腦及週邊設備」即可
- **核心題材**：POS 零售終端、McDonald's Kiosk、Berry AI 影像辨識
- **資金邏輯**：北美勞動力短缺驅動自助點餐/結帳機放量

### 2444 兆勁
- **誤分類原因**：Wi-Fi ODM 與 DRAM 模組代工，HBM 測試項目**僅為 Samsung 邊際業務**，毛利率 6% 反映典型 ODM 特性，不是 HBM 供應鏈財務結構
- **重分類至**：`網通` 族群（已存在）
- **核心題材**：Wi-Fi 7 路由器、DRAM 模組測試、VCSEL
- **資金邏輯**：Wi-Fi 7 + DDR5 模組需求復甦驅動毛利回升

### 3533 嘉澤
- **誤分類原因**：CPU/GPU Socket 與液冷快接頭廠，價值驅動來自「AI 伺服器主機板升級」而非 HBM 本身。Coverage **未直接提及 HBM**。
- **重分類至**：`連接器` 族群（已存在）+ `AI伺服器` 族群
- **核心題材**：GB300_RUBIN、LIQUID_COOL、SERDES_224G
- **資金邏輯**：液冷 UQD 單價高於傳統連接器數倍，2026 毛利率突破 52%，EPS 上看 95 元

---

## 六、修正後的 HBM 族群定義

### `concept_groups.py` 修正建議
```python
"HBM 高頻寬記憶體": [
    # ── 核心 (Tier 1) — 直接受惠 HBM 出貨 ──
    "6239",  # 力成（Micron HBM 獨家封測）
    "8096",  # 擎亞（Samsung HBM 台灣獨家代理）
    "6770",  # 力積電（HBM 後段代工 / Micron 合作）
    "3711",  # 日月光投控（CoWoS 含 HBM 共封）
    "3532",  # 台勝科（HBM 上游矽晶圓）
    # ── 衛星 (Tier 2) — 間接受惠 ──
    "2408",  # 南亞科（DRAM 母廠 / HBM 排擠效應 / 評估介入 HBM/CUBE）
    "6515",  # 穎崴（HBM 測試座 / 液冷 socket）
    "6510",  # 精測（高階探針卡 / AI 晶片測試）
    "3661",  # 世芯-KY（Trainium 3/4 + HBM3E/4 整合驗證）
    "3443",  # 創意（CSP ASIC + CoWoS / 邊緣相關）
],
```

### 移除清單（6 檔，重分類至其他族群）
| 代號 | 從 HBM 移除 | 重分類至 |
|---|---|---|
| 8299 | ✓ | `NAND Flash/SSD 控制` |
| 2344 | ✓ | `記憶體` (Niche DRAM 標籤) |
| 7711 | ✓ | `AI伺服器` / `伺服器準系統` |
| 6206 | ✓ | （從 HBM 移除即可） |
| 2444 | ✓ | `網通` |
| 3533 | ✓ | `連接器` + `AI伺服器` |

---

## 七、`HBM.md` 主題圖譜修正建議

當前 HBM.md 的「上中下游」分類完全顛倒（伺服器主機板列為上游、晶圓代工列為下游）。建議重寫如下：

```markdown
# HBM 高頻寬記憶體

> High Bandwidth Memory，AI 加速器必備的高速堆疊記憶體

**涵蓋公司數:** 10（精煉版，從 16 檔去蕪存菁）

**相關主題:** [[CoWoS]] | [[AI 伺服器]] | [[DRAM]] | [[ASIC]]

---

## 上游 (材料 / 設計)
- **3532 台勝科** — 矽晶圓供應 (Semiconductor Materials)
- **3443 創意** — ASIC + HBM IP 整合 (Semiconductors)
- **3661 世芯-KY** — ASIC + HBM 2.5D 整合驗證 (Semiconductors)

## 中游 (製造 / 封測 / 測試)
- **2408 南亞科** — DRAM 製造 / 評估介入 HBM (Semiconductors)
- **6770 力積電** — HBM 後段晶圓代工 (Semiconductors)
- **6239 力成** — HBM 封測 (Micron 獨家) (Semiconductors)
- **3711 日月光投控** — CoWoS 含 HBM 共封 (Semiconductors)
- **6515 穎崴** — HBM 液冷測試座 (Semiconductors)
- **6510 精測** — 高階探針卡 (Semiconductor Equipment)

## 下游 (通路 / 應用)
- **8096 擎亞** — Samsung HBM 台灣獨家代理 (Semiconductors)

## 應用端（不列為 HBM 成分股，但是 HBM 重要客戶）
- 2356 英業達、2376 技嘉、2382 廣達、3231 緯創、6669 緯穎 — AI 伺服器組裝
- 7711 永擎 — AI 伺服器整機（建議移到 [[AI 伺服器]] 主題）
```

---

## 八、JSON 結構化資料

```json
{
  "group_id": "HBM 高頻寬記憶體",
  "group_meta": {
    "industry_category": "AI / 半導體",
    "narrative": "AI 加速器必備的高速堆疊記憶體，2026 HBM3E/HBM4 量產，三大廠 (SK Hynix / Samsung / Micron) 壟斷產能。台廠卡位封測、測試、通路、矽晶圓上游。",
    "cagr": "50%",
    "market_size_usd": "35B"
  },
  "diagnosis": {
    "current_count": 16,
    "validated_core": 5,
    "validated_satellite": 5,
    "should_remove": 6,
    "summary": "原始 16 檔中 6 檔屬誤分類（NAND 控制、POS 系統、網通、連接器、伺服器整機等），應移除並重分類；保留的 10 檔再分為核心 5 檔與衛星 5 檔。"
  },
  "constituents": [
    {
      "ticker": "6239",
      "name": "力成",
      "tier": "core",
      "industry_segment": "AI_SEMI",
      "supply_chain_position": "OSAT_ADV",
      "core_themes": ["HBM3E_HBM4", "FOPLP", "DDR5_RISE"],
      "hbm_relevance": "強",
      "trading_logic": "Micron HBM 產能售罄至 2026 底，獨家封測訂單 + FOPLP 量產雙引擎，HPC/AI/ADAS 訂單能見度至 2027"
    },
    {
      "ticker": "8096",
      "name": "擎亞",
      "tier": "core",
      "industry_segment": "AI_SEMI",
      "supply_chain_position": "DISTRIB",
      "core_themes": ["HBM3E_HBM4", "SOCAMM2"],
      "hbm_relevance": "強",
      "trading_logic": "Samsung 2026 HBM 位元出貨量 3 倍成長至 112 億 Gb，擎亞為台灣區獨家代理；SoCAMM2 切入 AI PC，法人估 EPS 回升至 2.5-3.5 元"
    },
    {
      "ticker": "6770",
      "name": "力積電",
      "tier": "core",
      "industry_segment": "AI_SEMI",
      "supply_chain_position": "FOUNDRY",
      "core_themes": ["HBM3E_HBM4", "WOW", "DRAM 代工"],
      "hbm_relevance": "中度",
      "trading_logic": "銅鑼 P5 廠以 18 億美元售予 Micron，竹科 P3 廠展開 HBM 後段製造合作；一次性出售獲利 142.3 億元 + 本業轉虧為盈"
    },
    {
      "ticker": "3711",
      "name": "日月光投控",
      "tier": "core",
      "industry_segment": "AI_SEMI",
      "supply_chain_position": "OSAT_ADV",
      "core_themes": ["COWOS", "COWOP", "CPO_PHOTONIC"],
      "hbm_relevance": "中度",
      "trading_logic": "台積電 CoWoS 外包 30%+ 由日月光承接，2026 LEAP 先進封裝營收上修至 32 億美元（年增 100%），HBM 與 GPU 共封受惠"
    },
    {
      "ticker": "3532",
      "name": "台勝科",
      "tier": "core",
      "industry_segment": "AI_SEMI",
      "supply_chain_position": "MAT_WAFER",
      "core_themes": ["HBM3E_HBM4", "DDR5_RISE", "矽晶圓"],
      "hbm_relevance": "強",
      "trading_logic": "HBM 與 DDR5 高階 DRAM 製造拉動 12 吋拋光晶圓需求，與 SUMCO 合資導入先進技術切入 HBM 認證"
    },
    {
      "ticker": "2408",
      "name": "南亞科",
      "tier": "satellite",
      "industry_segment": "AI_SEMI",
      "supply_chain_position": "IDM_DRAM",
      "core_themes": ["DDR5_RISE", "NICHE_DRAM", "HBM3E_HBM4"],
      "hbm_relevance": "中度",
      "trading_logic": "DDR5 季增 70% 直接受惠 HBM 排擠 DRAM 產能；HBM/CUBE 客製化記憶體為長期選項"
    },
    {
      "ticker": "6515",
      "name": "穎崴",
      "tier": "satellite",
      "industry_segment": "AI_SEMI",
      "supply_chain_position": "TEST_INTF",
      "core_themes": ["AI_GPU_TEST", "HBM_TEST", "LIQUID_COOL"],
      "hbm_relevance": "中度",
      "trading_logic": "液冷測試座支援 3,500W@100°C，對應 HBM/SoIC 大封裝散熱；NVIDIA B300/Rubin 高功耗測試需求倍增"
    },
    {
      "ticker": "6510",
      "name": "精測",
      "tier": "satellite",
      "industry_segment": "AI_SEMI",
      "supply_chain_position": "TEST_INTF",
      "core_themes": ["AI_GPU_TEST", "N3_3NM"],
      "hbm_relevance": "中度",
      "trading_logic": "MEMS 探針卡為 NVIDIA、AMD、聯發科指定供應，AI 晶片測試複雜度推升 ASP，毛利率穩健 55%+"
    },
    {
      "ticker": "3661",
      "name": "世芯-KY",
      "tier": "satellite",
      "industry_segment": "AI_SEMI",
      "supply_chain_position": "ASIC_SVC",
      "core_themes": ["ASIC_TRAINIUM", "N2_2NM", "HBM3E_HBM4"],
      "hbm_relevance": "弱",
      "trading_logic": "Trainium 3 Q2 量產出貨 800-1000 萬顆，與 SK Hynix/Micron/Samsung HBM 團隊 2.5D 整合驗證；2028 營收 1500 億目標"
    },
    {
      "ticker": "3443",
      "name": "創意",
      "tier": "satellite",
      "industry_segment": "AI_SEMI",
      "supply_chain_position": "ASIC_SVC",
      "core_themes": ["ASIC_TRAINIUM", "ASIC_TPU", "COWOS"],
      "hbm_relevance": "弱（邊緣）",
      "trading_logic": "AWS Trainium 3 Q2 量產 + Google TPU v7e 設計案件，2026 營收成長 35-40%（HBM 為間接連動）"
    }
  ],
  "removed_with_reclassification": [
    {
      "ticker": "8299",
      "name": "群聯",
      "removal_reason": "NAND 控制器廠，aiDAPTIV+ 是把 NAND 模擬成 DRAM 的 HBM 替代品而非互補",
      "reclassify_to": "NAND Flash/SSD 控制",
      "core_themes_in_new_group": ["aiDAPTIV", "NAND_TIGHT", "Enterprise SSD"]
    },
    {
      "ticker": "2344",
      "name": "華邦電",
      "removal_reason": "Niche DRAM/NOR Flash 廠，CUBE 客製化記憶體定位介於 DRAM 與 HBM 之間，主打 Edge AI 非伺服器 HBM",
      "reclassify_to": "記憶體",
      "core_themes_in_new_group": ["NICHE_DRAM", "NOR Flash 短缺", "CUBE"]
    },
    {
      "ticker": "7711",
      "name": "永擎",
      "removal_reason": "AI 伺服器主機板/整機廠，HBM 僅為上游採購規格，非核心競爭點",
      "reclassify_to": "AI伺服器 + 伺服器準系統",
      "core_themes_in_new_group": ["GB300_RUBIN", "ASIC_TRAINIUM"]
    },
    {
      "ticker": "6206",
      "name": "飛捷",
      "removal_reason": "POS/Kiosk 系統廠，與 HBM 完全無關。Coverage 未提及 HBM 任何字眼",
      "reclassify_to": "（從 HBM 移除即可，可考慮新增智慧零售族群）",
      "core_themes_in_new_group": ["POS 零售", "McDonald's Kiosk", "Berry AI"]
    },
    {
      "ticker": "2444",
      "name": "兆勁",
      "removal_reason": "Wi-Fi ODM + DRAM 模組代工，HBM 測試僅為 Samsung 邊際業務，毛利率 6% 反映 ODM 特性",
      "reclassify_to": "網通",
      "core_themes_in_new_group": ["Wi-Fi 7", "DRAM 模組", "VCSEL"]
    },
    {
      "ticker": "3533",
      "name": "嘉澤",
      "removal_reason": "CPU/GPU Socket + 液冷快接頭廠，價值驅動來自 AI 伺服器主機板升級而非 HBM",
      "reclassify_to": "連接器 + AI伺服器",
      "core_themes_in_new_group": ["GB300_RUBIN", "LIQUID_COOL", "SERDES_224G"]
    }
  ]
}
```

---

## 九、後續批量處理建議

### 階段 A（高優先，一週內完成）
建議先處理與 HBM 強連動的 6 個族群：
1. CoWoS 先進封裝（與 HBM 共封）
2. AI 伺服器（HBM 下游應用）
3. ASIC/IP 矽智財（搭配 HBM 設計）
4. Google TPU、輝達概念股、Chiplet 小晶片

### 階段 B（中優先，兩週內完成）
記憶體相關 + 半導體核心 10 個族群：
- 記憶體、DDR5/LPDDR5、NAND Flash/SSD、半導體設備、矽光子、CPO、2 奈米、晶圓代工成熟製程、ABF 載板、特殊氣體

### 階段 C（低優先，可批量 spawn agent）
其他 170+ 個族群按產業板塊分批處理。

### 處理流程
每個族群執行下列 SOP：
1. 讀取 `concept_groups.py` 當前清單 + `industry_meta.py` metadata
2. 平行 spawn Explore agent 讀取 16-20 檔 coverage 摘要
3. 套用三維分類體系產出 `concept_taxonomy/{族群}.md`（仿本檔格式）
4. 修正 `concept_groups.py` 與 `My-TW-Coverage/themes/{主題}.md`
5. 執行 `python site/build_site.py` 重建網站驗證
