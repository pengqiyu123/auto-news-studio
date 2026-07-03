from __future__ import annotations

import importlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
import shutil
import sys
import tempfile
import types

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

if "openai" not in sys.modules:
    openai_stub = types.ModuleType("openai")

    class _OpenAIError(Exception):
        pass

    class _OpenAI:
        def __init__(self, *args, **kwargs) -> None:
            pass

    openai_stub.APIConnectionError = _OpenAIError
    openai_stub.APITimeoutError = _OpenAIError
    openai_stub.AuthenticationError = _OpenAIError
    openai_stub.BadRequestError = _OpenAIError
    openai_stub.InternalServerError = _OpenAIError
    openai_stub.NotFoundError = _OpenAIError
    openai_stub.OpenAI = _OpenAI
    openai_stub.RateLimitError = _OpenAIError
    sys.modules["openai"] = openai_stub

if "trafilatura" not in sys.modules:
    trafilatura_stub = types.ModuleType("trafilatura")
    trafilatura_stub.extract = lambda *args, **kwargs: ""
    sys.modules["trafilatura"] = trafilatura_stub

if "readability" not in sys.modules:
    readability_stub = types.ModuleType("readability")

    class _Document:
        def __init__(self, html: str) -> None:
            self._html = html

        def summary(self, html_partial: bool = True) -> str:
            return self._html

    readability_stub.Document = _Document
    sys.modules["readability"] = readability_stub

if "python_multipart" not in sys.modules:
    python_multipart_stub = types.ModuleType("python_multipart")
    python_multipart_stub.__version__ = "0.0.20"
    sys.modules["python_multipart"] = python_multipart_stub

if "multipart" not in sys.modules:
    multipart_stub = types.ModuleType("multipart")
    multipart_stub.__version__ = "0.0.20"
    sys.modules["multipart"] = multipart_stub

if "multipart.multipart" not in sys.modules:
    multipart_multipart_stub = types.ModuleType("multipart.multipart")
    multipart_multipart_stub.parse_options_header = lambda value: ("", {})
    sys.modules["multipart.multipart"] = multipart_multipart_stub

from backend.app.db import models  # noqa: F401
from backend.app.db.analysis_projection import sync_analysis_projection_from_events
from backend.app.db.base import Base
from backend.app.intel.pipeline import build_intel_state
from backend.app.routes.common import set_store
from backend.app.store import get_studio_store_class


UTC = timezone.utc
StudioStore = get_studio_store_class()


def _event(
    event_id: str,
    *,
    title: str,
    entity_ids: list[str],
    entity_names: list[str],
    anchor_tokens: list[str],
    first_seen_at: str,
    composite_score: float = 50.0,
    velocity_score: float = 10.0,
) -> dict:
    return {
        "id": event_id,
        "title": title,
        "summary": f"{title} summary",
        "representative_link": f"https://example.com/{event_id}",
        "representative_source_name": "RSS",
        "representative_discovery_item_id": f"disc-{event_id}",
        "discovery_item_ids": [f"disc-{event_id}"],
        "source_keys": ["rss"],
        "source_names": ["RSS"],
        "platforms": ["rss"],
        "platform_count": 1,
        "source_count": 1,
        "member_count": 1,
        "story_count": 1,
        "member_delta": 0,
        "platform_delta": 0,
        "published_at": first_seen_at,
        "latest_collected_at": first_seen_at,
        "first_seen_at": first_seen_at,
        "last_seen_at": first_seen_at,
        "tags": ["ai"],
        "anchor_tokens": anchor_tokens,
        "velocity_score": velocity_score,
        "coverage_score": 50.0,
        "freshness_score": 50.0,
        "audience_fit_score": 50.0,
        "composite_score": composite_score,
        "velocity_details": {},
        "alert_state": "watch",
        "change_state": "new_event",
        "alert_reason": "",
        "entity_ids": entity_ids,
        "entity_names": entity_names,
        "watchlisted": False,
        "ignored": False,
        "deep_dive_id": None,
        "brief_id": None,
        "deep_dive_status": None,
        "brief_status": None,
        "deep_dive_summary": "",
        "worth_to_brief": False,
        "worth_reason": "",
    }


def _snapshot(event_id: str, day_offset: int, count: int) -> dict:
    captured = datetime(2026, 5, 1, tzinfo=UTC) + timedelta(days=day_offset)
    return {
        "id": f"snap-{event_id}-{day_offset}",
        "event_id": event_id,
        "captured_at": captured.isoformat(),
        "member_count": count,
        "platform_count": 1,
        "source_count": count,
        "velocity_score": float(count),
        "coverage_score": 10.0,
        "freshness_score": 10.0,
        "audience_fit_score": 10.0,
        "composite_score": float(count * 10),
        "alert_state": "watch",
    }


def test_snapshot_retention_defaults_to_30_days(monkeypatch) -> None:
    monkeypatch.delenv("SNAPSHOT_RETENTION_HOURS", raising=False)
    captured_at = "2026-05-31T00:00:00+00:00"
    previous_snapshots = [
        {"id": "old", "event_id": "evt-old", "captured_at": "2026-04-30T23:59:00+00:00"},
        {"id": "recent", "event_id": "evt-recent", "captured_at": "2026-05-10T00:00:00+00:00"},
    ]

    intel = build_intel_state([], {}, previous_snapshots=previous_snapshots, captured_at=captured_at)

    retained_ids = {item["id"] for item in intel["event_snapshots"]}
    assert "recent" in retained_ids
    assert "old" not in retained_ids


def test_tokenizer_extracts_chinese_words_without_changing_title_tokenizer() -> None:
    from backend.app.intel.pipeline import tokenize_title
    from backend.app.intel.tokenizer import tokenize_for_analysis

    tokens = tokenize_for_analysis("OpenAI 发布医疗 AI 智能体，苹果加速端侧模型")

    assert "openai" in tokens
    assert "医疗" in tokens or "智能体" in tokens
    assert "发布" not in tokens
    assert tokenize_title("OpenAI 发布医疗 AI 智能体")


def test_topic_model_and_relation_detection() -> None:
    from backend.app.intel.correlation import build_event_relations
    from backend.app.intel.topics import build_topic_model

    events = [
        _event(
            "evt-1",
            title="OpenAI 医疗 AI 智能体发布",
            entity_ids=["openai", "health"],
            entity_names=["OpenAI", "医疗"],
            anchor_tokens=["openai", "health"],
            first_seen_at="2026-05-28T10:00:00+00:00",
        ),
        _event(
            "evt-2",
            title="OpenAI 医疗模型进入医院测试",
            entity_ids=["openai", "health"],
            entity_names=["OpenAI", "医疗"],
            anchor_tokens=["openai", "health", "hospital"],
            first_seen_at="2026-05-29T10:00:00+00:00",
        ),
        _event(
            "evt-3",
            title="Uber 自动驾驶合作传闻",
            entity_ids=["uber"],
            entity_names=["Uber"],
            anchor_tokens=["uber", "robotaxi"],
            first_seen_at="2026-05-29T11:00:00+00:00",
        ),
    ]

    topics = build_topic_model(events, topic_count=3)
    relations = build_event_relations(events, topics.event_topics)

    assert topics.topics
    assert any(topic.event_count >= 2 for topic in topics.topics)
    related_pair = {(item.source_event_id, item.target_event_id) for item in relations}
    assert ("evt-1", "evt-2") in related_pair
    assert all(item.weight >= 0.4 for item in relations)


def test_trend_detection_marks_emerging_and_insufficient_data() -> None:
    from backend.app.intel.trends import aggregate_daily_metrics, detect_trends

    events = [
        _event(
            "evt-openai",
            title="OpenAI update",
            entity_ids=["openai"],
            entity_names=["OpenAI"],
            anchor_tokens=["openai"],
            first_seen_at="2026-05-20T10:00:00+00:00",
        )
    ]
    snapshots = [_snapshot("evt-openai", day, 1 if day < 10 else 5) for day in range(17)]
    metrics = aggregate_daily_metrics(events, snapshots)
    trends = detect_trends(metrics, as_of=datetime(2026, 5, 17, tzinfo=UTC).date())

    assert trends[0].entity_id == "openai"
    assert trends[0].trend in {"hot", "emerging"}
    assert trends[0].signals
    short = detect_trends(metrics[:5], as_of=datetime(2026, 5, 5, tzinfo=UTC).date())
    assert short[0].trend == "insufficient_data"


def test_periodicity_detects_weekly_topic_cycle() -> None:
    from backend.app.intel.periodicity import detect_topic_periodicity
    from backend.app.intel.topics import EventTopic, TopicInfo, TopicModelResult

    topics = TopicModelResult(
        topics=[TopicInfo(topic_id="topic-weekly", label="OpenAI / 医疗", keywords=["OpenAI"], event_count=5)],
        event_topics=[
            EventTopic(event_id=f"evt-{day}", topic_id="topic-weekly", weight=1.0)
            for day in (0, 7, 14, 21, 28)
        ],
    )
    events = [
        _event(
            f"evt-{day}",
            title=f"OpenAI weekly update {day}",
            entity_ids=["openai"],
            entity_names=["OpenAI"],
            anchor_tokens=["openai", "weekly"],
            first_seen_at=(datetime(2026, 5, 1, tzinfo=UTC) + timedelta(days=day)).isoformat(),
        )
        for day in (0, 7, 14, 21, 28)
    ]

    results = detect_topic_periodicity(events, topics, min_confidence=0.2)

    assert results
    assert results[0].topic_id == "topic-weekly"
    assert results[0].period_days == 7
    assert results[0].confidence >= 0.2


def test_temporal_rules_detect_following_event_pattern() -> None:
    from backend.app.intel.correlation import EventRelationInfo
    from backend.app.intel.temporal_rules import mine_temporal_association_rules

    events = [
        _event(
            f"evt-a-{index}",
            title=f"Chip supply signal {index}",
            entity_ids=["chip"],
            entity_names=["芯片"],
            anchor_tokens=["chip", "supply"],
            first_seen_at=(datetime(2026, 5, 1, tzinfo=UTC) + timedelta(days=index * 4)).isoformat(),
        )
        for index in range(3)
    ] + [
        _event(
            f"evt-b-{index}",
            title=f"Device launch signal {index}",
            entity_ids=["device"],
            entity_names=["终端"],
            anchor_tokens=["device", "launch"],
            first_seen_at=(datetime(2026, 5, 2, tzinfo=UTC) + timedelta(days=index * 4)).isoformat(),
        )
        for index in range(3)
    ]
    relations = [
        EventRelationInfo(
            id=f"rel-{index}",
            source_event_id=f"evt-a-{index}",
            target_event_id=f"evt-b-{index}",
            relation_type="topic_shared+temporal_proximity",
            weight=0.8,
            evidence={},
        )
        for index in range(3)
    ]

    rules = mine_temporal_association_rules(events, relations, min_support=0.1, min_confidence=0.5)

    assert rules
    assert rules[0].antecedent_event_id.startswith("evt-a-")
    assert rules[0].consequent_event_id.startswith("evt-b-")
    assert rules[0].lag_days == 1
    assert rules[0].confidence >= 0.5


def test_analysis_routes_return_topics_related_events_and_trends() -> None:
    temp_root = Path(tempfile.mkdtemp(prefix="incremental-analysis-"))
    try:
        store = StudioStore(data_file=temp_root / "state.json")
        state = store._bootstrap_state()
        events = [
            _event(
                "evt-1",
                title="OpenAI 医疗 AI 智能体发布",
                entity_ids=["openai", "health"],
                entity_names=["OpenAI", "医疗"],
                anchor_tokens=["openai", "health"],
                first_seen_at="2026-05-20T10:00:00+00:00",
                composite_score=70.0,
            ),
            _event(
                "evt-2",
                title="OpenAI 医疗模型进入医院测试",
                entity_ids=["openai", "health"],
                entity_names=["OpenAI", "医疗"],
                anchor_tokens=["openai", "health", "hospital"],
                first_seen_at="2026-05-21T10:00:00+00:00",
                composite_score=65.0,
            ),
        ]
        state["intel_events"] = events
        state["event_snapshots"] = [_snapshot("evt-1", day, 1 if day < 10 else 5) for day in range(17)]
        store._write(state)

        import backend.app.main as main_module

        main_module = importlib.reload(main_module)
        main_module.store = store
        set_store(store)
        client = TestClient(main_module.app)

        topics = client.get("/api/admin/topics")
        related = client.get("/api/admin/events/evt-1/related")
        trends = client.get("/api/admin/trends")
        signals = client.get("/api/admin/analysis/signals")
        topic_events = client.get("/api/admin/topics/topic-00/events")
        feedback = client.post(
            "/api/admin/analysis/feedback",
            json={
                "target_type": "analysis_summary",
                "target_id": "openai",
                "feedback_type": "correct",
                "correction": {"note": "OpenAI 权重偏高"},
            },
        )
        report = client.post(
            "/api/admin/analysis/report",
            json={
                "scope": "weekly",
                "date_from": "2026-05-20",
                "date_to": "2026-05-29",
                "focus_entities": ["openai"],
                "focus_topics": ["topic-00"],
            },
        )
        reports = client.get("/api/admin/analysis/reports")
        feedback_stats = client.get("/api/admin/analysis/feedback/stats")
        periodicity = client.get("/api/admin/topics/periodicity")
        temporal_rules = client.get("/api/admin/analysis/temporal-rules")

        assert topics.status_code == 200
        assert topics.json()["items"]
        assert related.status_code == 200
        assert related.json()["items"][0]["event_id"] == "evt-2"
        assert trends.status_code == 200
        assert trends.json()["items"][0]["entity_name"] == "OpenAI"
        assert signals.status_code == 200
        assert signals.json()["items"][0]["entity_name"] == "OpenAI"
        assert "recent_event_count" in signals.json()["items"][0]
        assert "latest_event_title" in signals.json()["items"][0]
        assert topic_events.status_code == 200
        assert topic_events.json()["items"][0]["event_id"] in {"evt-1", "evt-2"}
        assert "composite_score" in topic_events.json()["items"][0]
        assert feedback.status_code == 200
        assert feedback.json()["ok"] is True
        stored_feedback = store._read().get("analysis_feedback", [])
        assert stored_feedback[0]["feedback_type"] == "correct"
        assert stored_feedback[0]["correction"]["note"] == "OpenAI 权重偏高"
        assert report.status_code == 200
        report_item = report.json()["item"]
        assert report_item["status"] == "no_llm"
        assert report_item["scope"] == "weekly"
        assert "周度" in report_item["markdown"] or "周报" in report_item["markdown"]
        assert "研判报告" in report_item["markdown"]
        assert report_item["sections"]["executive_summary"]
        stored_reports = store._read().get("analysis_reports", [])
        assert stored_reports[0]["id"] == report_item["report_id"]
        assert reports.status_code == 200
        assert reports.json()["items"][0]["report_id"] == report_item["report_id"]
        report_detail = client.get(f"/api/admin/analysis/reports/{report_item['report_id']}")
        assert report_detail.status_code == 200
        assert report_detail.json()["item"]["markdown"] == report_item["markdown"]
        assert feedback_stats.status_code == 200
        assert feedback_stats.json()["total"] == 1
        assert feedback_stats.json()["by_type"]["correct"] == 1
        assert periodicity.status_code == 200
        assert "items" in periodicity.json()
        assert temporal_rules.status_code == 200
        assert "items" in temporal_rules.json()
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_report_generator_uses_llm_json_when_available() -> None:
    from backend.app.features.analysis.report_generator import generate_analysis_report
    from backend.app.models import AnalysisReportRequest

    class FakeLLM:
        def generate(self, task_key, messages, temperature=None, max_tokens=None, timeout=None):
            assert task_key == "article"
            assert any("只输出 JSON" in message["content"] for message in messages)
            return {
                "content": """
                {
                  "sections": {
                    "executive_summary": "OpenAI 医疗主题升温。",
                    "key_findings": "两条事件共享实体和主题。",
                    "risk_assessment": "样本仍偏少。",
                    "recommendation": "继续跟踪医院落地进展。"
                  },
                  "markdown": "# 研判报告\\n\\n## 主结论\\nOpenAI 医疗主题升温。"
                }
                """,
                "model": "fake-model",
            }

    report = generate_analysis_report(
        AnalysisReportRequest(scope="weekly", date_from="2026-05-20", date_to="2026-05-29"),
        events=[
            _event(
                "evt-1",
                title="OpenAI 医疗 AI 智能体发布",
                entity_ids=["openai"],
                entity_names=["OpenAI"],
                anchor_tokens=["openai", "health"],
                first_seen_at="2026-05-20T10:00:00+00:00",
            )
        ],
        topics=[{"topic_id": "topic-00", "label": "OpenAI / 医疗", "event_count": 1}],
        signals=[{"entity_name": "OpenAI", "trend_label": "近7天持续上升", "recent_event_count": 1}],
        llm_service=FakeLLM(),
        report_id="report-test",
    )

    assert report.status == "ready"
    assert report.report_id == "report-test"
    assert report.sections.executive_summary == "OpenAI 医疗主题升温。"
    assert "主结论" in report.markdown


def test_weekly_digest_includes_temporal_rules_in_llm_payload() -> None:
    from backend.app.features.analysis.report_generator import generate_weekly_digest
    from backend.app.models import AnalysisReportRequest

    class FakeLLM:
        def generate(self, task_key, messages, temperature=None, max_tokens=None, timeout=None):
            assert task_key == "article"
            assert "temporal_rules" in messages[1]["content"]
            assert "OpenAI 发布" in messages[1]["content"]
            return {
                "content": """
                {
                  "sections": {
                    "executive_summary": "周度主题继续升温。",
                    "key_findings": "时序规则显示发布后两天出现落地事件。",
                    "risk_assessment": "规则样本仍少。",
                    "recommendation": "跟踪后续落地。"
                  },
                  "markdown": "# 周度情报摘要\\n\\n## 主结论\\n周度主题继续升温。"
                }
                """
            }

    report = generate_weekly_digest(
        AnalysisReportRequest(scope="weekly", date_from="2026-05-20", date_to="2026-05-29"),
        events=[
            _event(
                "evt-1",
                title="OpenAI 发布",
                entity_ids=["openai"],
                entity_names=["OpenAI"],
                anchor_tokens=["openai"],
                first_seen_at="2026-05-20T10:00:00+00:00",
            )
        ],
        topics=[{"topic_id": "topic-00", "label": "OpenAI / 医疗", "event_count": 1}],
        signals=[{"entity_name": "OpenAI", "trend": "emerging", "recent_event_count": 1}],
        temporal_rules=[{"antecedent_title": "OpenAI 发布", "consequent_title": "医疗落地", "lag_days": 2, "confidence": 0.8}],
        llm_service=FakeLLM(),
        report_id="report-weekly",
    )

    assert report.status == "ready"
    assert report.report_id == "report-weekly"
    assert report.sections.key_findings.startswith("时序规则")


def test_analysis_projection_populates_new_tables() -> None:
    temp_root = Path(tempfile.mkdtemp(prefix="analysis-projection-"))
    database_url = f"sqlite:///{temp_root / 'analysis.sqlite3'}"
    engine = create_engine(database_url, future=True)
    try:
        Base.metadata.create_all(bind=engine)
        events = [
            _event(
                "evt-1",
                title="OpenAI 医疗 AI 智能体发布",
                entity_ids=["openai", "health"],
                entity_names=["OpenAI", "医疗"],
                anchor_tokens=["openai", "health"],
                first_seen_at="2026-05-20T10:00:00+00:00",
            ),
            _event(
                "evt-2",
                title="OpenAI 医疗模型进入医院测试",
                entity_ids=["openai", "health"],
                entity_names=["OpenAI", "医疗"],
                anchor_tokens=["openai", "health", "hospital"],
                first_seen_at="2026-05-21T10:00:00+00:00",
            ),
        ]
        snapshots = [_snapshot("evt-1", day, 1 if day < 10 else 5) for day in range(17)]

        counts = sync_analysis_projection_from_events(events, snapshots, database_url=database_url)

        with engine.connect() as conn:
            topic_count = conn.execute(text("select count(*) from topic_models")).scalar_one()
            relation_count = conn.execute(text("select count(*) from event_relations")).scalar_one()
            metric_count = conn.execute(text("select count(*) from daily_event_metrics")).scalar_one()
            periodicity_count = conn.execute(text("select count(*) from topic_periodicity")).scalar_one()
            rule_count = conn.execute(text("select count(*) from temporal_association_rules")).scalar_one()
        assert counts["topic_models"] == topic_count
        assert relation_count >= 1
        assert metric_count >= 1
        assert "topic_periodicity" in counts
        assert "temporal_rules" in counts
        assert periodicity_count == counts["topic_periodicity"]
        assert rule_count == counts["temporal_rules"]
    finally:
        engine.dispose()
        shutil.rmtree(temp_root, ignore_errors=True)


def test_analysis_routes_prefer_cached_topics_trends_signals_and_batch_status(monkeypatch) -> None:
    temp_root = Path(tempfile.mkdtemp(prefix="analysis-cache-"))
    database_url = f"sqlite:///{temp_root / 'analysis-cache.sqlite3'}"
    engine = create_engine(database_url, future=True)
    try:
        Base.metadata.create_all(bind=engine)
        monkeypatch.setenv("DATABASE_URL", database_url)
        monkeypatch.setenv("STATE_BACKEND", "postgres")
        store = StudioStore(data_file=temp_root / "state.json")
        state = store._bootstrap_state()
        state["intel_events"] = [
            _event(
                "evt-cache",
                title="Cached OpenAI signal",
                entity_ids=["openai"],
                entity_names=["OpenAI"],
                anchor_tokens=["openai"],
                first_seen_at="2026-05-20T10:00:00+00:00",
            )
        ]
        store._write(state)
        now = datetime(2026, 5, 30, 8, 0, tzinfo=UTC)
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    insert into topic_models (topic_id, keywords_json, label, event_count, created_at, updated_at)
                    values (:topic_id, :keywords, :label, :event_count, :created_at, :updated_at)
                    """
                ),
                {
                    "topic_id": "cached-topic",
                    "keywords": '["cached","topic"]',
                    "label": "Cached Topic",
                    "event_count": 7,
                    "created_at": now,
                    "updated_at": now,
                },
            )
            conn.execute(
                text(
                    """
                    insert into trend_signals (id, entity_id, signal_type, signal_value, confidence, detected_at)
                    values ('trend-cache', 'openai', 'hot', 9.5, 0.8, :detected_at)
                    """
                ),
                {"detected_at": now},
            )
            conn.execute(
                text(
                    """
                    insert into analysis_batch_runs
                    (id, task_name, status, started_at, finished_at, items_processed, error_message)
                    values
                    ('run-1', 'topic_modeling', 'success', :started_at, :finished_at, 7, '')
                    """
                ),
                {"started_at": now - timedelta(minutes=3), "finished_at": now},
            )

        import backend.app.main as main_module

        main_module = importlib.reload(main_module)
        main_module.store = store
        set_store(store)
        client = TestClient(main_module.app)

        topics = client.get("/api/admin/topics")
        trends = client.get("/api/admin/trends")
        signals = client.get("/api/admin/analysis/signals")
        status = client.get("/api/admin/analysis/batch-status")

        assert topics.status_code == 200
        assert topics.json()["items"][0]["topic_id"] == "cached-topic"
        assert trends.status_code == 200
        assert trends.json()["items"][0]["entity_id"] == "openai"
        assert trends.json()["items"][0]["trend"] == "hot"
        assert signals.status_code == 200
        assert signals.json()["items"][0]["latest_event_id"] == "evt-cache"
        assert status.status_code == 200
        assert status.json()["items"][0]["task_name"] == "topic_modeling"
    finally:
        engine.dispose()
        shutil.rmtree(temp_root, ignore_errors=True)


def test_analysis_batch_runner_records_success_failure_and_dependencies(monkeypatch) -> None:
    temp_root = Path(tempfile.mkdtemp(prefix="analysis-batch-"))
    database_url = f"sqlite:///{temp_root / 'analysis-batch.sqlite3'}"
    engine = create_engine(database_url, future=True)
    try:
        Base.metadata.create_all(bind=engine)
        monkeypatch.setenv("DATABASE_URL", database_url)
        monkeypatch.setenv("STATE_BACKEND", "postgres")
        store = StudioStore(data_file=temp_root / "state.json")
        state = store._bootstrap_state()
        state["intel_events"] = [
            _event(
                "evt-a",
                title="OpenAI 医疗 AI 智能体发布",
                entity_ids=["openai", "health"],
                entity_names=["OpenAI", "医疗"],
                anchor_tokens=["openai", "health"],
                first_seen_at="2026-05-20T10:00:00+00:00",
            ),
            _event(
                "evt-b",
                title="OpenAI 医疗模型进入医院测试",
                entity_ids=["openai", "health"],
                entity_names=["OpenAI", "医疗"],
                anchor_tokens=["openai", "health"],
                first_seen_at="2026-05-21T10:00:00+00:00",
            ),
        ]
        state["event_snapshots"] = [_snapshot("evt-a", day, 1 if day < 10 else 5) for day in range(17)]
        store._write(state)
        set_store(store)

        from backend.app.features.analysis import scheduler as analysis_scheduler

        counts = analysis_scheduler.run_analysis_batch_task("event_relations")

        assert counts["event_relations"] >= 1
        with engine.connect() as conn:
            topic_success = conn.execute(
                text("select count(*) from analysis_batch_runs where task_name = 'topic_modeling' and status = 'success'")
            ).scalar_one()
            relation_success = conn.execute(
                text("select count(*) from analysis_batch_runs where task_name = 'event_relations' and status = 'success'")
            ).scalar_one()
        assert topic_success == 1
        assert relation_success == 1

        try:
            analysis_scheduler.run_analysis_batch_task("missing-task")
        except ValueError:
            pass
        else:  # pragma: no cover - defensive assertion branch
            raise AssertionError("missing task should fail")

        with engine.connect() as conn:
            failed = conn.execute(
                text("select status from analysis_batch_runs where task_name = 'missing-task' order by started_at desc limit 1")
            ).scalar_one()
        assert failed == "failed"
    finally:
        engine.dispose()
        shutil.rmtree(temp_root, ignore_errors=True)
