import os
import time
from pathlib import Path
from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

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
    version="1.2.0",
    docs_url="/swagger",
    redoc_url="/redoc",
)

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

templates = Jinja2Templates(directory=str(TEMPLATES_DIR)) if TEMPLATES_DIR.exists() else None

def get_base_context(request: Request, current_page: str):
    return {
        "request": request,
        "current_page": current_page,
        "metrics": cache.metrics.model_dump(),
        "total_cached": len(cache.entries),
        "settings": settings.model_dump(),
    }

# ================= PAGES =================

@app.get("/", response_class=HTMLResponse)
async def page_dashboard(request: Request):
    """Page 1: Live Radar & Gateway Console Playground"""
    ctx = get_base_context(request, "dashboard")
    ctx.update({
        "entries": cache.list_entries(limit=10),
    })
    return templates.TemplateResponse(request=request, name="index.html", context=ctx)

@app.get("/cache", response_class=HTMLResponse)
async def page_cache_explorer(request: Request):
    """Page 2: Living Vector Memory & Invalidation Matrix"""
    ctx = get_base_context(request, "cache")
    ctx.update({
        "entries": cache.list_entries(limit=100),
    })
    return templates.TemplateResponse(request=request, name="cache.html", context=ctx)

@app.get("/analytics", response_class=HTMLResponse)
async def page_analytics(request: Request):
    """Page 3: Drift & Cost Avoidance Analytics Hub"""
    ctx = get_base_context(request, "analytics")
    return templates.TemplateResponse(request=request, name="analytics.html", context=ctx)

@app.get("/settings", response_class=HTMLResponse)
async def page_settings(request: Request):
    """Page 4: Bifrost Gateway & Tavily Configuration Engine"""
    ctx = get_base_context(request, "settings")
    return templates.TemplateResponse(request=request, name="settings.html", context=ctx)

@app.get("/docs", response_class=HTMLResponse)
async def page_docs(request: Request):
    """Page 5: Interactive API Reference & SDK Guides"""
    ctx = get_base_context(request, "docs")
    return templates.TemplateResponse(request=request, name="docs.html", context=ctx)

# ================= API ENDPOINTS =================

@app.post("/v1/chat/completions")
async def chat_completions(req: ChatCompletionRequest, response: Response):
    resp_obj, headers = await proxy_engine.handle_chat_completion(req)
    for k, v in headers.items():
        response.headers[k] = v
    return resp_obj

@app.get("/api/metrics")
async def get_metrics():
    return {
        "metrics": cache.metrics.model_dump(),
        "total_cached_entries": len(cache.entries),
        "similarity_threshold": settings.SIMILARITY_THRESHOLD,
        "freshness_threshold": settings.FRESHNESS_THRESHOLD,
    }

@app.get("/api/cache/entries")
async def get_cache_entries(limit: int = 50):
    return cache.list_entries(limit=limit)

@app.post("/api/cache/probe/{entry_id}")
async def force_probe_entry(entry_id: str):
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
    if entry_id in cache.entries:
        cache.evict(entry_id)
        return {"status": "evicted", "id": entry_id}
    return JSONResponse(status_code=404, content={"error": "Entry not found"})

class SettingsUpdate(BaseModel):
    similarity_threshold: float
    freshness_threshold: float
    upstream_base_url: str

@app.post("/api/settings")
async def update_settings(payload: SettingsUpdate):
    settings.SIMILARITY_THRESHOLD = payload.similarity_threshold
    settings.FRESHNESS_THRESHOLD = payload.freshness_threshold
    settings.UPSTREAM_BASE_URL = payload.upstream_base_url
    return {"status": "updated", "settings": settings.model_dump()}
