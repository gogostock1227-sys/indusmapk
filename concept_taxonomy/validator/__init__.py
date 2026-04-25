"""
族群三維驗證系統 (Taxonomy Validator v2)

對 concept_groups.py 中 190 個族群、~2500 個 (族群,個股) pair 進行嚴謹的三維驗證：
  C1: industry_segment    (13 enum)
  C2: core_themes         (30+ enum, 必含族群必要題材)
  C3: supply_chain_position (27 enum, 必在族群允許位階白名單內)

證據來源：My-TW-Coverage / finlab / Web 搜尋。
產出：master_patch_v2.json + _VERIFICATION_REPORT_v2.md。

入口：python -m concept_taxonomy.validator.pipeline --full
"""

__version__ = "2.0.0"
