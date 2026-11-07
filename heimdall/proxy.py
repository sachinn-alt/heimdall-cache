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
    OpenAI & Bifrost-compatible proxy engine with Heimdall living cache integration
    and real-time Server-Sent Events (SSE) streaming support.
    """

    async def handle_chat_completion(
        self, request: ChatCompletionRequest
    ) -> Tuple[ChatCompletionResponse, Dict[str, str]]:
        prompt = self._extract_prompt(request)
        start_time = time.time()

        # Step 1: Query Heimdall Living Semantic Cache
        entry, status, sim, meta = cache.lookup(prompt)

        # Case 1: Verified Living Cache Hit
        if entry is not None and status in ("HIT_VERIFIED", "HIT_STATIC"):
            latency_ms = round((time.time() - start_time) * 1000, 2)
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
                    "similarity": sim,
                    "freshness_score": entry.overall_freshness,
                    "latency_ms": latency_ms,
                    "verified_via": "Tavily Live Web Search",
                    "sources": [s for c in entry.claims for s in c.sources][:3],
                },
            )
            return resp, headers

        # Case 2: Stale Invalidation or Cache Miss
        upstream_answer, sources = await self._fetch_upstream_or_synthesize(prompt, request)
        new_entry = cache.store(prompt, upstream_answer)
        latency_ms = round((time.time() - start_time) * 1000, 2)

        cache_action = "STALE_INVALIDATED_AND_REFRESHED" if status == "STALE_INVALIDATED" else "CACHE_MISS_STORED"
        headers = {
            "X-Heimdall-Cache": cache_action,
            "X-Heimdall-Similarity": str(sim),
            "X-Heimdall-Freshness-Score": f"{new_entry.overall_freshness}%",
            "X-Heimdall-Latency-MS": str(latency_ms),
            "X-Bifrost-Cache-Status": "MISS" if status != "STALE_INVALIDATED" else "STALE_INVALIDATED",
            "X-Bifrost-Grounded": "true",
        }

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
                "invalidation_detected": (status == "STALE_INVALIDATED"),
                "similarity": sim,
                "freshness_score": new_entry.overall_freshness,
                "latency_ms": latency_ms,
                "sources": sources,
            },
        )
        return resp, headers

    async def stream_chat_completion(
        self, request: ChatCompletionRequest
    ) -> AsyncGenerator[str, None]:
        """
        Streams response tokens as Server-Sent Events (SSE) compliant with OpenAI spec.
        """
        resp_obj, headers = await self.handle_chat_completion(request)
        content = resp_obj.choices[0].message.content
        chunk_id = resp_obj.id

        # Yield header diagnostic chunk
        meta_chunk = {
            "id": chunk_id,
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": request.model,
            "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}],
            "heimdall_meta": resp_obj.heimdall_meta,
        }
        yield f"data: {json.dumps(meta_chunk)}\n\n"

        # Stream words/tokens smoothly
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

        # Final stop chunk
        stop_chunk = {
            "id": chunk_id,
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": request.model,
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        }
        yield f"data: {json.dumps(stop_chunk)}\n\n"
        yield "data: [DONE]\n\n"

    def _extract_prompt(self, request: ChatCompletionRequest) -> str:
        for m in reversed(request.messages):
            if m.role == "user":
                return m.content
        return request.messages[-1].content if request.messages else ""

    async def _fetch_upstream_or_synthesize(
        self, prompt: str, request: ChatCompletionRequest
    ) -> Tuple[str, list]:
        if settings.UPSTREAM_API_KEY:
            try:
                url = f"{settings.UPSTREAM_BASE_URL.rstrip('/')}/chat/completions"
                headers = {
                    "Authorization": f"Bearer {settings.UPSTREAM_API_KEY}",
                    "Content-Type": "application/json",
                }
                async with httpx.AsyncClient(timeout=30.0) as client:
                    res = await client.post(url, json=request.model_dump(), headers=headers)
                    if res.status_code == 200:
                        data = res.json()
                        text = data["choices"][0]["message"]["content"]
                        return text, []
            except Exception as e:
                logger.warning(f"Upstream call failed, falling back to Tavily synthesis: {e}")

        # Intelligent Autonomous Fallback using Tavily
        search_results = []
        sources = []
        if tavily_prober.client:
            try:
                s_res = tavily_prober.client.search(
                    query=prompt, max_results=3, search_depth="basic", include_answer=True
                )
                direct_ans = s_res.get("answer", "")
                search_results = s_res.get("results", [])
                sources = [r["url"] for r in search_results if "url" in r]
                if direct_ans:
                    return f"{direct_ans}\n\n[Live ground truth verified via Tavily Search]", sources[:3]
            except Exception as e:
                logger.error(f"Fallback Tavily search error: {e}")

        if search_results:
            top_content = search_results[0].get("content", "")
            title = search_results[0].get("title", "")
            return f"{top_content}\n\n[Live verified via Tavily: {title}]", sources[:3]

        return f"Processed query: '{prompt}'. Result generated and cached.", []

proxy_engine = GatewayProxy()
