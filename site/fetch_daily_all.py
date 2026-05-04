"""
全站每日資料更新總爬蟲（近 2 個交易日增量）

用途：admin 不確定 finlab/公開資料今天更新了沒，一鍵跑這支總爬蟲，
依序執行所有日常增量資料源，任一支失敗不會中斷其他。

包含的子爬蟲（依執行順序）：
  1. fetch_daily_chip_report          — 每日籌碼報告（三大法人 / 融資融券 / VIX）
  2. fetch_extras                      — 處置股清單 + 集保戶股權分散表
  3. fetch_stock_futures_ranking       — 股期排行（保證金 + 成交量）→ 近 2 日 backfill
  4. fetch_trending_topics             — 熱門題材（Yahoo + 鉅亨網）
  5. fetch_stock_futures_history       — 個股期貨 K + OI（finlab）→ 近 2 日

設計原則（owner 意識）：
- 任一子爬蟲 fail 不影響後續：subprocess 隔離 + try/except 包住
- 每支跑完印 ✅/❌ 狀態 + 耗時，最後印總表
- 不接受參數，行為固定（避免 admin UI 過度複雜）
- 跑完後由 build_site.py --skip-finlab 統一 render 套用新資料

執行方式：
  python site/fetch_daily_all.py
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent  # site/

# ─── 子爬蟲定義 ────────────────────────────────────────────
# 每個 entry: (label, [python args after script path])
JOBS: list[tuple[str, str, list[str]]] = [
    ("每日籌碼報告",       "fetch_daily_chip_report.py",   []),
    ("處置股 + 集保戶分散", "fetch_extras.py",              []),
    ("股期排行 (近 2 日)",  "fetch_stock_futures_ranking.py", ["--backfill-days", "2"]),
    ("熱門題材",            "fetch_trending_topics.py",     []),
    ("個股期貨 K+OI (近 2 日)", "fetch_stock_futures_history.py", ["--days=2"]),
]

# 單支爬蟲超時保護（秒）：避免某支卡死拖累整個 pipeline
PER_JOB_TIMEOUT_SEC = 600  # 10 分鐘


def run_job(label: str, script: str, args: list[str]) -> tuple[bool, float, str]:
    """
    執行單支子爬蟲。
    回傳 (success, elapsed_sec, error_msg)
    """
    script_path = ROOT / script
    if not script_path.exists():
        return False, 0.0, f"script not found: {script_path}"

    cmd = [sys.executable, str(script_path), *args]
    start = time.time()
    try:
        result = subprocess.run(
            cmd,
            cwd=str(ROOT.parent),  # 從專案根目錄執行（與 build_site.py 一致）
            timeout=PER_JOB_TIMEOUT_SEC,
            capture_output=False,  # stdout/stderr 直接 pipe 到當前 console，方便看 GitHub Actions log
            check=False,
            text=True,
        )
        elapsed = time.time() - start
        if result.returncode == 0:
            return True, elapsed, ""
        return False, elapsed, f"exit code {result.returncode}"
    except subprocess.TimeoutExpired:
        elapsed = time.time() - start
        return False, elapsed, f"timeout after {PER_JOB_TIMEOUT_SEC}s"
    except Exception as e:
        elapsed = time.time() - start
        return False, elapsed, f"{type(e).__name__}: {e}"


def main() -> int:
    print("=" * 70)
    print("🚀 全站每日資料更新總爬蟲（近 2 個交易日增量）")
    print(f"   共 {len(JOBS)} 支子爬蟲，每支超時保護 {PER_JOB_TIMEOUT_SEC}s")
    print("=" * 70)

    results: list[tuple[str, str, bool, float, str]] = []
    overall_start = time.time()

    for idx, (label, script, args) in enumerate(JOBS, 1):
        argstr = " ".join(args) if args else "(no args)"
        print(f"\n[{idx}/{len(JOBS)}] ▶ {label}  ({script} {argstr})")
        print("-" * 70)
        ok, elapsed, err = run_job(label, script, args)
        results.append((label, script, ok, elapsed, err))
        status = "✅ 成功" if ok else f"⚠️  失敗：{err}"
        print(f"\n  → {status}（耗時 {elapsed:.1f}s）")

    # ─── 總結報告 ────────────────────────────────────────
    overall_elapsed = time.time() - overall_start
    succeeded = sum(1 for _, _, ok, _, _ in results if ok)
    failed = len(results) - succeeded

    print("\n" + "=" * 70)
    print("📊 執行總表")
    print("=" * 70)
    for label, script, ok, elapsed, err in results:
        icon = "✅" if ok else "⚠️ "
        suffix = "" if ok else f"  [{err}]"
        print(f"  {icon} {label:<28}  {elapsed:6.1f}s   {script}{suffix}")
    print("-" * 70)
    print(f"  總耗時：{overall_elapsed:.1f}s   |   成功 {succeeded} / {len(results)}   "
          f"{'⚠️ 失敗 ' + str(failed) if failed else '🎉 全部成功'}")
    print("=" * 70)

    # 即使有失敗也回傳 exit code 0，避免 GitHub Actions step fail 後不跑後續 build_site.py
    # （workflow 端可從上述 ⚠️ log 看到部分失敗）
    return 0


if __name__ == "__main__":
    sys.exit(main())
