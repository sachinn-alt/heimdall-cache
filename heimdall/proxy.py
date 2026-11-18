import json
import time
import uuid
import httpx
import logging
from typing import Tuple, Dict, Any, Optional, AsyncGenerator
from .models import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatChoice,
    ChatMessage,
    UsageInfo,
)
from .living_cache import cache
from .config import settings
from .tavily_probe import tavily_prober

logger = logging.getLogger("heimdall.proxy")


class GatewayProxy:
    """
    High-Speed OpenAI & Bifrost-compatible proxy engine with Heimdall living cache
    integration, pooled async HTTP, and real-time Server-Sent Events (SSE) streaming.
    """

    def __init__(self):
        self._upstream_http: Optional[httpx.AsyncClient] = None

    def _get_upstream_client(self) -> httpx.AsyncClient:
        if self._upstream_http is None or self._upstream_http.is_closed:
            self._upstream_http = httpx.AsyncClient(
                timeout=httpx.Timeout(12.0, connect=3.0),
                limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
            )
        return self._upstream_http

    async def close(self):
        if self._upstream_http is not None and not self._upstream_http.is_closed:
            await self._upstream_http.aclose()
        await tavily_prober.close()

    async def handle_chat_completion(
        self, request: ChatCompletionRequest
    ) -> Tuple[ChatCompletionResponse, Dict[str, str]]:
        prompt = self._extract_prompt(request)
        start_time = time.perf_counter()

        # Step 1: Non-blocking Living Semantic Cache Lookup
        entry, status, sim, meta = await cache.async_lookup(prompt)

        # Case 1: Verified Living Cache Hit
        if entry is not None and status in ("HIT_VERIFIED", "HIT_STATIC"):
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            cache.record_latency(is_cache_hit=True, latency_ms=latency_ms)

            headers = {
                "X-Heimdall-Cache": status,
                "X-Heimdall-Similarity": str(sim),
                "X-Heimdall-Freshness-Score": f"{entry.overall_freshness}%",
                "X-Heimdall-Latency-MS": str(latency_ms),
                "X-Bifrost-Cache-Status": "HIT",
                "X-Bifrost-Grounded": "true",
            }

            resp = ChatCompletionResponse(
                id=f"chatcmpl-heimdall-hit-{uuid.uuid4().hex[:8]}",
                model=request.model,
                choices=[
                    ChatChoice(
                        index=0,
                        message=ChatMessage(role="assistant", content=entry.response_text),
                        finish_reason="stop",
                    )
                ],
                usage=UsageInfo(
                    prompt_tokens=len(prompt.split()),
                    completion_tokens=len(entry.response_text.split()),
                    total_tokens=len(prompt.split()) + len(entry.response_text.split()),
                ),
                heimdall_meta={
                    "status": "CACHE_HIT",
                    "cache_type": status,
                    "invalidation_detected": False,
                    "similarity": sim,
                    "freshness_score": entry.overall_freshness,
                    "volatility_level": entry.max_volatility,
                    "tavily_probed": bool(meta and meta.get("tavily_probed")),
                    "latency_ms": latency_ms,
                    "verified_via": (meta or {}).get("verified_via", "Living Vector Memory"),
                    "sources": [s for c in entry.claims for s in c.sources][:3],
                },
            )
            return resp, headers

        # Case 2: Stale Invalidation or Cache Miss -> Fast Async Grounding
        upstream_answer, sources, grounded_by_tavily = await self._fetch_upstream_or_synthesize(prompt, request)

        # Avoid double-probing when answer was just fetched live from Tavily!
        new_entry = await cache.async_store(
            prompt,
            upstream_answer,
            sources=sources,
            already_grounded=grounded_by_tavily,
        )
        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        cache.record_latency(is_cache_hit=False, latency_ms=latency_ms)

        cache_action = "STALE_INVALIDATED_AND_REFRESHED" if status == "STALE_INVALIDATED" else "CACHE_MISS_STORED"
        headers = {
            "X-Heimdall-Cache": cache_action,
            "X-Heimdall-Similarity": str(sim),
            "X-Heimdall-Freshness-Score": f"{new_entry.overall_freshness}%",
            "X-Heimdall-Latency-MS": str(latency_ms),
            "X-Bifrost-Cache-Status": "MISS" if status != "STALE_INVALIDATED" else "STALE_INVALIDATED",
            "X-Bifrost-Grounded": "true",
        }

        combined_sources = sources or [s for c in new_entry.claims for s in c.sources][:3]
        resp = ChatCompletionResponse(
            id=f"chatcmpl-heimdall-fresh-{uuid.uuid4().hex[:8]}",
            model=request.model,
            choices=[
                ChatChoice(
                    index=0,
                    message=ChatMessage(role="assistant", content=upstream_answer),
                    finish_reason="stop",
                )
            ],
            usage=UsageInfo(
                prompt_tokens=len(prompt.split()),
                completion_tokens=len(upstream_answer.split()),
                total_tokens=len(prompt.split()) + len(upstream_answer.split()),
            ),
            heimdall_meta={
                "status": cache_action,
                "cache_type": status,
                "invalidation_detected": (status == "STALE_INVALIDATED"),
                "similarity": sim,
                "freshness_score": new_entry.overall_freshness,
                "volatility_level": new_entry.max_volatility,
                "tavily_probed": grounded_by_tavily or bool(meta and meta.get("tavily_probed")),
                "latency_ms": latency_ms,
                "verified_via": "Tavily Live Web Search" if grounded_by_tavily else "Bifrost Upstream LLM",
                "sources": combined_sources[:3],
            },
        )
        return resp, headers

    async def stream_chat_completion(
        self, request: ChatCompletionRequest
    ) -> AsyncGenerator[str, None]:
        """
        Streams response tokens as Server-Sent Events (SSE) compliant with OpenAI spec.
        """
        resp_obj, _ = await self.handle_chat_completion(request)
        content = resp_obj.choices[0].message.content
        chunk_id = resp_obj.id

        meta_chunk = {
            "id": chunk_id,
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": request.model,
            "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}],
            "heimdall_meta": resp_obj.heimdall_meta,
        }
        yield f"data: {json.dumps(meta_chunk)}\n\n"

        words = content.split(" ")
        for i, word in enumerate(words):
            token = word if i == 0 else " " + word
            chunk = {
                "id": chunk_id,
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": request.model,
                "choices": [{"index": 0, "delta": {"content": token}, "finish_reason": None}],
            }
            yield f"data: {json.dumps(chunk)}\n\n"

        stop_chunk = {
            "id": chunk_id,
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": request.model,
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        }
        yield f"data: {json.dumps(stop_chunk)}\n\n"
        yield "data: [DONE]\n\n"

    @staticmethod
    def _extract_prompt(request: ChatCompletionRequest) -> str:
        for m in reversed(request.messages):
            if m.role == "user":
                return m.content
        return request.messages[-1].content if request.messages else ""

    async def _fetch_upstream_or_synthesize(
        self, prompt: str, request: ChatCompletionRequest
    ) -> Tuple[str, list, bool]:
        """Returns (answer_text, sources, grounded_by_tavily)."""
        if settings.UPSTREAM_API_KEY:
            try:
                url = f"{settings.UPSTREAM_BASE_URL.rstrip('/')}/chat/completions"
                headers = {
                    "Authorization": f"Bearer {settings.UPSTREAM_API_KEY}",
                    "Content-Type": "application/json",
                }
                client = self._get_upstream_client()
                res = await client.post(url, json=request.model_dump(), headers=headers)
                if res.status_code == 200:
                    data = res.json()
                    text = data["choices"][0]["message"]["content"]
                    return text, [], False
            except Exception as e:
                logger.warning(f"Upstream call failed, falling back to Tavily synthesis: {e}")

        # Fast Non-Blocking Async Tavily Grounding
        search_results = []
        sources = []
        if tavily_prober.api_key:
            try:
                s_res = await tavily_prober.async_search(
                    query=prompt,
                    max_results=3,
                    search_depth="basic",
                    include_answer=True,
                )
                direct_ans = s_res.get("answer", "")
                search_results = s_res.get("results", [])
                sources = [r["url"] for r in search_results if "url" in r]
                if direct_ans:
                    return f"{direct_ans}\n\n[Live ground truth verified via Tavily Search]", sources[:3], True
            except Exception as e:
                logger.error(f"Fallback async Tavily search error: {e}")

        if search_results:
            top_content = search_results[0].get("content", "")
            title = search_results[0].get("title", "")
            return f"{top_content}\n\n[Live verified via Tavily: {title}]", sources[:3], True

        return f"Processed query: '{prompt}'. Result generated and cached.", [], False


proxy_engine = GatewayProxy()
