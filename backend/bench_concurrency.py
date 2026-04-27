"""并发基准测试 — 测量不同 max_workers 下的采集耗时，找到最优值。

用法:
    cd auto-news-studio/backend
    python bench_concurrency.py

会依次用 max_workers = 1, 3, 5, 8, 10, 15 采集所有已启用来源，
打印每轮的总耗时、成功数、失败数，最后给出推荐值。
"""
from __future__ import annotations

import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

sys.path.insert(0, ".")

from app.connectors import _collect_with_retry
from app.sources import discover_sources

WORKER_LEVELS = [1, 3, 5, 8, 10, 15]

STATE_FILE = Path(__file__).resolve().parent.parent / "studio_state.json"


def load_enabled_sources() -> list[dict[str, Any]]:
    """Load sources from state.json (user-modified), fall back to registry defaults."""
    state_paths = [
        Path(__file__).resolve().parent / "data" / "state.json",
        Path(__file__).resolve().parent.parent / "studio_state.json",
    ]
    for path in state_paths:
        if path.exists():
            try:
                with open(path, encoding="utf-8") as f:
                    state = json.load(f)
                sources = state.get("sources", [])
                enabled = [s for s in sources if s.get("enabled")]
                if enabled:
                    return enabled
            except Exception:
                continue
    # Fall back to registry (requires being run as module)
    try:
        all_sources = discover_sources()
        return [s for s in all_sources if s.get("enabled")]
    except ImportError:
        print("无法加载来源：state.json 不存在且 registry 导入失败")
        return []


def collect_with_workers(
    sources: list[dict[str, Any]], max_workers: int
) -> tuple[float, int, int, list[str]]:
    start = time.perf_counter()
    success_count = 0
    fail_count = 0
    errors: list[str] = []

    def _safe(source: dict[str, Any]) -> tuple[int, int, str]:
        try:
            items, warning = _collect_with_retry(source)
            return len(items), 0, warning or ""
        except Exception as exc:
            return 0, 1, f"{source['name']}: {exc}"

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_safe, s): s for s in sources}
        for future in as_completed(futures):
            item_count, failed, msg = future.result()
            if failed:
                fail_count += 1
                errors.append(msg)
            else:
                success_count += 1

    elapsed = time.perf_counter() - start
    return elapsed, success_count, fail_count, errors


def main() -> None:
    enabled = load_enabled_sources()

    if not enabled:
        print("没有已启用的来源，无法测试。")
        return

    print(f"已启用来源: {len(enabled)} 个")
    print(f"来源列表:")
    for s in enabled:
        print(f"  - {s['name']} ({s['kind']}, driver={s.get('driver', '?')})")
    print()

    results: list[tuple[int, float, int, int]] = []

    for workers in WORKER_LEVELS:
        print(f"max_workers = {workers:>2} ...", end=" ", flush=True)
        elapsed, success, fail, errors = collect_with_workers(enabled, workers)
        results.append((workers, elapsed, success, fail))
        print(f"{elapsed:>6.1f}s  成功 {success}  失败 {fail}")
        if errors:
            for err in errors[:3]:
                print(f"    ! {err}")
            if len(errors) > 3:
                print(f"    ... 还有 {len(errors) - 3} 个错误")

    print()
    print("=" * 50)
    print("结果汇总:")
    print(f"{'workers':>8}  {'耗时(s)':>8}  {'成功':>4}  {'失败':>4}")
    print("-" * 40)
    for workers, elapsed, success, fail in results:
        print(f"{workers:>8}  {elapsed:>8.1f}  {success:>4}  {fail:>4}")

    no_fail = [(w, t) for w, t, s, f in results if f == 0]
    if no_fail:
        recommended = min(no_fail, key=lambda x: x[1])[0]
        print(f"\n推荐 max_workers = {recommended}  (无失败，耗时最短)")
    else:
        best = min(results, key=lambda x: (x[3], x[1]))
        recommended = best[0]
        print(f"\n推荐 max_workers = {recommended}  (所有轮次均有失败，选失败最少且最快)")

    print()
    print("注意:")
    print("  - 结果受网络环境影响，建议在不同时段跑 2-3 次取平均")
    print("  - 如果失败数随 workers 增加而上升，说明目标服务器有连接限制")
    print("  - 推荐值应留有余量（比最优值低 1-2 档），避免高峰期超时")


if __name__ == "__main__":
    main()
