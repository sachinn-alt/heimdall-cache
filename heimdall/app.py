import os
from pathlib import Path
from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .models import ChatCompletionRequest
from .proxy import proxy_engine
from .living_cache import cache
from .config import settings

BASE_DIR = Path(__file__).resolve().parent.parent
DASHBOARD_DIR = BASE_DIR / "dashboard"
TEMPLATES_DIR = DASHBOARD_DIR / "templates"
STATIC_DIR = DASHBOARD_DIR / "static"

app = FastAPI(
    title="HeimdallCache Gateway",
    description="The All-Seeing Living Semantic Cache for Bifrost Gateway, Powered by Tavily",
    version="1.0.0",
)

# Mount static files and templates if they exist
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

templates = Jinja2Templates(directory=str(TEMPLATES_DIR)) if TEMPLATES_DIR.exists() else None

@app.get("/", response_class=HTMLResponse)
async def serve_dashboard(request: Request):
    """
    Renders the HeimdallCache Live Operator Dashboard.
    """
    if templates and (TEMPLATES_DIR / "index.html").exists():
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "metrics": cache.metrics.model_dump(),
                "entries": cache.list_entries(),
                "threshold": settings.SIMILARITY_THRESHOLD,
            },
        )
    return HTMLResponse("<h1>HeimdallCache Gateway is running!</h1>")

@app.post("/v1/chat/completions")
async def chat_completions(req: ChatCompletionRequest, response: Response):
    """
    OpenAI & Bifrost drop-in proxy completion endpoint with Living Semantic Caching.
    """
    resp_obj, headers = await proxy_engine.handle_chat_completion(req)
    for k, v in headers.items():
        response.headers[k] = v
    return resp_obj

@app.get("/api/metrics")
async def get_metrics():
    """
    Returns live operational metrics: cache hits, invalidations, token savings.
    """
    return {
        "metrics": cache.metrics.model_dump(),
        "total_cached_entries": len(cache.entries),
        "similarity_threshold": settings.SIMILARITY_THRESHOLD,
        "freshness_threshold": settings.FRESHNESS_THRESHOLD,
    }

@app.get("/api/cache/entries")
async def get_cache_entries(limit: int = 50):
    """
    Lists cached vectors, volatility levels, and live Tavily verification status.
    """
    return cache.list_entries(limit=limit)

@app.post("/api/cache/probe/{entry_id}")
async def force_probe_entry(entry_id: str):
    """
    Manually forces a Tavily Delta-Probe on a specific cached entry.
    """
    if entry_id not in cache.entries:
        return JSONResponse(status_code=404, content={"error": "Entry not found"})
    entry = cache.entries[entry_id]
    from .tavily_probe import tavily_prober
    verified_claims, freshness = tavily_prober.probe_claims_batch(entry.claims)
    entry.claims = verified_claims
    entry.overall_freshness = freshness
    if freshness < settings.FRESHNESS_THRESHOLD:
        entry.status = "DRIFT_DETECTED"
        cache.metrics.stale_invalidations += 1
    return {
        "id": entry_id,
        "freshness": freshness,
        "status": entry.status,
        "claims": [c.model_dump() for c in verified_claims],
    }

@app.delete("/api/cache/entries/{entry_id}")
async def evict_entry(entry_id: str):
    """
    Evicts an entry from the cache.
    """
    if entry_id in cache.entries:
        cache.evict(entry_id)
        return {"status": "evicted", "id": entry_id}
    return JSONResponse(status_code=404, content={"error": "Entry not found"})
