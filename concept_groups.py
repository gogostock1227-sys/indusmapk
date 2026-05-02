"""網站題材與 Moneydj 產業族群清單。

此檔由 concept_taxonomy/validator/sync_moneydj_industries.py 更新。
Moneydj CSV 以「細產業」作為網站族群名稱；大族群分類寫入 site/moneydj_industry_meta.py。
既有概念股與題材股依保護規則保留，不被 Moneydj 同名產業覆蓋。
"""

import json as _json
import pathlib as _pathlib
CONCEPT_GROUPS = _json.load(
    (_pathlib.Path(__file__).parent / 'data/concept_groups.json').open(encoding="utf-8")
)
