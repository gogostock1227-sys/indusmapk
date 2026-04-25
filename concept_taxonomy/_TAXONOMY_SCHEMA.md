# 族群三維分類體系 (Taxonomy Schema)

> 為「族群統計網頁」定義可重用的標籤字典，避免標的歸類流於印象式。
> 每個標的必須同時擁有【產業板塊】+【供應鏈位階】+【核心驅動題材】三個維度的標籤。

最後更新：2026-04-25

---

## 維度 1：產業板塊 (Industry Segment)

對應 `site/industry_meta.py` 中的 `category` 欄位。13 大類覆蓋全市場：

| 板塊代碼 | 中文標籤 | 涵蓋範圍 |
|---|---|---|
| `AI_SEMI` | AI / 半導體 | DRAM、NAND、晶圓代工、ASIC、IP、先進封裝、測試、設備、材料 |
| `ELEC_COMP` | 電子零組件 | 連接器、被動元件、PCB、載板、機構件 |
| `NETCOM` | 網通 / 通訊 | 交換器、路由器、5G/6G 基地台、光通訊、低軌衛星 |
| `COMP_HW` | 電腦及週邊 | 伺服器組裝、PC、筆電、儲存、AI 伺服器準系統 |
| `POWER_GREEN` | 電源 / 綠能 | BBU、HVDC、UPS、太陽能、風電、儲能、氫能、充電樁 |
| `EV_AUTO` | 車用 / 電動車 | 車用半導體、ADAS、車用連接器、電池材料 |
| `DEFENSE` | 軍工 / 國防 | 軍機、軍艦、無人機、軍用通訊 |
| `MED_BIO` | 生技醫療 | 新藥、CDMO、醫材、智慧醫療 |
| `FIN` | 金融 | 銀行、保險、證券 |
| `CONSUMER` | 消費 / 民生 | 食品、零售、餐飲、觀光、寵物、銀髮 |
| `MATERIALS` | 塑化 / 原物料 | 石化、鋼鐵、水泥、紙業、輪胎、稀土 |
| `LOGISTICS` | 航運 / 物流 | 貨櫃、散裝、航空、陸運 |
| `SOFTWARE` | 軟體 / 服務 | SaaS、遊戲、影音、電商、資安 |

---

## 維度 2：供應鏈位階 (Supply Chain Position)

避免「物理元件」與「抽象技術」混淆。每個標的必須歸到最具體的位階。

### 半導體供應鏈
| 位階代碼 | 中文標籤 | 典型標的範例 |
|---|---|---|
| `IP` | IP / 矽智財 | M31、力旺、晶心科 |
| `IC_DESIGN` | IC 設計 / Fabless | 聯發科、聯詠、瑞昱 |
| `ASIC_SVC` | ASIC 設計服務 | 創意 (3443)、世芯-KY (3661)、智原 |
| `FOUNDRY` | 晶圓代工 | 台積電、聯電、力積電 (DRAM 代工) |
| `IDM_DRAM` | DRAM 製造 / IDM | 南亞科、華邦電、Micron、SK Hynix |
| `IDM_NAND` | NAND Flash 製造 | 旺宏、Samsung、Kioxia |
| `OSAT_ADV` | 先進封裝 (OSAT) | 日月光、力成 (HBM 封測)、京元電 |
| `OSAT_TRAD` | 一般封測 | 京元電 (CIS)、頎邦 (DDIC) |
| `TEST_INTF` | 測試介面 / 探針卡 / 測試座 | 穎崴、精測、雍智 |
| `TEST_SVC` | 測試代工 | 京元電子、旺矽 |
| `EQUIP` | 半導體設備 | 弘塑、辛耘、家登 |
| `MAT_WAFER` | 矽晶圓 / 上游材料 | 環球晶、台勝科、合晶 |
| `MAT_CHEM` | 半導體化學品 / 特用氣體 | 永光、長春石化、聯華氣體 |
| `SUBSTRATE` | 載板 / 基板 | 欣興、南電、景碩 |

### 電子零組件
| 位階代碼 | 中文標籤 | 典型標的範例 |
|---|---|---|
| `CONNECTOR` | 連接器 / Socket | 嘉澤、貿聯-KY、信邦 |
| `PASSIVE` | 被動元件 | 國巨、華新科、禾伸堂 |
| `PCB_HDI` | 高階 PCB / HDI | 健鼎、台光電、定穎投控 |
| `PCB_FPC` | 軟板 FPC | 臻鼎-KY、台郡、嘉聯益 |
| `THERMAL` | 散熱模組 | 雙鴻、奇鋐、建準 |
| `CHASSIS` | 機構件 / 機殼 | 鴻準、可成、勝利-KY |

### 系統/應用
| 位階代碼 | 中文標籤 | 典型標的範例 |
|---|---|---|
| `ODM_SYS` | 系統組裝 / ODM | 鴻海、廣達、緯創、緯穎 |
| `BRAND` | 品牌商 / OEM | 華碩、宏碁、技嘉 |
| `END_USER` | 終端應用商 | 飛捷 (POS)、永擎 (AI 伺服器整機) |
| `DISTRIB` | 通路 / 代理 | 大聯大、文曄、擎亞 |

### 電源/光通訊/其他
| 位階代碼 | 中文標籤 | 典型標的範例 |
|---|---|---|
| `POWER_MOD` | 電源模組 / BBU | 台達電、光寶科、康舒 |
| `OPTIC_MOD` | 光通訊模組 | 華星光、聯亞、聯鈞 |
| `OPTIC_COMP` | 光通訊元件 | 波若威、光環 |
| `SVC_SAAS` | 軟體 / SaaS | 訊聯、鼎新電腦 |

---

## 維度 3：核心驅動題材 (Core Driver Theme)

具體的技術 / 產品 / 事件層級，避免「AI」「半導體」這類抽象詞。

### 記憶體類
- `HBM3E_HBM4` — HBM3E (288GB) / HBM4 (384GB) 量產
- `DDR5_RISE` — DDR5 ASP 漲價週期
- `NICHE_DRAM` — 利基型 DRAM 缺貨 (DDR4 訂單能見度至 2028)
- `NAND_TIGHT` — NAND Flash 結構性短缺
- `aiDAPTIV` — NAND 模擬 DRAM 替代方案 (HBM 競品)
- `SOCAMM2` — 三星 SoCAMM2 模組導入 AI PC/伺服器

### 先進封裝類
- `COWOS` — CoWoS / CoWoS-L / CoWoS-S
- `COWOP` — 日月光自研類 CoWoS
- `SOIC_3D` — TSMC SoIC 3D 封裝
- `FOPLP` — 面板級扇出封裝
- `WOW` — Wafer on Wafer 晶圓堆疊

### AI 算力類
- `GB300_RUBIN` — NVIDIA GB300 / Rubin 平台
- `ASIC_TRAINIUM` — AWS Trainium 3/4
- `ASIC_TPU` — Google TPU v6/v7
- `ASIC_MTIA` — Meta MTIA
- `CSP_DEVERTICAL` — CSP 去輝達化自研晶片

### 光通訊 / 高速傳輸類
- `CPO_PHOTONIC` — 矽光子 CPO 共封裝光學
- `OPTIC_800G_1.6T` — 800G / 1.6T 光模組
- `SERDES_224G` — 224G SerDes 高速通道
- `VCSEL` — VCSEL 雷射晶片

### 系統 / 電源 / 散熱類
- `LIQUID_COOL` — 液冷散熱 / UQD 快接頭
- `HVDC_800V` — 800V HVDC 高壓直流
- `BBU` — 伺服器 BBU 備援電池

### 製程 / 材料類
- `N2_2NM` — 2nm 製程量產
- `N3_3NM` — 3nm 製程量產
- `EUV_RISE` — EUV 微影機放量
- `GLASS_GCS` — 玻璃基板 GCS

### 測試類
- `AI_GPU_TEST` — AI GPU 測試介面 / 探針卡升級
- `HBM_TEST` — HBM 專屬測試 (液冷測試座)

### 其他熱門題材（範例，非全部）
- `EV_BATTERY` — 電動車電池
- `LEO_SAT` — 低軌衛星
- `QUANTUM` — 量子電腦
- `ROBOTICS` — 人形機器人
- `MED_GLP1` — 減重新藥 GLP-1

---

## 標的歸類規則 (Classification Rules)

每個標的必須同時填寫四個欄位：

```json
{
  "ticker": "6239",
  "industry_segment": "AI_SEMI",
  "supply_chain_position": "OSAT_ADV",
  "core_themes": ["HBM3E_HBM4", "FOPLP", "DDR5_RISE"],
  "trading_logic": "Micron HBM 產能售罄至 2026 底，獨家封測訂單 + FOPLP 量產雙引擎"
}
```

### 規則
1. **`industry_segment` 單選**：每個標的歸一個產業板塊
2. **`supply_chain_position` 單選**：每個標的歸一個最具體的供應鏈位階
3. **`core_themes` 多選 (1-3 個)**：列出該標的真正受惠的核心題材，按重要性排序
4. **`trading_logic` 必填**：一句話寫清「資金為什麼買這檔」，要可操作（具體營收驅動 / EPS 推動 / 訂單能見度）

### 反模式（禁止）
- ❌ 把「物理元件 (連接器)」和「抽象技術 (高速傳輸)」混為一談
  - 例：3533 嘉澤 → 不能標 `core_themes: ["高速傳輸"]`，要標 `supply_chain_position: "CONNECTOR"` + `core_themes: ["GB300_RUBIN", "LIQUID_COOL", "SERDES_224G"]`
- ❌ 用「AI」「半導體」這種抽象詞當核心題材
- ❌ 為了塞進熱門族群而美化關聯度（例：把 8299 群聯標進 HBM 族群）

---

## 族群成分股驗證流程 (Validation Workflow)

每個族群定義（`concept_groups.py` 中的 list）必須通過三道驗證：

1. **Coverage 驗證**：該標的在 `My-TW-Coverage/Pilot_Reports/` 中的 coverage 是否真的提及該族群核心題材？
2. **題材一致性**：該標的的 `core_themes` 是否包含該族群的核心題材？
3. **位階合理性**：該標的的 `supply_chain_position` 是否在該族群的合理位階範圍內？

三項都通過 → 列為**核心成分股 (core)**
通過 1-2 項 → 列為**衛星成分股 (satellite)**
全部不通過 → **應移除**（重分類至更精確的族群）

---

## 後續批量處理計畫

- [x] HBM 高頻寬記憶體（樣本，已完成）
- [ ] CoWoS 先進封裝（高優先）
- [ ] AI 伺服器（高優先）
- [ ] Google TPU（高優先）
- [ ] ASIC/IP 矽智財（高優先）
- [ ] DDR5/LPDDR5 記憶體（高優先）
- [ ] NAND Flash/SSD 控制（高優先）
- [ ] Chiplet 小晶片（中優先）
- [ ] 矽光子 / CPO（中優先）
- [ ] 連接器 / 散熱 / 載板 / PCB（中優先）
- [ ] 其他 180 個族群（低優先，可批量 spawn agent 處理）
