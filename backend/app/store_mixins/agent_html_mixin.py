from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import hashlib
import json
import re
from pathlib import Path
import sys
from typing import Any
from urllib.parse import urljoin, urlsplit
from uuid import uuid4

from ..deep_dive import canonicalize_url, fetch_and_extract_link
from ..models import (
    AgentHtmlDiscoveryItem,
    AgentHtmlDiscoveryRules,
    AgentHtmlDocument,
    AgentHtmlEvent,
    AgentHtmlEventHistoryItem,
    AgentHtmlRun,
    AgentHtmlTarget,
    AgentHtmlTargetCreatePayload,
    AgentHtmlTargetUpdatePayload,
    SourceSyncResponse,
)
from ..store_base import MAX_RAW_ITEMS, RUNTIME_CACHE_DIR, UTC, atomic_write_json, now_iso, parse_time


class AgentHtmlMixin:
    def _agent_html_cache_root(self) -> Path:
        return RUNTIME_CACHE_DIR / "agent_html"

    def _agent_html_list_cache_dir(self) -> Path:
        return self._agent_html_cache_root() / "list_pages"

    def _agent_html_detail_cache_dir(self) -> Path:
        return self._agent_html_cache_root() / "detail_pages"

    def _agent_html_hash(self, text: str) -> str:
        return hashlib.sha256(str(text or "").strip().encode("utf-8")).hexdigest()

    def _agent_html_clean_text(self, value: str) -> str:
        return re.sub(r"\s+", " ", str(value or "")).strip()

    def _agent_html_cache_write(self, cache_dir: Path, key: str, payload: dict[str, Any]) -> None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        atomic_write_json(cache_dir / f"{key}.json", payload)

    def _agent_html_find_target(self, state: dict[str, Any], target_id: str) -> dict[str, Any]:
        for item in state.get("agent_html_targets", []):
            if isinstance(item, dict) and str(item.get("id") or "") == target_id:
                return item
        raise ValueError(f"未找到 Agent HTML 目标：{target_id}")

    def _agent_html_find_document(self, state: dict[str, Any], document_id: str) -> dict[str, Any]:
        for item in state.get("agent_html_documents", []):
            if isinstance(item, dict) and str(item.get("id") or "") == document_id:
                return item
        raise ValueError(f"未找到 Agent HTML 文档：{document_id}")

    def _agent_html_find_event(self, state: dict[str, Any], event_id: str) -> dict[str, Any]:
        for item in state.get("agent_html_events", []):
            if isinstance(item, dict) and str(item.get("id") or "") == event_id:
                return item
        raise ValueError(f"未找到 Agent HTML 事件：{event_id}")

    def _agent_html_domain(self, url: str) -> str:
        return urlsplit(str(url or "").strip()).netloc.lower()

    @staticmethod
    def _agent_html_fetch_and_extract_link(item: dict[str, Any], *, timeout_seconds: float) -> dict[str, Any]:
        store_module = sys.modules.get("backend.app.store")
        fetcher = getattr(store_module, "fetch_and_extract_link", fetch_and_extract_link) if store_module else fetch_and_extract_link
        return fetcher(item, timeout_seconds=timeout_seconds)

    def create_agent_html_target(self, payload: AgentHtmlTargetCreatePayload) -> AgentHtmlTarget:
        with self._lock:
            state = self._upgrade_state(self._read())
            now = now_iso()
            record = {
                "id": f"aht-{uuid4().hex[:12]}",
                "brand": str(payload.brand).strip(),
                "name": str(payload.name).strip(),
                "entry_url": str(payload.entry_url).strip(),
                "target_type": payload.target_type,
                "enabled": payload.enabled,
                "tags": list(payload.tags),
                "discover_mode": payload.discover_mode,
                "extract_mode": payload.extract_mode,
                "discovery_rules": payload.discovery_rules.model_dump(),
                "last_run_at": None,
                "last_success_at": None,
                "last_error": None,
                "created_at": now,
                "updated_at": now,
            }
            state.setdefault("agent_html_targets", []).insert(0, record)
            self._append_log(state, "success", "agent_html", f"已新增 Agent HTML 目标：{record['name']}")
            self._write(state)
            return AgentHtmlTarget(**record)

    def list_agent_html_targets(self) -> list[AgentHtmlTarget]:
        state = self._read_live()
        items = [item for item in state.get("agent_html_targets", []) if isinstance(item, dict)]
        items.sort(key=lambda item: parse_time(item.get("updated_at")) or datetime.min.replace(tzinfo=UTC), reverse=True)
        return [AgentHtmlTarget(**item) for item in items]

    def update_agent_html_target(self, target_id: str, payload: AgentHtmlTargetUpdatePayload) -> AgentHtmlTarget:
        with self._lock:
            state = self._upgrade_state(self._read())
            target = self._agent_html_find_target(state, target_id)
            updates = payload.model_dump(exclude_none=True)
            for key, value in updates.items():
                target[key] = value.model_dump() if isinstance(value, AgentHtmlDiscoveryRules) else value
            target["updated_at"] = now_iso()
            self._write(state)
            return AgentHtmlTarget(**target)

    def run_agent_html_target(self, target_id: str, *, triggered_by: str = "dashboard") -> AgentHtmlRun:
        with self._lock:
            state = self._upgrade_state(self._read())
            target = self._agent_html_find_target(state, target_id)
            if not bool(target.get("enabled", True)):
                raise ValueError("目标已禁用，无法执行。")
            started_at = now_iso()
            run = {
                "id": f"ahr-{uuid4().hex[:12]}",
                "target_id": target_id,
                "status": "running",
                "started_at": started_at,
                "finished_at": None,
                "discovered_count": 0,
                "new_discovery_count": 0,
                "updated_discovery_count": 0,
                "fetched_count": 0,
                "extracted_count": 0,
                "failed_count": 0,
                "list_fetch_status": "pending",
                "ai_fallback_used": False,
                "error_summary": None,
                "triggered_by": triggered_by,
                "created_at": started_at,
                "updated_at": started_at,
            }
            state.setdefault("agent_html_runs", []).insert(0, run)

            list_meta, list_html = self._agent_html_raw_html_fetch(str(target.get("entry_url") or ""))
            run["list_fetch_status"] = str(list_meta.get("fetch_status") or "fetch_failed")
            cache_key = self._agent_html_hash(str(target.get("entry_url") or "") + "|" + started_at)
            self._agent_html_cache_write(
                self._agent_html_list_cache_dir(),
                cache_key,
                {"meta": list_meta, "html": list_html, "target_id": target_id, "run_id": run["id"]},
            )
            if str(list_meta.get("fetch_status") or "") != "fetched" or not list_html:
                run["status"] = "failed"
                run["error_summary"] = str(list_meta.get("error") or "列表页抓取失败")
                run["finished_at"] = now_iso()
                run["updated_at"] = now_iso()
                target["last_run_at"] = run["finished_at"]
                target["last_error"] = run["error_summary"]
                self._append_log(
                    state,
                    "warning",
                    "agent_html",
                    f"Agent HTML 列表页抓取失败：{target.get('name')}",
                    actor=triggered_by,
                    detail=run["error_summary"],
                )
                self._write(state)
                return AgentHtmlRun(**run)

            candidates, ai_used = self._agent_html_collect_candidates(state, target, list_html)
            run["ai_fallback_used"] = ai_used
            run["discovered_count"] = len(candidates)
            if not candidates:
                run["status"] = "failed"
                run["error_summary"] = "未发现可用候选文章"
                run["finished_at"] = now_iso()
                run["updated_at"] = now_iso()
                target["last_run_at"] = run["finished_at"]
                target["last_error"] = run["error_summary"]
                self._append_log(state, "warning", "agent_html", f"Agent HTML 未发现候选文章：{target.get('name')}", actor=triggered_by)
                self._write(state)
                return AgentHtmlRun(**run)

            document_lookup = {
                str(item.get("canonical_url") or ""): item
                for item in state.get("agent_html_documents", [])
                if isinstance(item, dict) and item.get("canonical_url")
            }
            discovery_records: list[dict[str, Any]] = []
            extracted_count = 0
            new_count = 0
            updated_count = 0
            failed_count = 0

            for candidate in candidates[:20]:
                if not self._agent_html_is_article_candidate(candidate, target):
                    failed_count += 1
                    continue
                detail_meta, detail_html = self._agent_html_raw_html_fetch(str(candidate.get("link") or ""))
                detail_cache_key = self._agent_html_hash(str(candidate.get("link") or "") + "|" + started_at)
                self._agent_html_cache_write(
                    self._agent_html_detail_cache_dir(),
                    detail_cache_key,
                    {"meta": detail_meta, "html": detail_html, "target_id": target_id, "run_id": run["id"]},
                )
                run["fetched_count"] += 1
                if str(detail_meta.get("fetch_status") or "") != "fetched" or not detail_html:
                    failed_count += 1
                    continue
                fetched = self._agent_html_fetch_and_extract_link(
                    {
                        "link": str(candidate.get("link") or ""),
                        "title": str(candidate.get("title") or ""),
                        "source_key": "agent_html",
                        "source_name": str(target.get("name") or ""),
                        "published_at": candidate.get("published_at"),
                    },
                    timeout_seconds=15.0,
                )
                content_text = str(fetched.get("cleaned_full_text") or "")
                content_hash = self._agent_html_hash(content_text) if content_text else ""
                canonical = str(
                    fetched.get("canonical_link")
                    or canonicalize_url(str(candidate.get("link") or ""))
                    or str(candidate.get("link") or "")
                )
                existing_document = document_lookup.get(canonical)
                item_state = "new_item"
                document_id: str | None = None
                if not content_text or str(fetched.get("extract_status") or "") != "extracted":
                    failed_count += 1
                else:
                    extracted_count += 1
                    if existing_document:
                        document_id = str(existing_document.get("id") or "")
                        if str(existing_document.get("current_content_hash") or "") == content_hash:
                            item_state = "seen_item"
                        else:
                            item_state = "updated_item"
                            updated_count += 1
                    else:
                        new_count += 1
                    if existing_document:
                        revision_index = len(
                            [
                                item
                                for item in state.get("agent_html_document_revisions", [])
                                if str(item.get("document_id") or "") == document_id
                            ]
                        ) + 1
                        revision = {
                            "id": f"ahrv-{uuid4().hex[:12]}",
                            "document_id": document_id,
                            "run_id": run["id"],
                            "source_url": str(candidate.get("link") or ""),
                            "title": str(fetched.get("title") or candidate.get("title") or ""),
                            "content_text": content_text,
                            "excerpt": str(fetched.get("excerpt") or "")[:280],
                            "content_hash": content_hash,
                            "word_count": int(fetched.get("word_count", 0) or 0),
                            "extractor": str(fetched.get("extract_status") or ""),
                            "published_at": fetched.get("published_at") or candidate.get("published_at"),
                            "fetched_at": now_iso(),
                            "revision_index": revision_index,
                            "change_summary": "content_updated" if item_state == "updated_item" else "seen_again",
                        }
                        state.setdefault("agent_html_document_revisions", []).insert(0, revision)
                        existing_document["current_revision_id"] = revision["id"]
                        existing_document["title"] = revision["title"]
                        existing_document["published_at"] = revision["published_at"]
                        existing_document["latest_seen_at"] = revision["fetched_at"]
                        existing_document["current_content_hash"] = content_hash
                        existing_document["word_count"] = revision["word_count"]
                        existing_document["extractor"] = str(fetched.get("extract_status") or "")
                        existing_document["updated_at"] = revision["fetched_at"]
                    else:
                        document_id = f"ahdoc-{uuid4().hex[:12]}"
                        revision = {
                            "id": f"ahrv-{uuid4().hex[:12]}",
                            "document_id": document_id,
                            "run_id": run["id"],
                            "source_url": str(candidate.get("link") or ""),
                            "title": str(fetched.get("title") or candidate.get("title") or ""),
                            "content_text": content_text,
                            "excerpt": str(fetched.get("excerpt") or "")[:280],
                            "content_hash": content_hash,
                            "word_count": int(fetched.get("word_count", 0) or 0),
                            "extractor": str(fetched.get("extract_status") or ""),
                            "published_at": fetched.get("published_at") or candidate.get("published_at"),
                            "fetched_at": now_iso(),
                            "revision_index": 1,
                            "change_summary": "initial_capture",
                        }
                        document = {
                            "id": document_id,
                            "target_id": target_id,
                            "canonical_url": canonical,
                            "current_revision_id": revision["id"],
                            "title": revision["title"],
                            "published_at": revision["published_at"],
                            "latest_seen_at": revision["fetched_at"],
                            "current_content_hash": content_hash,
                            "word_count": revision["word_count"],
                            "extractor": str(fetched.get("extract_status") or ""),
                            "first_seen_at": revision["fetched_at"],
                            "updated_at": revision["fetched_at"],
                        }
                        state.setdefault("agent_html_document_revisions", []).insert(0, revision)
                        state.setdefault("agent_html_documents", []).insert(0, document)
                        document_lookup[canonical] = document
                        document_id = document["id"]

                discovery = self._agent_html_build_discovery_item(
                    target,
                    run["id"],
                    candidate,
                    content_hash=content_hash,
                    item_state=item_state,
                    document_id=document_id,
                )
                discovery_records.append(discovery)

            for discovery in discovery_records:
                event = self._agent_html_group_event(state, target, discovery)
                matched_existing = next(
                    (
                        item
                        for item in state.get("agent_html_events", [])
                        if isinstance(item, dict) and str(item.get("id") or "") == str(event.get("id") or "")
                    ),
                    None,
                )
                if matched_existing is None:
                    matched_existing = event
                    state.setdefault("agent_html_events", []).insert(0, matched_existing)
                discovery["event_id"] = matched_existing["id"]
                matched_existing.setdefault("discovery_item_ids", [])
                matched_existing.setdefault("document_ids", [])
                if discovery["id"] not in matched_existing["discovery_item_ids"]:
                    matched_existing["discovery_item_ids"].append(discovery["id"])
                if discovery.get("document_id") and discovery["document_id"] not in matched_existing["document_ids"]:
                    matched_existing["document_ids"].append(discovery["document_id"])
                matched_existing["member_count"] = len(matched_existing["discovery_item_ids"])
                matched_existing["source_count"] = max(1, len({str(target.get("entry_url") or "")}))
                matched_existing["last_seen_at"] = discovery.get("collected_at")
                if matched_existing.get("first_seen_at") is None:
                    matched_existing["first_seen_at"] = discovery.get("collected_at")
                if discovery.get("item_state") == "updated_item":
                    matched_existing["change_state"] = "growing_event"
                elif matched_existing["member_count"] > 1:
                    matched_existing["change_state"] = "growing_event"
                snapshot = {
                    "id": f"ahes-{uuid4().hex[:12]}",
                    "event_id": matched_existing["id"],
                    "captured_at": now_iso(),
                    "member_count": matched_existing["member_count"],
                    "document_count": len(matched_existing["document_ids"]),
                    "source_count": matched_existing["source_count"],
                    "freshness_score": float(matched_existing["member_count"]),
                    "coverage_score": float(len(matched_existing["document_ids"])),
                    "composite_score": float(matched_existing["member_count"]),
                    "change_state": matched_existing["change_state"],
                }
                state.setdefault("agent_html_event_snapshots", []).insert(0, snapshot)
                state.setdefault("agent_html_discovery_items", []).insert(0, discovery)

            self._refresh_agent_html_event_history(state)
            run["new_discovery_count"] = new_count
            run["updated_discovery_count"] = updated_count
            run["extracted_count"] = extracted_count
            run["failed_count"] = failed_count
            run["status"] = "completed" if extracted_count and not failed_count else "partial" if extracted_count else "failed"
            run["finished_at"] = now_iso()
            run["updated_at"] = now_iso()
            target["last_run_at"] = run["finished_at"]
            if run["status"] in {"completed", "partial"}:
                target["last_success_at"] = run["finished_at"]
                target["last_error"] = None if run["status"] == "completed" else f"部分失败：{failed_count}"
            else:
                target["last_error"] = run["error_summary"] or "未成功抽取正文"
            self._append_log(
                state,
                "success" if run["status"] in {"completed", "partial"} else "warning",
                "agent_html",
                f"Agent HTML 已完成：{target.get('name', '未命名目标')}",
                actor=triggered_by,
                detail=f"发现 {run['discovered_count']} 条，新增 {new_count}，更新 {updated_count}，正文成功 {extracted_count}。",
            )
            self._write(state)
            return AgentHtmlRun(**run)

    def run_agent_html_targets_batch(self, target_ids: list[str], *, triggered_by: str = "dashboard") -> list[AgentHtmlRun]:
        results: list[AgentHtmlRun] = []
        ids = [str(item).strip() for item in target_ids if str(item).strip()]
        if not ids:
            raise ValueError("目标列表不能为空。")
        for target_id in ids:
            results.append(self.run_agent_html_target(target_id, triggered_by=triggered_by))
        return results

    def list_agent_html_runs(self) -> list[AgentHtmlRun]:
        state = self._read_live()
        items = [item for item in state.get("agent_html_runs", []) if isinstance(item, dict)]
        items.sort(key=lambda item: parse_time(item.get("created_at")) or datetime.min.replace(tzinfo=UTC), reverse=True)
        return [AgentHtmlRun(**item) for item in items]

    def list_agent_html_discovery(self, *, page: int = 1, page_size: int = 50) -> tuple[list[AgentHtmlDiscoveryItem], int]:
        state = self._read_live()
        all_items = [AgentHtmlDiscoveryItem(**item) for item in state.get("agent_html_discovery_items", []) if isinstance(item, dict)]
        total = len(all_items)
        safe_page = max(1, page)
        safe_page_size = max(1, min(page_size, 200))
        start = (safe_page - 1) * safe_page_size
        end = start + safe_page_size
        return all_items[start:end], total

    def list_agent_html_events(self, *, page: int = 1, page_size: int = 50) -> tuple[list[AgentHtmlEvent], int]:
        state = self._read_live()
        all_items = [AgentHtmlEvent(**item) for item in state.get("agent_html_events", []) if isinstance(item, dict)]
        all_items.sort(key=lambda item: parse_time(item.last_seen_at) or datetime.min.replace(tzinfo=UTC), reverse=True)
        total = len(all_items)
        safe_page = max(1, page)
        safe_page_size = max(1, min(page_size, 200))
        start = (safe_page - 1) * safe_page_size
        end = start + safe_page_size
        return all_items[start:end], total

    def list_agent_html_event_history(self) -> list[AgentHtmlEventHistoryItem]:
        state = self._read_live()
        items = self._prune_agent_html_event_history(state.get("agent_html_event_history", []))
        return [AgentHtmlEventHistoryItem(**item) for item in items]

    def get_agent_html_event(self, event_id: str) -> AgentHtmlEvent:
        state = self._read_live()
        return AgentHtmlEvent(**self._agent_html_find_event(state, event_id))

    def list_agent_html_documents(self, *, page: int = 1, page_size: int = 50) -> tuple[list[AgentHtmlDocument], int]:
        state = self._read_live()
        revisions_by_document: dict[str, list[dict[str, Any]]] = {}
        for item in state.get("agent_html_document_revisions", []):
            if not isinstance(item, dict):
                continue
            revisions_by_document.setdefault(str(item.get("document_id") or ""), []).append(item)
        documents: list[AgentHtmlDocument] = []
        for item in state.get("agent_html_documents", []):
            if not isinstance(item, dict):
                continue
            payload = deepcopy(item)
            payload["revisions"] = revisions_by_document.get(str(item.get("id") or ""), [])
            documents.append(AgentHtmlDocument(**payload))
        documents.sort(key=lambda item: parse_time(item.updated_at) or datetime.min.replace(tzinfo=UTC), reverse=True)
        total = len(documents)
        safe_page = max(1, page)
        safe_page_size = max(1, min(page_size, 200))
        start = (safe_page - 1) * safe_page_size
        end = start + safe_page_size
        return documents[start:end], total

    def _rebuild_mainline_from_raw_items(
        self,
        state: dict[str, Any],
        *,
        triggered_by: str,
        work_scope_override: str | None = None,
    ) -> SourceSyncResponse:
        stamp = now_iso()
        raw_items = [item for item in state.get("raw_items", []) if isinstance(item, dict)]
        raw_items = sorted(raw_items, key=lambda item: item.get("collected_at") or "", reverse=True)[:MAX_RAW_ITEMS]
        state["raw_items"] = raw_items
        self._rebuild_candidates_for_state(state, work_scope_override=work_scope_override)
        runtime = self._runtime(state)
        runtime["last_collect_at"] = stamp
        if raw_items:
            runtime["last_successful_sync_at"] = stamp
        runtime["next_collect_at"] = self._calculate_next_collect_at(
            state,
            minimum_interval_minutes=self._collect_interval_for_profile(state),
        )
        self._append_log(
            state,
            "success" if raw_items else "warning",
            "collection",
            f"已重建主链素材池：{len(raw_items)} 条素材，{len(state.get('intel_events', []))} 个事件。",
            stream="business_event",
            actor=triggered_by,
        )
        return SourceSyncResponse(
            raw_count=len(raw_items),
            normalized_count=len(state.get("normalized_items", [])),
            event_count=len(state.get("intel_events", [])),
            synced_at=stamp,
            warnings=[],
        )

    def sync_agent_html_into_mainline(self, target_ids: list[str], *, triggered_by: str = "dashboard") -> SourceSyncResponse:
        with self._lock:
            state = self._upgrade_state(self._read())
            ids = [str(item).strip() for item in target_ids if str(item).strip()]
            if not ids:
                raise ValueError("目标列表不能为空。")
            for target_id in ids:
                self.run_agent_html_target(target_id, triggered_by=triggered_by).model_dump()
                state = self._upgrade_state(self._read())
            active_targets = {
                str(item.get("id") or ""): item
                for item in state.get("agent_html_targets", [])
                if isinstance(item, dict) and str(item.get("id") or "") in ids
            }
            documents_by_id = {
                str(item.get("id") or ""): item
                for item in state.get("agent_html_documents", [])
                if isinstance(item, dict) and str(item.get("target_id") or "") in ids
            }
            revisions_by_id = {
                str(item.get("id") or ""): item
                for item in state.get("agent_html_document_revisions", [])
                if isinstance(item, dict)
            }
            html_source_keys = {f"html-{target_id}" for target_id in ids}
            existing_raw = [
                item
                for item in state.get("raw_items", [])
                if isinstance(item, dict) and str(item.get("source_key") or "") not in html_source_keys
            ]
            new_raw_items: list[dict[str, Any]] = []
            for document in documents_by_id.values():
                target = active_targets.get(str(document.get("target_id") or ""))
                if not target:
                    continue
                current_revision = revisions_by_id.get(str(document.get("current_revision_id") or ""))
                if not current_revision:
                    continue
                raw_item = self._agent_html_map_document_to_raw_item(target, document, current_revision)
                new_raw_items.append(raw_item)
            merged_by_id: dict[str, dict[str, Any]] = {}
            for item in existing_raw + new_raw_items:
                merged_by_id[str(item.get("id") or "")] = item
            state["raw_items"] = sorted(
                merged_by_id.values(),
                key=lambda item: item.get("collected_at") or "",
                reverse=True,
            )[:MAX_RAW_ITEMS]
            response = self._rebuild_mainline_from_raw_items(state, triggered_by=triggered_by)
            html_ok = len(new_raw_items)
            self._append_log(
                state,
                "success" if html_ok else "warning",
                "agent_html",
                f"Agent HTML 已并入主链：{html_ok} 条 HTML 素材进入 raw_items。",
                actor=triggered_by,
            )
            self._write(state)
            return response

    def get_agent_html_document(self, document_id: str) -> AgentHtmlDocument:
        state = self._read_live()
        document = deepcopy(self._agent_html_find_document(state, document_id))
        revisions = [
            item
            for item in state.get("agent_html_document_revisions", [])
            if isinstance(item, dict) and str(item.get("document_id") or "") == document_id
        ]
        revisions.sort(key=lambda item: int(item.get("revision_index", 0) or 0), reverse=True)
        document["revisions"] = revisions
        return AgentHtmlDocument(**document)

    def reextract_agent_html_document(self, document_id: str, *, triggered_by: str = "dashboard") -> AgentHtmlDocument:
        with self._lock:
            state = self._upgrade_state(self._read())
            document = self._agent_html_find_document(state, document_id)
            latest_revision = next(
                (
                    item
                    for item in state.get("agent_html_document_revisions", [])
                    if isinstance(item, dict)
                    and str(item.get("id") or "") == str(document.get("current_revision_id") or "")
                ),
                None,
            )
            if not latest_revision:
                raise ValueError("未找到文档当前版本，无法重新提取。")
            fetched = self._agent_html_fetch_and_extract_link(
                {
                    "link": str(latest_revision.get("source_url") or document.get("canonical_url") or ""),
                    "title": str(document.get("title") or ""),
                    "source_key": "agent_html",
                    "source_name": "Agent HTML",
                    "published_at": document.get("published_at"),
                },
                timeout_seconds=15.0,
            )
            content_text = str(fetched.get("cleaned_full_text") or "")
            if not content_text or str(fetched.get("extract_status") or "") != "extracted":
                raise ValueError(str(fetched.get("error") or "正文重新提取失败。"))
            content_hash = self._agent_html_hash(content_text)
            revision_index = (
                len(
                    [
                        item
                        for item in state.get("agent_html_document_revisions", [])
                        if str(item.get("document_id") or "") == document_id
                    ]
                )
                + 1
            )
            revision = {
                "id": f"ahrv-{uuid4().hex[:12]}",
                "document_id": document_id,
                "run_id": "manual-reextract",
                "source_url": str(latest_revision.get("source_url") or document.get("canonical_url") or ""),
                "title": str(fetched.get("title") or document.get("title") or ""),
                "content_text": content_text,
                "excerpt": str(fetched.get("excerpt") or "")[:280],
                "content_hash": content_hash,
                "word_count": int(fetched.get("word_count", 0) or 0),
                "extractor": str(fetched.get("extract_status") or ""),
                "published_at": fetched.get("published_at") or document.get("published_at"),
                "fetched_at": now_iso(),
                "revision_index": revision_index,
                "change_summary": "manual_reextract",
            }
            state.setdefault("agent_html_document_revisions", []).insert(0, revision)
            document["current_revision_id"] = revision["id"]
            document["title"] = revision["title"]
            document["published_at"] = revision["published_at"]
            document["latest_seen_at"] = revision["fetched_at"]
            document["current_content_hash"] = content_hash
            document["word_count"] = revision["word_count"]
            document["extractor"] = str(fetched.get("extract_status") or "")
            document["updated_at"] = revision["fetched_at"]
            self._append_log(state, "success", "agent_html", f"已重新提取 Agent HTML 文档：{document.get('title')}", actor=triggered_by)
            self._write(state)
            return self.get_agent_html_document(document_id)
