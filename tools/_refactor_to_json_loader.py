"""一次性 refactor：把 concept_groups.py / site/industry_meta.py 的大 dict
替換成從 data/*.json load 的 thin wrapper。

執行前請確認：
  - tools/migrate_pyconfig_to_json.py 已成功跑過（data/*.json 已存在）
  - .pre-refactor.bak 備份檔已建立

跑法：python tools/_refactor_to_json_loader.py
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def refactor(py_path: Path, var_name: str, json_rel_from_pyfile: str) -> None:
    src = py_path.read_text(encoding="utf-8")
    tree = ast.parse(src)

    target = None
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == var_name:
                    target = node
                    break
        if target is not None:
            break

    if target is None:
        raise RuntimeError(f"{py_path}: 找不到 {var_name} 賦值")

    start = target.lineno          # 1-indexed
    end = target.end_lineno        # 1-indexed inclusive

    lines = src.splitlines(keepends=True)

    head = "".join(lines[: start - 1])
    tail = "".join(lines[end:])

    has_json = any(
        l.strip().startswith(("import json as _json", "import json"))
        for l in lines[: start - 1]
    )
    has_pathlib = any(
        l.strip().startswith(("import pathlib as _pathlib", "import pathlib"))
        for l in lines[: start - 1]
    )

    inject_imports = ""
    if not has_json:
        inject_imports += "import json as _json\n"
    if not has_pathlib:
        inject_imports += "import pathlib as _pathlib\n"

    loader = (
        f"{var_name} = _json.load(\n"
        f"    (_pathlib.Path(__file__).parent / {json_rel_from_pyfile!r}).open(encoding=\"utf-8\")\n"
        f")\n"
    )

    if inject_imports and not head.endswith("\n\n"):
        if head.endswith("\n"):
            inject_imports = "\n" + inject_imports
        else:
            inject_imports = "\n\n" + inject_imports

    new_src = head + inject_imports + loader + tail

    py_path.write_text(new_src, encoding="utf-8")
    new_lines = new_src.count("\n")
    old_lines = src.count("\n")
    print(
        f"  ✓ {py_path.relative_to(ROOT)}:"
        f"  替換 lines {start}-{end} ({end - start + 1} 行)"
        f"  →  total {old_lines} → {new_lines} 行"
    )


def main() -> int:
    print("Refactor concept_groups.py …")
    refactor(
        ROOT / "concept_groups.py",
        "CONCEPT_GROUPS",
        "data/concept_groups.json",
    )

    print("\nRefactor site/industry_meta.py …")
    refactor(
        ROOT / "site" / "industry_meta.py",
        "INDUSTRY_META",
        "../data/industry_meta.json",
    )

    print("\n完成。下一步：跑 zero-diff hash 驗證 + build_site.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
