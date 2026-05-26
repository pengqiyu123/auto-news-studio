"""Fix dirty status values in event_deep_dives.

Phase 1 completion: Normalize 'success' -> 'fetched'/'extracted' for 8 records.

Usage:
    python -m scripts.fix_status_values

This script:
1. Reads current state.json
2. Normalizes all fetch_status and extract_status fields
3. Writes new state.json
4. Reports changes made
"""

from __future__ import annotations

import json
from pathlib import Path

from backend.app.db.status_normalizer import (
    normalize_extract_status,
    normalize_fetch_status,
    normalize_state_deep_dives,
)


def main() -> None:
    state_path = Path(__file__).parent.parent / "data" / "state" / "state.json"

    print(f"Reading state from: {state_path}")

    # Read current state
    state = json.loads(state_path.read_text(encoding="utf-8"))

    # Count dirty records BEFORE normalization
    fetch_success_count = 0
    extract_success_count = 0

    for record in state.get("event_deep_dives", []):
        for item in record.get("sources", []):
            if item.get("fetch_status") == "success":
                fetch_success_count += 1
            if item.get("extract_status") == "success":
                extract_success_count += 1

    print(f"\nDirty records found:")
    print(f"  fetch_status = 'success': {fetch_success_count}")
    print(f"  extract_status = 'success': {extract_success_count}")

    total_dirty = fetch_success_count + extract_success_count
    if total_dirty == 0:
        print("\nNo changes needed. State is already clean.")
        return

    # Normalize deep_dives
    original_count = len(state.get("event_deep_dives", []))
    normalized_state = normalize_state_deep_dives(state)
    normalized_count = len(normalized_state.get("event_deep_dives", []))

    print(f"\nNormalized: {original_count} deep_dives -> {normalized_count} deep_dives")
    print(f"Fixed: {total_dirty} dirty status values")

    # Write normalized state
    state_path.write_text(json.dumps(normalized_state, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nOK: New state written to: {state_path}")
    print("\nNext steps:")
    print("  1. Start backend and verify model validation passes")
    print("  2. Run ./auto-news-studio/start.bat")
    print("  3. Check if Pydantic models now accept the data")


if __name__ == "__main__":
    main()
