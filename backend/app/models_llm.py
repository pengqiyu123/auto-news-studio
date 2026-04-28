"""LLM-related Pydantic models for Auto News Studio."""

from __future__ import annotations

from typing import Any

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


class LLMConfig(BaseModel):
    current_profile_id: str = ""
    profiles: list[LLMProfileConfig] = Field(default_factory=list)
    providers: list[LLMProviderConfig] = Field(default_factory=list)
    tasks: list[LLMTaskConfig] = Field(default_factory=list)
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
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=4096, ge=64, le=32768)
    system_prompt: str = ""


class LLMTestResult(BaseModel):
    ok: bool
    model: str = ""
    content: str = ""
    latency_ms: float = 0.0
    error: str = ""


class LLMUsageResponse(BaseModel):
    item: dict[str, dict[str, int]]
