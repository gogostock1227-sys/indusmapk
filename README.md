# 台股產業寶 · Taiwan Industry Intelligence

台股產業族群深度資料庫 + 每日漲跌熱力圖 + 技術亮點排名。

- **176 題材** × **534 個股技術亮點（100% 覆蓋）**
- 產業地圖導覽、族群熱力圖、法人動向、相關題材
- 資料來源：[FinLab](https://www.finlab.tw/)
- 部署：Cloudflare Pages（`indusmapk.com`）

---

## 本地開發

```bat
REM 每日重建（抓 FinLab 新資料）
daily_build.bat

REM 開發用：用快取、跳過 FinLab 抓資料
python site\build_site.py --skip-finlab
```

輸出到 `site/dist/`，雙擊 `site/dist/index.html` 即可看。

## 部署流程

```
15:30 Windows 工作排程：盤後第一版
17:00 Windows 工作排程：主站完整版
21:30 Windows 工作排程：晚間補版
  → daily_build.bat quiet（FinLab → Python build → git push）
  → Cloudflare Pages 自動部署
  → https://indusmapk.com 更新
```

建立或更新這三個排程：

```bat
setup_daily_schedule.bat
```

## 檔案結構

```
族群統計網頁/
  concept_groups.py          # 題材 → 成分股對照表（176 題材）
  daily_build.bat            # 每日自動更新 + git push
  site/
    build_site.py            # 主建置腳本
    industry_meta.py         # 題材元資料
    stock_highlights.py      # 個股技術亮點
    templates/               # Jinja2 模板
    static/                  # CSS / JS
    dist/                    # 產生的靜態網站
  logs/                      # 建置 log
```

## 授權

僅供個人研究，非投資建議。
