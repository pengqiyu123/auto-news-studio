from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path
from typing import Any

SOURCES_ROOT = Path(__file__).resolve().parent
DISCOVERY_FOLDERS = ("hotlists", "rss", "monitors")


def _module_name_from_path(path: Path) -> str:
    relative = path.relative_to(SOURCES_ROOT.parent)
    return ".".join(("backend", "app", *relative.with_suffix("").parts))


def discover_sources() -> list[dict[str, Any]]:
    registry: list[dict[str, Any]] = []
    seen_keys: set[str] = set()

    for folder_name in DISCOVERY_FOLDERS:
        folder = SOURCES_ROOT / folder_name
        if not folder.exists():
            continue
        for module_info in pkgutil.iter_modules([str(folder)]):
            module_path = folder / f"{module_info.name}.py"
            module = importlib.import_module(_module_name_from_path(module_path))
            register = getattr(module, "register", None)
            if not callable(register):
                continue
            for source in register():
                key = str(source.get("key") or "").strip()
                if not key or key in seen_keys:
                    continue
                registry.append(source)
                seen_keys.add(key)

    return registry
