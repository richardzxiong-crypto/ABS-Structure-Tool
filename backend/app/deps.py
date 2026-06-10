import os
from functools import lru_cache
from pathlib import Path

from absengine.library import DealLibrary


@lru_cache
def get_library() -> DealLibrary:
    root = os.environ.get("ABS_DEALS_DIR")
    if root is None:
        # repo_root/deals (this file lives at backend/app/deps.py)
        root = Path(__file__).resolve().parents[2] / "deals"
    return DealLibrary(Path(root))
