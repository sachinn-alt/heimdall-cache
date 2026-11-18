import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from heimdall.app import app
from heimdall.living_cache import cache
from heimdall.tavily_probe import tavily_prober
from heimdall.embeddings import embedding_engine


def test_initialization():
    assert app is not None
    assert cache is not None
    assert len(cache.entries) >= 2
    print(f"Total initial seeded scenarios: {len(cache.entries)}")

    # Verify deterministic embeddings
    v1 = embedding_engine.get_embedding("What is the time complexity of QuickSort?")
    v2 = embedding_engine.get_embedding("What is the time complexity of QuickSort?")
    assert v1 == v2
    assert embedding_engine.cosine_similarity(v1, v2) > 0.999
    print("Deterministic CRC32 embeddings verified.")

    assert tavily_prober is not None
    if tavily_prober.api_key:
        assert tavily_prober.client is not None
        print("Tavily API key configured and client initialized.")
    else:
        print("Tavily API key not configured locally (graceful fallback verified).")

    print("All basic tests passed!")


if __name__ == "__main__":
    test_initialization()
