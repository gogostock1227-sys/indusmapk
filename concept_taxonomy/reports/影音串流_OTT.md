# 影音串流/OTT — 驗證報告 v2

> 生成於 2026-04-25 17:07 UTC
> 三維 spec：allowed_segments=['SOFTWARE', 'CONSUMER'] / allowed_positions=['SVC_SAAS', 'BRAND'] / required_themes_any=[]

## 小結

| 判決 | 檔數 |
|---|---:|
| 🟢 core | 3 |
| 🟡 satellite | 2 |
| 🔴 remove | 2 |
| ⚪ skipped (profile 不完整) | 0 |
| **總計** | **7** |

平均信心：**0.74**

## 🟢 核心成分股（3 檔）

- **6542 隆中** `pos=SVC_SAAS` `themes=[]` （信心 1.00）
- **3293 鈊象** `pos=SVC_SAAS` `themes=[]` （信心 1.00）
- **6180 橘子** `pos=SVC_SAAS` `themes=[]` （信心 1.00）

## 🟡 衛星成分股（2 檔）

- 3045 台灣大 `pos=BRAND` （信心 0.75；產業板塊不匹配（個股 NETCOM vs 族群允許 ['SOFTWARE', 'CONSUMER']）；必要題材交集：[...）
- 8487 愛爾達-創 `pos=ODM_SYS` （信心 0.65；產業板塊匹配 (SOFTWARE)；必要題材交集：[]；位階「ODM_SYS」不在白名單（族群 allowed=['SV...）

## 🔴 應移除（2 檔）

| 代號 | 公司 | 移除原因 | 信心 |
|---|---|---|---:|
| 2485 | 兆赫 | 產業板塊不匹配（個股 NETCOM vs 族群允許 ['SOFTWARE', 'CONSUMER']）；必要題材交集：[]；位階「ODM_SYS」不在白名單（族 | 0.40 |
| 4904 | 遠傳 | 產業板塊不匹配（個股 NETCOM vs 族群允許 ['SOFTWARE', 'CONSUMER']）；必要題材交集：[]；位階「ODM_SYS」不在白名單（族 | 0.40 |
