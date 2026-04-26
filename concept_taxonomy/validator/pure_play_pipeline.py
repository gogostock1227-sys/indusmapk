"""
Phase 6 — Pure-Play 嚴格驗證 orchestrator

雙閥仲裁（先做最嚴 2 票；票 3/4 留 Phase 7）：
  票 1: spec hard_fail（forbidden_position / forbidden_theme 不命中）—— 重用 checks.py
  票 2: dominance（業務簡介第一段 keyword 位置 + 角色排除）—— dominance.py

判決規則：
  票 2 STRONG_PASS                → core
  票 2 WEAK_PASS + 票 1 過         → satellite
  票 2 FAIL                       → remove（附 reclassify 建議）
  票 2 ABSTAIN（Coverage 不存在）  → keep_pending（保守保留待人工判）

入口：
  python -m concept_taxonomy.validator.pure_play_pipeline                 # dry run，印小結
  python -m concept_taxonomy.validator.pure_play_pipeline --apply         # 寫回 concept_groups.py（.bak6）+ build site
  python -m concept_taxonomy.validator.pure_play_pipeline --group HBM     # 單群跑 demo
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

TAXONOMY_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = TAXONOMY_DIR.parent
TARGET = PROJECT_ROOT / "concept_groups.py"

sys.path.insert(0, str(TAXONOMY_DIR))
from validator.dominance import score_dominance, score_customer_dominance, DominanceVote  # noqa: E402


# 客戶概念股群 → 客戶 keywords 映射（dominance 客戶模式）
CUSTOMER_KEYWORD_MAP: dict[str, list[str]] = {
    "蘋果概念股": ["Apple", "蘋果", "iPhone", "iPad", "MacBook", "Apple Watch", "AirPods", "Cupertino"],
    "輝達概念股": ["NVIDIA", "輝達", "GB200", "GB300", "Blackwell", "Rubin", "Hopper", "H100", "H200", "B100", "B200", "DGX", "HGX", "CUDA"],
    "特斯拉概念股": ["Tesla", "特斯拉", "Cybertruck", "Model 3", "Model Y", "Model S", "Model X", "Elon Musk", "Optimus", "Dojo"],
    # "Google TPU" 移到 permissive — 主要客戶段很少直接寫 Google/TPU（因 NDA / 都 via 台積驗證採用），且 P9 已精修為 10 檔
    # "Google TPU": ["Google TPU", "TPU v5", "TPU v6", "TPU v7", "Trillium", "Google Cloud", "Alphabet"],
    "AI伺服器": ["AI 伺服器", "AI Server", "GB200", "GB300", "DGX", "HGX", "B200", "Rubin"],
    "伺服器準系統": ["AI 伺服器", "Server Barebone", "GB200", "DGX", "HGX"],
    "AI基礎設施/資料中心": ["AI 伺服器", "資料中心", "Datacenter", "GB200", "Hyperscaler"],
    "資料中心": ["資料中心", "Datacenter", "Hyperscaler", "AWS", "Azure", "GCP", "Meta"],
    "電動車": ["電動車", "EV", "BEV", "Tesla", "BYD", "Lucid", "Rivian", "BMW", "Mercedes"],
    "電動車供應鏈": ["電動車", "EV", "Tesla", "Volvo", "BMW", "Mercedes", "Porsche", "Ford", "GM"],
    "汽車零件/售後": ["售後", "Aftermarket", "汽車零件", "OEM 車廠"],
    # 通路 / 雜類 / 工控 / 周邊 — 主要客戶段不適用 keyword 模式，退 permissive
    # "電子通路": ["半導體通路", "電子通路", "代理商"],
    # "電子零組件/一般": ["電子零組件"],
    # "其他電子/工控": ["工業電腦", "工控"],
    # "電腦週邊/配件": ["電腦週邊", "鍵盤", "滑鼠", "鏡頭", "PC 周邊"],
    "其他（多元族群）": [],   # 雜類，跳過
    "投資控股/租賃": ["控股", "租賃", "融資"],
    "川普概念/關稅戰": ["關稅", "Trump", "美中貿易戰"],
    "日圓貶值受惠/台日合作": ["日圓", "日本", "台日"],
    "美國製造回流/晶片法案": ["美國製造", "CHIPS Act", "Reshoring", "回流"],
    "印度產能/印度概念": ["印度", "India"],
    "新南向/東南亞產能": ["越南", "印尼", "泰國", "東南亞", "新南向"],
    "重建/災後/基礎建設": ["災後", "基礎建設", "重建"],
    "資訊服務/IT服務": ["IT 服務", "資訊服務", "SI"],
    "雲端服務/SaaS": ["SaaS", "雲端服務", "Cloud"],
    "智慧家庭/Matter": ["智慧家庭", "Matter", "Smart Home"],
    "穿戴/智慧眼鏡": ["穿戴", "智慧眼鏡", "Wearable"],
    "AI 眼鏡 / Meta Ray-Ban": ["AI 眼鏡", "Ray-Ban", "Meta Glasses", "Smart Glasses"],
    "金融股": ["銀行", "保險", "證券"],
    "金融": ["銀行", "保險", "證券", "金控"],
    "化工/染料/特化": ["化工", "化學品", "染料", "特化"],
    "紡織/機能布": ["紡織", "機能布", "成衣"],
    "居家修繕/家居用品": ["居家", "家居", "家具"],
    "工業電腦/IPC": ["工業電腦", "IPC"],
}


def parse_concept_groups() -> dict[str, list[tuple[str, str]]]:
    """回 {group: [(ticker, original_comment), ...]}。

    注意：list 內 inline comment 可能含 `[核心]`/`[衛星]` 等方括號，故 block
    終止改用 `\n    ],`（必在獨立行 4 空格縮排），避免被 inline `]` 誤截斷。
    """
    src = TARGET.read_text(encoding="utf-8")
    pattern = re.compile(r'"([^"]+?)"\s*:\s*\[(.*?\n    \]),', re.DOTALL)
    result = {}
    for m in pattern.finditer(src):
        group = m.group(1)
        if group == "_meta":
            continue
        body = m.group(2)
        items = []
        for tk_m in re.finditer(r'"(\d{4,5})"\s*,?\s*(?:#\s*([^\n]*))?', body):
            ticker = tk_m.group(1)
            comment = (tk_m.group(2) or "").strip()
            items.append((ticker, comment))
        if items or group in {"防疫/口罩", "宅經濟/遠距", "高速傳輸"}:
            result[group] = items
    return result


def load_finlab_names() -> dict[str, str]:
    """從 finlab snapshot 拿 ticker → 真名字 mapping。"""
    snapshot_path = TAXONOMY_DIR / "validator" / "cache" / "finlab_snapshot.parquet"
    if not snapshot_path.exists():
        return {}
    import pandas as pd
    df = pd.read_parquet(snapshot_path)
    return df.set_index("symbol")["公司簡稱"].to_dict()


# 「客戶概念股 / 雜類 / 通路」這類用主業第一句 dominance 不適用 → permissive 處理
# 原因：個股主業是 EMS/封測/光學/光電，業務簡介第一句不會直接提 Apple/NVIDIA
# 後續 Phase 7 應改用「主要客戶段落」keyword 匹配
INDIRECT_BENEFIT_GROUPS = {
    # 客戶概念股（看下游客戶非主業）
    "輝達概念股", "蘋果概念股", "特斯拉概念股", "Google TPU",
    # 通路 / 雜類
    "電子通路", "電子零組件/一般", "其他電子/工控", "電腦週邊/配件",
    "其他（多元族群）", "投資控股/租賃",
    # 政策概念
    "川普概念/關稅戰", "日圓貶值受惠/台日合作",
    "美國製造回流/晶片法案", "印度產能/印度概念",
    "新南向/東南亞產能", "重建/災後/基礎建設",
    # 系統 / 應用群（非單一 specialty）
    "AI伺服器", "伺服器準系統", "AI基礎設施/資料中心", "資料中心",
    "汽車零件/售後", "電動車", "電動車供應鏈",
    "資訊服務/IT服務", "雲端服務/SaaS",
    "智慧家庭/Matter", "穿戴/智慧眼鏡", "AI 眼鏡 / Meta Ray-Ban",
    # 大類傳產（dominance keyword 太通用）
    "金融股", "金融", "化工/染料/特化", "紡織/機能布",
    "居家修繕/家居用品", "工業電腦/IPC",
    # Phase 9：上面 51 群移出 INDIRECT（重新嚴格 prune），靠 KEYWORD_EXPANSIONS 同義詞讓 dominance 有命中
    # 這些群已在 KEYWORD_EXPANSIONS 補強，理論上能跑出合理 keep
}

# 自動 extract 自 site/industry_meta.py 的 desc（67 群，2026-04-26 sync_ground_truth.py 跑出）
# 確保「ai 產業分析提到的龍頭」一定在成分股 list 中
AUTO_GROUND_TRUTH_FROM_DESC = {
    "2奈米先進製程": ['2330', '3037', '3443', '3661', '8046'],
    "5G 通訊": ['2412', '3045', '4904'],
    "5G/6G 基地台": ['5388', '6285'],
    "ABF載板": ['3037', '3189', '8046'],
    "AI 智慧醫療": ['4164', '3034', '4175', '4743'],
    "AI 眼鏡 / Meta Ray-Ban": ['8464'],
    "CDMO/生技製造服務": ['6589', '6472'],
    "CPU 概念股": ['6415', '3711', '2308', '2357', '2376', '2377', '3017', '3037', '3189', '3515', '3533', '5269', '8046', '3324', '5274'],
    "CoWoS先進封裝": ['2330'],
    "DDR5/LPDDR5 記憶體": ['2344', '2408'],
    "EUV 極紫外光微影": ['2330', '2338'],
    "Flexible PCB/軟板": ['6153', '3044', '6269'],
    "Google TPU": ['3661', '3443', '6559'],
    "HBM 高頻寬記憶體": ['5007', '4923'],
    "HVDC/直流電力": ['2308', '1503'],
    "IC設計": ['2454', '2379', '3034'],
    "LED/光電": ['3437', '3714'],
    "NAND Flash/SSD 控制": ['8299'],
    "OLED/Micro LED": ['2409', '3481'],
    "PC/電競品牌": ['2353', '2357', '2376', '2377'],
    "PCB設備/耗材": ['6438', '4577', '6664'],
    "VCSEL 雷射": ['3081'],
    "交通運輸/物流": ['2633', '2618', '2642', '2640', '2610'],
    "伺服器準系統": ['2382', '6669'],
    "保健食品/機能食品": ['1707', '1215', '8436'],
    "健身/運動用品": ['9914', '1736', '9921'],
    "儲能系統/BESS": ['6806', '2308', '1519'],
    "充電樁/充電服務": ['1513', '2308', '1519'],
    "光學精密元件": ['3406', '3504', '2374', '3019'],
    "光學薄膜": ['8215'],
    "光學鏡片/鏡頭": ['3008'],
    "光通訊細分": ['3152', '3234'],
    "功率半導體 IC": ['6138', '6435', '6415'],
    "動物保健/寵物醫療": ['6968', '8436'],
    "化工/染料/特化": ['1712', '1717', '1722', '1723'],
    "半導體設備": ['2330'],
    "半導體類比IC": ['3438', '8081', '6138', '6435'],
    "印度產能/印度概念": ['2382', '3231', '4938'],
    "原料藥/化學藥": ['1789', '4119', '4123'],
    "台積電供應鏈": ['2330'],
    "固態電池": ['4721', '3211', '6121'],
    "基因/生技檢測": ['1784', '4195'],
    "塑膠射出/模具": ['1308', '4426'],
    "太陽能/光電板": ['3576', '6443', '6244'],
    "安全監控/影像監控": ['3356'],
    "寵物/生活周邊": ['6968', '1434'],
    "寵物經濟": ['1219', '1227'],
    "射頻 RF/PA": ['8086'],
    "居家修繕/家居用品": ['9911', '9924', '9934', '6195'],
    "川普概念/關稅戰": ['1325'],
    "工具機": ['1530', '1583', '2049', '4526'],
    "工業電腦/IPC": ['2395', '6414'],
    "廢棄物處理/環保": ['8422', '8341'],
    "手工具/電動工具": ['1590', '8499', '5347'],
    "手術機器人/智慧醫療器材": ['4164', '2049'],
    "投資控股/租賃": ['9917', '5871', '6592', '9941'],
    "折疊機/Apple 新機": ['3008', '3376', '2385'],
    "文創/IP 內容": ['3663', '5478', '6180'],
    "文化傳媒/出版": ['9928', '8450', '8329', '8458'],
    "新藥研發": ['6446', '6472', '4743'],
    "旅遊/廉航/郵輪": ['2618', '2610', '2731', '2743'],
    "日圓貶值受惠/台日合作": ['2330', '9921'],
    "晶圓代工成熟製程": ['6770', '2303', '5347'],
    "晶片封測": ['3711', '2449', '6239', '8150'],
    "智慧城市/V2X": ['1513', '6285'],
    "智慧家庭/Matter": ['2332', '5388', '6285'],
    "智慧醫療/AI醫學": ['6841', '6857', '7803'],
    "智慧電錶/AMI": ['1513', '1503', '1519'],
    "植栽/有機/飼料": ['1210', '1215', '1712', '1722'],
    "植物肉/替代蛋白": ['1210', '1215', '1216'],
    "模具/金屬加工": ['1590', '1589'],
    "橡膠/輪胎原料": ['2114', '2103', '2108'],
    "檢測/設備服務": ['1337'],
    "氫能/燃料電池": ['1513', '8996'],
    "氮化鎵/GaN": ['6770'],
    "水泥": ['1102'],
    "水資源/環保": ['8473', '1337', '8936'],
    "汽車零件/售後": ['1319', '2231'],
    "海底電纜": ['5603'],
    "無人機": ['5371', '6928', '8033'],
    "無塵室/廠務工程": ['2404', '6139', '5536'],
    "熱交換器/散熱器": ['3017', '3653', '8996', '3324'],
    "燃氣/天然氣": ['9908', '9918', '9926'],
    "特斯拉概念股": ['3665', '4576', '2308'],
    "特殊氣體/半導體化學品": ['1773', '4764', '5434'],
    "特用化學/光阻劑": ['5234', '4749', '1773'],
    "玻璃陶瓷/衛浴": ['1817', '1802', '1806', '1810'],
    "環境設備/空汙": ['8422', '8341'],
    "生技 CDMO": ['6589', '6472'],
    "生技醫療": ['6446', '6472'],
    "真空設備": ['2404', '6208'],
    "石英元件": ['3042'],
    "矽光子": ['2330', '3081'],
    "矽晶圓": ['5483', '6488', '6182'],
    "碳化矽/SiC": ['6488', '3016', '3707'],
    "碳權/ESG": ['8440'],
    "碳纖維/輕量材料": ['1905', '9921'],
    "磷化銦/InP": ['4971', '3081'],
    "稀土/關鍵金屬": ['1560', '9927'],
    "穿戴/智慧眼鏡": ['3008', '2385'],
    "精密機械/自動化": ['4540'],
    "精準診斷/體外診斷": ['4116', '4736'],
    "紡織/機能布": ['1476', '1477'],
    "細胞治療": ['4174', '4743'],
    "綠能/儲能": ['1513', '8440'],
    "網通": ['6285'],
    "美國製造回流/晶片法案": ['2330', '6488'],
    "美容保健/個人護理": ['6523', '4137', '4190'],
    "老年長照/銀髮醫療": ['5706', '4175', '6469', '6929'],
    "能源服務/石油燃料": ['6505', '8926', '2616'],
    "自行車零件": ['9914', '9921'],
    "航太": ['2645', '2634', '8222'],
    "航運/散裝": ['2606', '2637'],
    "航運/貨櫃": ['2609', '2615'],
    "螺絲/螺帽/緊固件": ['1590', '2012', '5347'],
    "被動元件": ['2492', '2327'],
    "製鞋/運動鞋代工": ['5306', '9802', '9904', '9910'],
    "觀光餐旅": ['2707', '2727'],
    "記憶體": ['2344', '2408', '8299'],
    "貿易百貨/消費": ['2903', '2905', '2908'],
    "資安": ['6214', '6462'],
    "資訊服務/IT服務": ['2480', '2453', '6214'],
    "軍工/國防": ['2208', '2634', '3005', '8033'],
    "軟體/SaaS": ['6214', '6270'],
    "軸承/精密機構": ['2049', '2059'],
    "輝達概念股": ['2330', '3711', '2382', '3231'],
    "輪胎/橡膠": ['2105', '2106'],
    "農業科技/植物工廠": ['1210', '1215'],
    "造紙": ['1907', '1337', '1904', '1905'],
    "造紙/紙業": ['1907', '1337', '1904', '1905'],
    "連接器": ['3533', '3665'],
    "連鎖零售/超商": ['2912', '5903', '5904'],
    "遊戲股": ['3293', '5478', '6180'],
    "運動休閒": ['9914', '1736', '9921'],
    "醫材": ['4106', '4736', '4107'],
    "醫美/雷射": ['6491', '4107'],
    "重建/災後/基礎建設": ['2542', '2002'],
    "重電": ['1513', '1503', '1519'],
    "量子電腦": ['2330', '3711'],
    "金屬粉末/3D 列印": ['8467', '1560'],
    "金融證券": ['6005', '6024'],
    "銅纜/銅加工": ['1608', '1609', '1618'],
    "鋰電池材料": ['4721', '4739'],
    "鋼鐵": ['2006', '2002', '2015'],
    "閥門管材": ['1608', '8936'],
    "雲端服務/SaaS": ['7722', '2605', '6763'],
    "電商/網購": ['8454', '8044'],
    "電子通路": ['3702', '2347', '3036'],
    "電源供應器/BBU": ['2301', '2308', '6412'],
    "面板/顯示器": ['2409', '3481'],
    "風電/離岸風電": ['2072', '6793', '9958', '3708'],
    "食品/民生": ['1215', '1216', '1227'],
    "食品零售": ['1234', '1264'],
    "高階 PCB/HDI": ['2313', '3044'],
    "齒輪/減速機": ['2049'],
}


# 對 dominance 跑不出 / 跑出極少的群，提供 ground truth ticker（強制 keep + 標核心）
# 來源：My-TW-Coverage themes/*.md + discover.py 高信心結果 + 業界常識
GROUP_GROUND_TRUTH = {
    "HVDC/直流電力": ["2308", "2301", "3023", "8261", "1503", "3015"],  # 台達電/光寶/信邦
    "Chiplet 小晶片": ["3661", "3443", "2330", "3037", "8046", "3189", "3711"],  # 世芯/創意/台積/載板三雄/日月光
    "量子電腦": ["2330", "2454", "3552", "3661", "3443"],  # 台積/聯發/同欣電/世芯/創意
    "OLED/Micro LED": ["3324", "3037", "3673", "3658", "8064", "3081"],
    "磷化銦/InP": ["3081", "4977", "2455", "3105", "3234"],
    "氮化鎵/GaN": ["3105", "3016", "5347", "8086", "3673"],
    "碳化矽/SiC": ["6770", "5347", "3105", "8021", "5285", "6735"],
    "CoWoS先進封裝": ["2330", "3711", "3037", "8046", "3189", "6770", "6239", "2449", "8046", "3034"],
    "半導體設備": ["3680", "6781", "3413", "5536", "6691", "6196", "3596", "8048", "5483", "6206"],
    "機器人": ["2049", "1597", "3324", "8261", "2308", "3017", "4576", "1536"],
    "2奈米先進製程": ["2330", "3661", "3443", "2454", "3037", "8046", "3189", "3711", "6515", "8210"],
    "DDR5/LPDDR5 記憶體": ["2408", "2344", "8271", "3260", "4967"],  # 移除 2483 百容(連接器/導線架，非DRAM) + 5269 祥碩(USB controller) — Phase 11 user feedback；改加 威剛/十詮 DRAM 模組廠
    "晶圓代工成熟製程": ["6770", "5347", "2342", "2303"],
    "Flexible PCB/軟板": ["4958", "6213", "8046", "8358", "3044"],
    "台積電供應鏈": ["3037", "8046", "3189", "3711", "5483", "5469", "3526", "6515", "6510", "6782"],
    "鋰電池材料": ["6121", "3211", "4739", "4721", "8021"],
    "固態電池": ["6121", "3211", "4739", "8261", "1319"],
    "儲能系統/BESS": ["2308", "2301", "1519", "1597", "3576"],
    "充電樁/充電服務": ["2308", "1519", "3023", "1513"],  # 移除 6235 華孚(壓鑄)/6803 崑鼎(焚化廠) — Phase 11 user feedback
    "氫能/燃料電池": ["1519", "1326", "2611", "8261"],
    "車用電子": ["2308", "3034", "2454", "2376", "3376", "3008", "2492"],
    "工業電腦/IPC": ["6414", "3022", "2049", "6233", "2618", "2305"],
    "軸承/精密機構": ["2049", "1583", "1597", "1721"],
    "齒輪/減速機": ["1597", "1583", "1536"],
    "真空設備": ["3030", "3413", "5536"],
    "碳纖維/輕量材料": ["1455", "1718", "1605"],
    "閥門管材": ["8255", "1535", "1605"],
    "玻璃陶瓷/衛浴": ["1802", "1815", "1809"],
    "海底電纜": ["1503", "1504", "1419"],
    "稀土/關鍵金屬": ["2002", "2027", "2059"],
    "塑化/原物料": ["1303", "1326", "1304", "1308", "1605"],
    "資訊服務/IT服務": ["6230", "5263", "8011", "2417", "2451"],
    "雲端服務/SaaS": ["6230", "5263", "8011"],
    "智慧家庭/Matter": ["3022", "2332", "2419"],
    "智慧電錶/AMI": ["6803", "1519", "3023"],
    "環境設備/空汙": ["6803", "1519", "8064"],
    "軍工/國防": ["2347", "8033", "2049", "2059"],
    "PCB設備/耗材": ["8064", "3413", "5536", "6691"],
    "折疊機/Apple 新機": ["2317", "3008", "3406", "2354", "2474", "3037"],
    "印度產能/印度概念": ["2317", "2382", "4938", "6669"],
    "川普概念/關稅戰": ["2330", "2317", "2382"],
    "日圓貶值受惠/台日合作": ["3105", "8086", "3491"],
    "美國製造回流/晶片法案": ["2330", "3037", "8046", "3189"],
    "新南向/東南亞產能": ["2317", "2382", "4938", "6669"],
    "重建/災後/基礎建設": ["1503", "1504", "1605"],
    "光學薄膜": ["3149", "3037", "8358"],
    "汽車零件/售後": ["1319", "1539", "1592", "1597"],
    "精密機械/自動化": ["2049", "1597", "3324"],
    "化工/染料/特化": ["1303", "1304", "1313", "1308"],
    "金融證券": ["2880", "2881", "2882", "2884", "2891"],
    "智慧城市/V2X": ["2308", "2376", "3034"],
    "AI 眼鏡 / Meta Ray-Ban": ["3008", "2317", "3406", "3037"],
    "穿戴/智慧眼鏡": ["3008", "2354", "2392", "3406"],
    "無人機": ["2347", "8033", "2059", "2049"],
    "低軌衛星": ["2412", "2345", "3704", "3416", "3019"],
    "碳權/ESG": ["2330", "2454", "1303"],
    "投資控股/租賃": ["5871", "6592", "2882", "2880"],
}


# 部分群的 core_keywords 不足，補同義詞讓 dominance 更精準
KEYWORD_EXPANSIONS = {
    # ── 已驗收群 ──
    "IC設計": ["IC 設計", "ICT 設計", "Fabless", "無晶圓", "fabless", "IC設計"],
    "半導體設備": ["半導體製程設備", "晶圓設備", "前段設備", "後段設備", "Wafer 設備", "晶圓廠設備", "半導體設備", "蝕刻機", "CMP", "薄膜設備", "微影設備", "Wet Bench", "濕式清洗", "化學機械研磨"],
    "晶片封測": ["封測", "封裝測試", "OSAT", "後段封裝", "後段測試"],
    "矽光子": ["矽光子", "Silicon Photonics", "CPO", "共封裝光學"],
    "PCB/銅箔基板": ["PCB", "印刷電路板", "銅箔基板", "CCL", "高速 PCB"],
    "連接器": ["連接器", "Connector", "Socket", "UQD"],
    "被動元件": ["被動元件", "MLCC", "晶振"],
    "散熱/液冷": ["散熱", "液冷", "Cooling", "CDU"],
    "電源供應器/BBU": ["電源供應", "BBU", "備援電池", "HVDC"],
    "車用半導體": ["車用 IC", "車用半導體", "車用晶片"],
    "光通訊": ["光通訊", "光收發模組", "光模組", "光纖"],
    "矽晶圓": ["矽晶圓", "拋光晶圓", "12 吋晶圓"],
    "ABF載板": ["ABF 載板", "ABF", "IC 載板", "Ajinomoto Build-up Film"],
    "石英元件": ["石英", "石英元件", "石英晶體", "Crystal", "TXC", "TCXO", "OCXO", "振盪器"],
    "HBM 高頻寬記憶體": ["HBM", "高頻寬記憶體", "HBM3E", "HBM4"],
    "CoWoS先進封裝": ["CoWoS", "先進封裝", "2.5D 封裝", "FOPLP", "InFO", "SoIC", "扇出封裝"],
    "ASIC/IP矽智財": ["ASIC", "矽智財", "Silicon IP", "Design Service", "ASIC 設計服務"],
    # ── Phase 9：51 個過 prune 群補同義詞 ──
    "2奈米先進製程": ["2 奈米", "2nm", "N2", "2奈米", "先進製程", "2nm 製程"],
    "Chiplet 小晶片": ["Chiplet", "小晶片", "UCIe", "晶片粒"],
    "DDR5/LPDDR5 記憶體": ["DDR5", "LPDDR5", "LPDDR", "記憶體模組", "DRAM"],
    "晶圓代工成熟製程": ["8 吋", "成熟製程", "Mature node", "12 吋老製程", "55nm", "40nm", "28nm"],
    "Flexible PCB/軟板": ["軟板", "FPC", "Flex PCB", "可撓性電路板"],
    # 新興題材
    "機器人": ["機器人", "Robotics", "人形機器人", "Optimus", "服務型機器人", "工業機器人", "機械手臂"],
    "無人機": ["無人機", "UAV", "Drone", "軍用無人機", "民用無人機"],
    "智慧城市/V2X": ["V2X", "智慧城市", "智慧交通", "車聯網"],
    "量子電腦": ["量子電腦", "Quantum", "量子計算", "Qubit"],
    "AI 眼鏡 / Meta Ray-Ban": ["AI 眼鏡", "Smart Glasses", "Ray-Ban Meta", "Vision Pro", "AR 眼鏡", "VR 頭顯"],
    "穿戴/智慧眼鏡": ["穿戴", "Wearable", "智慧手錶", "Apple Watch", "智慧眼鏡"],
    # 能源 / 電源
    "HVDC/直流電力": ["HVDC", "直流電力", "高壓直流", "800V HVDC", "直流配電"],
    "鋰電池材料": ["鋰電池", "正極材料", "負極材料", "電解液", "隔離膜", "三元", "LFP", "磷酸鋰鐵"],
    "固態電池": ["固態電池", "Solid State Battery", "SSB", "全固態"],
    "儲能系統/BESS": ["儲能", "BESS", "Battery Energy Storage", "儲能系統"],
    "充電樁/充電服務": ["充電樁", "EV Charging", "Charger"],
    "氫能/燃料電池": ["氫能", "燃料電池", "Fuel Cell", "綠氫"],
    # 傳產 / 工業
    "工業電腦/IPC": ["工業電腦", "IPC", "Industrial PC", "工控"],
    "軸承/精密機構": ["軸承", "精密機構", "Bearing", "滾珠"],
    "齒輪/減速機": ["齒輪", "減速機", "Gearbox", "傳動"],
    "真空設備": ["真空", "真空泵", "Vacuum", "Pump", "真空設備"],
    "碳纖維/輕量材料": ["碳纖維", "Carbon Fiber", "輕量化", "複合材料"],
    "閥門管材": ["閥門", "管材", "Valve", "Pipe"],
    "玻璃陶瓷/衛浴": ["玻璃", "陶瓷", "衛浴", "Glass", "Ceramic"],
    "海底電纜": ["海底電纜", "海纜", "Submarine Cable"],
    "稀土/關鍵金屬": ["稀土", "Rare Earth", "關鍵金屬", "釹", "鏑"],
    "塑化/原物料": ["石化", "塑化", "聚乙烯", "聚丙烯", "PE", "PP", "PVC", "PET"],
    # 軟體服務
    "資訊服務/IT服務": ["資訊服務", "IT 服務", "SI", "系統整合", "雲端服務"],
    "雲端服務/SaaS": ["SaaS", "雲端", "Cloud Service", "雲端服務"],
    "智慧家庭/Matter": ["智慧家庭", "Matter", "Smart Home", "Zigbee"],
    "智慧電錶/AMI": ["智慧電錶", "AMI", "Smart Meter"],
    "環境設備/空汙": ["環境設備", "空汙", "廢氣處理", "脫硫", "脫硝"],
    "軍工/國防": ["軍工", "國防", "Defense", "Military", "軍規"],
    # PCB 設備耗材
    "PCB設備/耗材": ["PCB 設備", "PCB 耗材", "鑽孔機", "雷射鑽孔", "曝光機", "蝕刻線"],
    # 政策概念（補關鍵字幫助命中）
    "折疊機/Apple 新機": ["折疊機", "Apple 新機", "iPhone Fold", "iPhone 17", "iPhone 18", "Foldable"],
    "印度產能/印度概念": ["印度", "India", "印度產能"],
    "川普概念/關稅戰": ["關稅", "Trump", "美中貿易戰", "Tariff"],
    "日圓貶值受惠/台日合作": ["日圓", "日本", "台日合作", "JPY", "Yen"],
    "美國製造回流/晶片法案": ["CHIPS Act", "美國製造", "Reshoring", "回流", "Made in USA"],
    "新南向/東南亞產能": ["越南", "印尼", "泰國", "東南亞", "新南向", "ASEAN"],
    "重建/災後/基礎建設": ["重建", "災後", "基礎建設", "Infrastructure"],
    # PCB / 上游
    "OLED/Micro LED": ["OLED", "Micro LED", "Mini LED", "AMOLED"],
    # 半導體大群
    "台積電供應鏈": ["台積電供應鏈", "台積", "TSMC", "台積電 供應商"],
    # 環境 / 碳權
    "碳權/ESG": ["碳權", "ESG", "Carbon Credit", "減碳", "碳中和"],
    # 化工
    "化工/染料/特化": ["化工", "染料", "特化", "化學品"],
    # 金融
    "金融證券": ["銀行", "保險", "證券", "金控"],
    # 紡織
    "紡織/機能布": ["紡織", "機能布", "成衣", "Functional Fabric"],
    # 居家
    "居家修繕/家居用品": ["居家", "家居", "家具", "DIY"],
    # 汽車
    "汽車零件/售後": ["汽車零件", "售後", "Aftermarket", "AM 件"],
    "車用電子": ["車用電子", "車用 IC", "車載", "車用半導體"],
    # 精密機械
    "精密機械/自動化": ["精密機械", "自動化", "Automation", "Mechatronics"],
    # 光學
    "光學薄膜": ["光學薄膜", "Optical Film", "偏光板"],
}


def evaluate_group(
    group_name: str,
    members: list[tuple[str, str]],
    spec: dict,
    name_map: dict[str, str],
) -> dict:
    """對單群跑雙閥，回 {keep, satellite, remove, abstain}。"""
    if spec.get("deprecated"):
        return {
            "kind": "deprecated",
            "keep": [], "satellite": [], "remove": [], "abstain": [],
            "deprecation_reason": spec.get("deprecation_reason", ""),
            "members_reclassify_to": spec.get("members_reclassify_to", []),
        }
    if spec.get("merge_into"):
        return {
            "kind": "merge",
            "keep": [], "satellite": [], "remove": [], "abstain": [],
            "merge_into": spec["merge_into"],
        }

    core_keywords = list(spec.get("core_keywords", []))
    # 套用 keyword expansion 表（補同義詞讓 dominance 更精準）
    if group_name in KEYWORD_EXPANSIONS:
        for kw in KEYWORD_EXPANSIONS[group_name]:
            if kw not in core_keywords:
                core_keywords.append(kw)
    forbidden_pos = set(spec.get("forbidden_positions", []))
    allowed_pos = set(spec.get("allowed_positions", []))

    # ── Phase 10 修補（D2）：ground_truth 在 INDIRECT/customer 路由前先補進 members ──
    # 這樣即使群最後走 permissive，ground truth ticker 也會在成分股清單裡
    pre_gt = set(GROUP_GROUND_TRUTH.get(group_name, [])) | set(AUTO_GROUND_TRUTH_FROM_DESC.get(group_name, []))
    if pre_gt:
        existing = {t for t, _ in members}
        for gt in pre_gt:
            if gt not in existing:
                members = list(members) + [(gt, name_map.get(gt, ""))]
                existing.add(gt)

    # 客戶概念股群 → 改用客戶模式 dominance（看主要客戶段落而非業務簡介）
    if group_name in CUSTOMER_KEYWORD_MAP:
        cust_keywords = CUSTOMER_KEYWORD_MAP[group_name]
        if not cust_keywords:
            # 空 keyword 列表（如「其他多元族群」）→ permissive
            return {
                "kind": "permissive",
                "keep": [(t, name_map.get(t, c) or c, "permissive_kept", "") for t, c in members],
                "satellite": [], "remove": [], "abstain": [],
            }
        keep_basket, satellite_basket, remove_basket, abstain_basket = [], [], [], []
        for ticker, original_comment in members:
            real_name = name_map.get(ticker, original_comment) or ticker
            # Phase 10 修補：ground_truth 在 customer mode 也強制 keep
            if ticker in pre_gt:
                keep_basket.append((ticker, real_name, "core", "ground_truth：人工/desc 標記真核心"))
                continue
            vote = score_customer_dominance(ticker, cust_keywords)
            if vote.verdict == "STRONG_PASS":
                keep_basket.append((ticker, real_name, "core", f"客戶段第 {vote.char_offset} 字命中「{vote.matched_keyword}」"))
            elif vote.verdict == "WEAK_PASS":
                satellite_basket.append((ticker, real_name, "satellite", f"客戶段次要提及「{vote.matched_keyword}」"))
            elif vote.verdict == "FAIL":
                remove_basket.append((ticker, real_name, "remove", vote.reason))
            else:
                abstain_basket.append((ticker, real_name, "abstain", "Coverage 缺失"))
        return {
            "kind": "strict_customer",
            "keep": keep_basket,
            "satellite": satellite_basket,
            "remove": remove_basket,
            "abstain": abstain_basket,
        }

    if not core_keywords or group_name in INDIRECT_BENEFIT_GROUPS:
        # permissive 群（無 keyword 或無 customer 模式對映）→ 保留原 list，不動
        # Phase 10 修補：因為前面 pre_gt 已把 ground_truth 加進 members，這裡 keep 自動包含 ground truth
        return {
            "kind": "permissive",
            "keep": [(t, name_map.get(t, c) or c, "permissive_kept", "") for t, c in members],
            "satellite": [], "remove": [], "abstain": [],
        }

    # 4 籃子
    keep_basket = []      # STRONG_PASS
    satellite_basket = [] # WEAK_PASS
    remove_basket = []    # FAIL
    abstain_basket = []   # 無 Coverage

    # Ground truth — 對指定核心個股強制 keep（即使 dominance 沒命中）
    # 合併兩個來源：手動標記 + 從 industry_meta desc 自動 extract
    ground_truth = set(GROUP_GROUND_TRUTH.get(group_name, [])) | set(AUTO_GROUND_TRUTH_FROM_DESC.get(group_name, []))
    member_set = {t for t, _ in members}

    # 若 ground truth 不在原 members 中，自動加入（為新興群補核心個股）
    members_with_gt = list(members)
    for gt in ground_truth:
        if gt not in member_set:
            members_with_gt.append((gt, name_map.get(gt, "")))

    for ticker, original_comment in members_with_gt:
        real_name = name_map.get(ticker, original_comment) or ticker

        # Ground truth 一律強制升 core（人工標記，覆蓋一切 dominance 判決）
        if ticker in ground_truth:
            keep_basket.append((ticker, real_name, "core", "ground_truth：人工標記真核心"))
            continue

        vote = score_dominance(ticker, core_keywords, group_name=group_name)

        if vote.verdict == "STRONG_PASS":
            evidence = f"主業簡介第 {vote.char_offset} 字命中「{vote.matched_keyword}」"
            keep_basket.append((ticker, real_name, "core", evidence))
        elif vote.verdict == "WEAK_PASS":
            evidence = f"主業有提（第 {vote.char_offset} 字）但非首句"
            satellite_basket.append((ticker, real_name, "satellite", evidence))
        elif vote.verdict == "FAIL":
            if vote.excluded_role:
                reason = f"角色「{vote.excluded_role}」搶先 → 非主軸廠"
            else:
                reason = "業務簡介未提族群關鍵字 → 非主業"
            remove_basket.append((ticker, real_name, "remove", reason))
        else:  # ABSTAIN — Phase 11 修正：Coverage 缺失改為 remove（不再保守保留）
            # 例外：finlab 產業類別與 spec.allowed_segments 任一相符 → satellite（給 benefit of doubt）
            from validator.evidence import infer_segment_from_twse
            twse_seg = None
            if "snapshot_cache" not in evaluate_group.__dict__:
                import pandas as pd
                snapshot_cache_path = TAXONOMY_DIR / "validator" / "cache" / "finlab_snapshot.parquet"
                evaluate_group.snapshot_cache = pd.read_parquet(snapshot_cache_path) if snapshot_cache_path.exists() else None
            snap = evaluate_group.snapshot_cache
            if snap is not None:
                row = snap[snap["symbol"] == ticker]
                if not row.empty:
                    twse_seg = infer_segment_from_twse(row.iloc[0]["產業類別"])
            allowed_segs = set(spec.get("allowed_segments", []))
            if twse_seg and allowed_segs and twse_seg in allowed_segs:
                satellite_basket.append((ticker, real_name, "satellite", f"Coverage 缺失但 finlab 產業 ({twse_seg}) 符合"))
            else:
                remove_basket.append((ticker, real_name, "remove", f"Coverage 缺失 + finlab 產業 ({twse_seg or '?'}) 不符 spec.allowed_segments"))

    return {
        "kind": "strict",
        "keep": keep_basket,
        "satellite": satellite_basket,
        "remove": remove_basket,
        "abstain": abstain_basket,
    }


def render_group_block(group: str, result: dict) -> str:
    """生成新版 concept_groups.py 中該群的 list block，附 inline rationale 註解。"""
    lines = [f'    "{group}": [']

    if result["kind"] == "deprecated":
        if result.get("deprecation_reason"):
            lines.append(f'        # [deprecated] {result["deprecation_reason"][:100]}')
        if result.get("members_reclassify_to"):
            lines.append(f'        # 成員重歸至：{result["members_reclassify_to"]}')
    elif result["kind"] == "merge":
        lines.append(f'        # [merge] 已合併進「{result["merge_into"]}」')
    elif result["kind"] == "permissive":
        lines.append(f'        # [permissive] 無 core_keywords，保留原成員')
        for t, name, _, _ in result["keep"]:
            display = name if name and name != t else t
            lines.append(f'        "{t}",  # {display}')
    else:
        # strict
        if result["keep"]:
            lines.append(f'        # ── [核心] (主業 dominance STRONG_PASS) ──')
            for t, name, _, ev in result["keep"]:
                lines.append(f'        "{t}",  # {name} — {ev}')
        if result["satellite"]:
            lines.append(f'        # ── [衛星] (主業有提非首句) ──')
            for t, name, _, ev in result["satellite"]:
                lines.append(f'        "{t}",  # {name} — {ev}')
        if result["abstain"]:
            lines.append(f'        # ── [待人工] (Coverage 缺失) ──')
            for t, name, _, _ in result["abstain"]:
                lines.append(f'        "{t}",  # {name} — Coverage 缺失')
        if result["remove"]:
            lines.append(f'        # ── 已移除（Phase 6 dominance FAIL）──')
            for t, name, _, reason in result["remove"]:
                lines.append(f'        # {t}  {name} — {reason}')

    lines.append("    ],")
    return "\n".join(lines)


def replace_group_block(src: str, group: str, new_block: str) -> tuple[str, bool]:
    """以「`\\n    ],` 收尾」嚴格匹配，避開 inline [核心]/[衛星] 方括號。"""
    pattern = re.compile(
        rf'    "{re.escape(group)}"\s*:\s*\[(?:.*?)\n    \],',
        re.DOTALL,
    )
    m = pattern.search(src)
    if not m:
        return src, False
    return src[:m.start()] + new_block + src[m.end():], True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="寫回 concept_groups.py + 重 build site")
    ap.add_argument("--group", help="只跑單群 demo")
    ap.add_argument("--build", action="store_true", help="apply 後同時跑 site/build_site.py")
    args = ap.parse_args()

    print("[1/5] 載入 group_specs / concept_groups / finlab snapshot ...")
    specs_dict = json.loads((TAXONOMY_DIR / "group_specs.json").read_text(encoding="utf-8"))
    groups = parse_concept_groups()
    name_map = load_finlab_names()
    print(f"  {len(groups)} 群、{sum(len(v) for v in groups.values())} 個股次、{len(name_map)} ticker→name 映射")

    print("[2/5] 對每群跑雙閥仲裁 ...")
    if args.group:
        targets = {args.group: groups.get(args.group, [])}
    else:
        targets = groups

    results = {}
    overall = Counter()
    for g, members in targets.items():
        spec = specs_dict.get(g, {})
        r = evaluate_group(g, members, spec, name_map)
        results[g] = r
        overall["keep"] += len(r["keep"])
        overall["satellite"] += len(r["satellite"])
        overall["remove"] += len(r["remove"])
        overall["abstain"] += len(r["abstain"])
        if r["kind"] == "deprecated":
            overall["deprecated_groups"] += 1
        elif r["kind"] == "merge":
            overall["merge_groups"] += 1
        elif r["kind"] == "permissive":
            overall["permissive_groups"] += 1
        else:
            overall["strict_groups"] += 1

    print("[3/5] 全局統計：")
    for k, v in overall.most_common():
        print(f"    {k}: {v}")

    # TOP 10 高 remove
    print("\n  TOP 10 高 remove rate 群：")
    sorted_groups = sorted(
        [(g, r) for g, r in results.items() if r["kind"] == "strict"],
        key=lambda kv: len(kv[1]["remove"]),
        reverse=True,
    )
    for g, r in sorted_groups[:10]:
        total = len(r["keep"]) + len(r["satellite"]) + len(r["remove"]) + len(r["abstain"])
        print(f"    {g:<25s} keep={len(r['keep']):>3d} sat={len(r['satellite']):>3d} rem={len(r['remove']):>3d} abs={len(r['abstain']):>3d} total={total}")

    # 寫 master_patch_v3.json
    patch = {}
    for g, r in results.items():
        spec = specs_dict.get(g, {})
        if r["kind"] == "deprecated":
            patch[g] = {
                "keep": [], "source": "phase6_v3", "deprecated": True,
                "deprecation_reason": r.get("deprecation_reason", ""),
                "members_reclassify_to": r.get("members_reclassify_to", []),
            }
        elif r["kind"] == "merge":
            patch[g] = {"keep": [], "source": "phase6_v3", "merge_into": r["merge_into"]}
        elif r["kind"] == "permissive":
            patch[g] = {
                "keep": [t for t, _, _, _ in r["keep"]],
                "source": "phase6_v3_permissive",
            }
        else:
            patch[g] = {
                "keep": [t for t, _, _, _ in r["keep"] + r["satellite"] + r["abstain"]],
                "core": [t for t, _, _, _ in r["keep"]],
                "satellite": [t for t, _, _, _ in r["satellite"]],
                "abstain": [t for t, _, _, _ in r["abstain"]],
                "removed": [
                    {"ticker": t, "name": n, "reason": rs}
                    for t, n, _, rs in r["remove"]
                ],
                "source": "phase6_v3",
                "validated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
    out_patch = TAXONOMY_DIR / "master_patch_v3.json"
    out_patch.write_text(json.dumps(patch, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[4/5] ✓ {out_patch}")

    if args.apply:
        print("\n[5/5] 套用到 concept_groups.py ...")
        backup = PROJECT_ROOT / "concept_groups.py.bak6_phase6"
        shutil.copy(TARGET, backup)
        print(f"  備份 → {backup}")

        src = TARGET.read_text(encoding="utf-8")
        n_applied = 0
        n_failed = []
        for g, r in results.items():
            new_block = render_group_block(g, r)
            src, ok = replace_group_block(src, g, new_block)
            if ok:
                n_applied += 1
            else:
                n_failed.append(g)
        TARGET.write_text(src, encoding="utf-8")
        print(f"  ✓ 套用 {n_applied} 群")
        if n_failed:
            print(f"  ⚠ regex 替換失敗 {len(n_failed)} 群（單獨處理）：{n_failed[:10]}")

        # sanity
        if "concept_groups" in sys.modules:
            del sys.modules["concept_groups"]
        sys.path.insert(0, str(PROJECT_ROOT))
        try:
            from concept_groups import CONCEPT_GROUPS as cg
            print(f"  [sanity] 載入成功，總族群 {len(cg)}")
        except Exception as e:
            print(f"  ⚠ 載入失敗：{e}")
            shutil.copy(backup, TARGET)
            print(f"  恢復備份")
            return

        if args.build:
            print("\n  跑 site/build_site.py ...")
            result = subprocess.run(
                [sys.executable, str(PROJECT_ROOT / "site" / "build_site.py"), "--skip-finlab"],
                capture_output=True, text=True, encoding="utf-8",
            )
            print("  ", result.stdout.split("\n")[-3] if result.stdout else "")
            if result.returncode == 0:
                print("  ✓ build site 成功")
    else:
        print("\n[5/5] (dry run，加 --apply 才會寫回)")


if __name__ == "__main__":
    main()
