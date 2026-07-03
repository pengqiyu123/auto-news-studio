"""LLM-related Pydantic models for Auto News Studio."""

from __future__ import annotations

from pydantic import BaseModel, Field


class LLMProviderConfig(BaseModel):
    key: str
    api_key: str = ""
    base_url: str = ""
    model_id: str = ""
    enabled: bool = False
    last_tested_at: str | None = None
    last_test_result: str | None = None


class LLMTaskConfig(BaseModel):
    task_key: str
    label: str = ""
    provider_key: str = ""
    model_id: str = ""
    fallback_provider_key: str = ""
    fallback_model_id: str = ""
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=4096, ge=64, le=32768)
    system_prompt: str = ""


class LLMProfileConfig(BaseModel):
    id: str
    label: str
    description: str = ""
    provider_key: str
    api_key: str = ""
    base_url: str = ""
    model_id: str = ""
    enabled: bool = False
    last_tested_at: str | None = None
    last_test_result: str | None = None
    source: str | None = None
    cc_app_type: str | None = None
    cc_api_format: str | None = None
    cc_is_full_url: bool | None = None
    cc_endpoint_auto_select: bool | None = None
    cc_endpoint_candidates: list[str] = Field(default_factory=list)
    cc_base_url_raw: str | None = None
    cc_usage_base_url: str | None = None
    cc_last_verified_endpoint: str | None = None
    cc_last_verified_format: str | None = None
    cc_last_verified_model: str | None = None
    cc_probe_status: str | None = None
    cc_probe_message: str | None = None


class LLMConfig(BaseModel):
    current_profile_id: str = ""
    fallback_profile_id: str | None = None
    profiles: list[LLMProfileConfig] = Field(default_factory=list)
    providers: list[LLMProviderConfig] = Field(default_factory=list)
    # date → provider → {input_tokens, output_tokens, calls}
    usage_today: dict[str, dict[str, dict[str, int]]] = Field(default_factory=dict)


class LLMConfigResponse(BaseModel):
    item: LLMConfig


class LLMProviderPayload(BaseModel):
    key: str
    api_key: str = ""
    base_url: str = ""
    model_id: str = ""
    enabled: bool = False


class LLMTaskPayload(BaseModel):
    task_key: str
    label: str = ""
    provider_key: str = ""
    model_id: str = ""
    fallback_provider_key: str = ""
    fallback_model_id: str = ""
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=4096, ge=64, le=32768)
    system_prompt: str = ""


class LLMTestResult(BaseModel):
    ok: bool
    model: str = ""
    content: str = ""
    latency_ms: float = 0.0
    error: str = ""
    probe_status: str = ""
    probe_message: str = ""
    resolved_endpoint: str = ""
    resolved_format: str = ""
    resolved_model: str = ""
    supports_generation: bool = False


class LLMUsageResponse(BaseModel):
    item: dict[str, dict[str, int]]
