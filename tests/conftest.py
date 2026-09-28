"""Shared pytest setup.

The ingestion scripts are standalone modules in hyphenated directories
(not packages), several share a file name (backfill.py, wipe_dlt.py), and
most read BIGQUERY_SERVICE_ACCOUNT_JSON at import time. `load_module`
imports one by path under a unique name, with its own directory on
sys.path so its sibling imports (`from utils import ...`) resolve.

The tests never touch BigQuery or the network: when the real key is
absent (CI, fresh checkout) a dummy one is set so module-level
`json.loads(...)` succeeds.
"""

import importlib.util
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"

os.environ.setdefault(
    "BIGQUERY_SERVICE_ACCOUNT_JSON", '{"project_id": "test-project"}'
)


def load_module(relpath: str, name: str):
    """Import REPO_ROOT/relpath as module `name` (cached across tests)."""
    if name in sys.modules:
        return sys.modules[name]
    path = REPO_ROOT / relpath
    module_dir = str(path.parent)
    if module_dir not in sys.path:
        sys.path.insert(0, module_dir)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES
