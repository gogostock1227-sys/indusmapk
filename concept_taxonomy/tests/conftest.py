"""
pytest 共用 fixture：
  - specs_path / profiles_path / known_issues_path
  - load_specs() / load_profiles() / load_known_issues()
  - 把 concept_taxonomy 父目錄加入 sys.path，以利 `from validator.xxx import ...`
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

# 讓測試可以 import validator.*（pytest 從 concept_taxonomy/tests 跑時）
TAXONOMY_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = TAXONOMY_DIR.parent
sys.path.insert(0, str(TAXONOMY_DIR))


@pytest.fixture(scope="session")
def specs_path() -> Path:
    return TAXONOMY_DIR / "group_specs.json"


@pytest.fixture(scope="session")
def profiles_path() -> Path:
    return TAXONOMY_DIR / "tests" / "fixtures" / "test_profiles.json"


@pytest.fixture(scope="session")
def known_issues_path() -> Path:
    return TAXONOMY_DIR / "tests" / "known_issues.yaml"


@pytest.fixture(scope="session")
def specs(specs_path: Path) -> dict:
    return json.loads(specs_path.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def profiles(profiles_path: Path) -> dict:
    return json.loads(profiles_path.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def known_issues(known_issues_path: Path) -> list[dict]:
    return yaml.safe_load(known_issues_path.read_text(encoding="utf-8"))
