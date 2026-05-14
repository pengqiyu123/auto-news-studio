from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType


_LEGACY_MODULE_NAME = "backend.app._publishers_legacy"


def load_legacy_publishers() -> ModuleType:
    module = sys.modules.get(_LEGACY_MODULE_NAME)
    if module is not None:
        return module

    legacy_path = Path(__file__).resolve().parents[1] / "publishers.py"
    spec = importlib.util.spec_from_file_location(_LEGACY_MODULE_NAME, legacy_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载旧版 publishers 模块：{legacy_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[_LEGACY_MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


legacy_publishers = load_legacy_publishers()

__all__ = ["legacy_publishers", "load_legacy_publishers"]
