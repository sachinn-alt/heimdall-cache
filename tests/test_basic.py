import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from heimdall.app import app
from heimdall.living_cache import cache
from heimdall.tavily_probe import tavily_prober

def test_initialization():
    assert app is not None
    assert cache is not None
    print(f"Total initial seeded scenarios: {len(cache.entries)}")
    print("Testing Tavily probe initialization...")
    assert tavily_prober.client is not None
    print("All basic tests passed!")

if __name__ == "__main__":
    test_initialization()
