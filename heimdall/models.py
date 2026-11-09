import time
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

class Claim(BaseModel):
    id: str
    claim_text: str
    entity_type: str = "GENERAL"  # PRICING, API_VERSION, LEADERSHIP, POLICY, FACT
    volatility_level: str = "MODERATE"  # STATIC, MODERATE, HIGH
    freshness_score: float = 100.0  # 0 to 100%
    is_stale: bool = False
    verification_summary: Optional[str] = None
    sources: List[str] = Field(default_factory=list)

class CacheEntry(BaseModel):
    id: str
    prompt: str
    response_text: str
    embedding: List[float] = Field(default_factory=list)
    created_at: float = Field(default_factory=time.time)
    last_verified_at: float = Field(default_factory=time.time)
    hit_count: int = 0
    claims: List[Claim] = Field(default_factory=list)
    max_volatility: str = "MODERATE"
    overall_freshness: float = 100.0
    status: str = "HEALTHY"  # HEALTHY, DRIFT_DETECTED, EVICTED

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatCompletionRequest(BaseModel):
    model: str = "gpt-4o-mini"
    messages: List[ChatMessage]
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = 1024
    stream: Optional[bool] = False

class ChatChoice(BaseModel):
    index: int = 0
    message: ChatMessage
    finish_reason: str = "stop"

class UsageInfo(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int = Field(default_factory=lambda: int(time.time()))
    model: str
    choices: List[ChatChoice]
    usage: UsageInfo = Field(default_factory=UsageInfo)
    heimdall_meta: Optional[Dict[str, Any]] = None

class ProxyMetrics(BaseModel):
    total_requests: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    stale_invalidations: int = 0
    tokens_saved: int = 0
    avg_cache_latency_ms: float = 0.0
    avg_upstream_latency_ms: float = 0.0
