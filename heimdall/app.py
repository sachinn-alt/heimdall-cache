import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from .models import ChatCompletionRequest
from .proxy import proxy_engine
from .living_cache import cache
from .config import settings
from .tavily_probe import tavily_prober
from .storage import db_storage

BASE_DIR = Path(__file__).resolve().parent.parent
DASHBOARD_DIR = BASE_DIR / "dashboard"
TEMPLATES_DIR = DASHBOARD_DIR / "templates"
STATIC_DIR = DASHBOARD_DIR / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await proxy_engine.close()


app = FastAPI(
    title="HeimdallCache Gateway",
    description="The All-Seeing Living Semantic Cache for Bifrost Gateway, Powered by Tavily",
    version="1.4.0",
    docs_url="/swagger",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# GZip compression for fast HTML/JSON transfer
app.add_middleware(GZipMiddleware, minimum_size=500)

# Enable universal CORS for seamless Vercel, GitHub Pages, and multi-cloud interconnection
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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


# ================= HEALTH CHECK =================

@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "version": "1.4.0",
        "cached_vectors": len(cache.entries),
        "tavily_configured": bool(tavily_prober.api_key),
    }


# ================= PAGES =================

@app.get("/", response_class=HTMLResponse)
@app.get("/index.html", response_class=HTMLResponse)
async def page_dashboard(request: Request):
    """Page 1: Live Radar & Gateway Console Playground"""
    ctx = get_base_context(request, "dashboard")
    ctx.update({"entries": cache.list_entries(limit=10)})
    return templates.TemplateResponse(request=request, name="index.html", context=ctx)


@app.get("/cache", response_class=HTMLResponse)
@app.get("/cache.html", response_class=HTMLResponse)
async def page_cache_explorer(request: Request):
    """Page 2: Living Vector Memory & Invalidation Matrix"""
    ctx = get_base_context(request, "cache")
    ctx.update({"entries": cache.list_entries(limit=100)})
    return templates.TemplateResponse(request=request, name="cache.html", context=ctx)


@app.get("/analytics", response_class=HTMLResponse)
@app.get("/analytics.html", response_class=HTMLResponse)
async def page_analytics(request: Request):
    """Page 3: Drift & Cost Avoidance Analytics Hub"""
    ctx = get_base_context(request, "analytics")
    return templates.TemplateResponse(request=request, name="analytics.html", context=ctx)


@app.get("/settings", response_class=HTMLResponse)
@app.get("/settings.html", response_class=HTMLResponse)
async def page_settings(request: Request):
    """Page 4: Bifrost Gateway & Tavily Configuration Engine"""
    ctx = get_base_context(request, "settings")
    return templates.TemplateResponse(request=request, name="settings.html", context=ctx)


@app.get("/docs", response_class=HTMLResponse)
@app.get("/docs.html", response_class=HTMLResponse)
async def page_docs(request: Request):
    """Page 5: Interactive API Reference & SDK Guides"""
    ctx = get_base_context(request, "docs")
    return templates.TemplateResponse(request=request, name="docs.html", context=ctx)


@app.get("/pitch", response_class=HTMLResponse)
@app.get("/pitch.html", response_class=HTMLResponse)
async def page_pitch(request: Request):
    """Page 6: Interactive Pitch Deck & Presentation Slides"""
    ctx = get_base_context(request, "pitch")
    return templates.TemplateResponse(request=request, name="pitch.html", context=ctx)


@app.get("/404", response_class=HTMLResponse)
@app.get("/404.html", response_class=HTMLResponse)
async def page_404(request: Request):
    """Custom 404 Error Page"""
    return templates.TemplateResponse(request=request, name="404.html", context={"request": request}, status_code=404)


@app.exception_handler(404)
async def not_found_exception_handler(request: Request, exc):
    if request.url.path.startswith(("/v1", "/api")):
        return JSONResponse(status_code=404, content={"detail": "Not Found", "path": request.url.path})
    return templates.TemplateResponse(request=request, name="404.html", context={"request": request}, status_code=404)


# ================= STATIC FAVICONS =================

FAVICON_CACHE_HEADERS = {"Cache-Control": "public, max-age=86400"}


@app.get("/favicon.ico", include_in_schema=False)
async def favicon_ico():
    ico_path = BASE_DIR / "favicon.ico"
    if ico_path.exists():
        return FileResponse(ico_path, media_type="image/x-icon", headers=FAVICON_CACHE_HEADERS)
    return Response(status_code=404)


@app.get("/favicon.svg", include_in_schema=False)
async def favicon_svg():
    svg_path = BASE_DIR / "favicon.svg"
    if svg_path.exists():
        return FileResponse(svg_path, media_type="image/svg+xml", headers=FAVICON_CACHE_HEADERS)
    return Response(status_code=404)


@app.get("/favicon.png", include_in_schema=False)
async def favicon_png():
    png_path = BASE_DIR / "favicon.png"
    if png_path.exists():
        return FileResponse(png_path, media_type="image/png", headers=FAVICON_CACHE_HEADERS)
    return Response(status_code=404)


@app.get("/apple-touch-icon.png", include_in_schema=False)
async def apple_touch_icon():
    touch_path = BASE_DIR / "apple-touch-icon.png"
    if touch_path.exists():
        return FileResponse(touch_path, media_type="image/png", headers=FAVICON_CACHE_HEADERS)
    return Response(status_code=404)


@app.get("/styles.css", include_in_schema=False)
async def static_styles_css():
    css_path = BASE_DIR / "styles.css"
    if css_path.exists():
        return FileResponse(css_path, media_type="text/css", headers=FAVICON_CACHE_HEADERS)
    return Response(status_code=404)


# ================= API ENDPOINTS =================

@app.post("/v1/chat/completions")
async def chat_completions(req: ChatCompletionRequest, response: Response):
    """
    OpenAI & Bifrost drop-in proxy completion endpoint with Living Semantic Caching
    and real-time token streaming (SSE) support.
    """
    if req.stream:
        return StreamingResponse(
            proxy_engine.stream_chat_completion(req),
            media_type="text/event-stream",
            headers={"X-Heimdall-Mode": "STREAMING_SSE"},
        )

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
        "tavily_configured": bool(tavily_prober.api_key),
    }


@app.get("/api/cache/entries")
async def get_cache_entries(limit: int = 50):
    return cache.list_entries(limit=limit)


@app.post("/api/cache/probe/{entry_id}")
async def force_probe_entry(entry_id: str):
    if entry_id not in cache.entries:
        return JSONResponse(status_code=404, content={"error": "Entry not found"})
    t0 = time.perf_counter()
    entry = cache.entries[entry_id]
    verified_claims, freshness = await tavily_prober.async_probe_claims_batch(entry.claims)
    entry.claims = verified_claims
    entry.overall_freshness = freshness
    entry.last_verified_at = time.time()
    if freshness < settings.FRESHNESS_THRESHOLD:
        entry.status = "DRIFT_DETECTED"
        cache.metrics.stale_invalidations += 1
    else:
        entry.status = "HEALTHY"
    db_storage.save_entry(entry)
    cache._sync_metrics()
    probe_ms = round((time.perf_counter() - t0) * 1000, 1)
    return {
        "id": entry_id,
        "freshness": freshness,
        "status": entry.status,
        "probe_latency_ms": probe_ms,
        "claims": [c.model_dump() for c in verified_claims],
    }


@app.delete("/api/cache/entries/{entry_id}")
async def evict_entry(entry_id: str):
    if entry_id in cache.entries:
        cache.evict(entry_id)
        return {"status": "evicted", "id": entry_id}
    return JSONResponse(status_code=404, content={"error": "Entry not found"})


@app.get("/api/settings")
async def get_settings():
    return {
        "similarity_threshold": settings.SIMILARITY_THRESHOLD,
        "freshness_threshold": settings.FRESHNESS_THRESHOLD,
        "upstream_base_url": settings.UPSTREAM_BASE_URL,
        "ttl_volatile_seconds": settings.TTL_VOLATILE_SECONDS,
        "ttl_moderate_seconds": settings.TTL_MODERATE_SECONDS,
        "ttl_static_seconds": settings.TTL_STATIC_SECONDS,
    }


class SettingsUpdate(BaseModel):
    similarity_threshold: float
    freshness_threshold: float
    upstream_base_url: str


@app.post("/api/settings")
async def update_settings(payload: SettingsUpdate):
    settings.SIMILARITY_THRESHOLD = max(0.5, min(0.99, payload.similarity_threshold))
    settings.FRESHNESS_THRESHOLD = max(10.0, min(99.0, payload.freshness_threshold))
    if payload.upstream_base_url.strip():
        settings.UPSTREAM_BASE_URL = payload.upstream_base_url.strip()
    return {
        "status": "updated",
        "settings": {
            "similarity_threshold": settings.SIMILARITY_THRESHOLD,
            "freshness_threshold": settings.FRESHNESS_THRESHOLD,
            "upstream_base_url": settings.UPSTREAM_BASE_URL,
        },
    }
