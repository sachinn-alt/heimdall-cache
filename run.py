import uvicorn
from heimdall.config import settings

def main():
    print("=" * 65)
    print("🌈 Starting HeimdallCache Gateway for Bifrost & Tavily...")
    print(f"👉 Living Semantic Cache Active on http://localhost:{settings.PORT}")
    print(f"👉 Dashboard: http://localhost:{settings.PORT}/")
    print(f"👉 OpenAI/Bifrost Proxy: http://localhost:{settings.PORT}/v1/chat/completions")
    print(f"👉 Tavily Freshness Invalidation: ENABLED (Threshold: {settings.FRESHNESS_THRESHOLD}%)")
    print("=" * 65)
    uvicorn.run("heimdall.app:app", host=settings.HOST, port=settings.PORT, reload=True)

if __name__ == "__main__":
    main()
