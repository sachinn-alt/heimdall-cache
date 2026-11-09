import sys
from pathlib import Path
from starlette.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from heimdall.app import app
from heimdall.storage import db_storage

def test_all_pages_and_features():
    client = TestClient(app)
    
    pages = [
        ("/", "Console"),
        ("/index.html", "Console"),
        ("/cache", "Living Vector Memory"),
        ("/cache.html", "Living Vector Memory"),
        ("/analytics", "The Economics of"),
        ("/analytics.html", "The Economics of"),
        ("/settings", "Thresholds & Control Plane"),
        ("/settings.html", "Thresholds & Control Plane"),
        ("/docs", "OpenAI"),
        ("/docs.html", "OpenAI"),
        ("/pitch", "INTERACTIVE PITCH DECK"),
        ("/pitch.html", "INTERACTIVE PITCH DECK"),
    ]

    for path, expected_text in pages:
        response = client.get(path)
        assert response.status_code == 200, f"Failed on {path}: {response.status_code}"
        assert expected_text in response.text, f"Text '{expected_text}' not found in {path}"
        print(f"✓ Page {path} rendered with 200 OK")

    # Test SQLite persistence
    persisted = db_storage.load_all_entries()
    assert len(persisted) > 0
    print(f"✓ SQLite persistence verified with {len(persisted)} vectors in DB.")

    # Test SSE Streaming endpoint
    stream_payload = {
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": "What is the time complexity of QuickSort in the average case?"}],
        "stream": True
    }
    with client.stream("POST", "/v1/chat/completions", json=stream_payload) as stream_resp:
        assert stream_resp.status_code == 200
        assert "text/event-stream" in stream_resp.headers.get("content-type", "")
        chunks = [chunk for chunk in stream_resp.iter_lines()]
        assert any("[DONE]" in c for c in chunks)
        print("✓ Server-Sent Events (SSE) streaming verified with [DONE] termination chunk.")

    print("\n🎉 All 6 application pages, SQLite persistence, and SSE streaming verified with zero errors!")

if __name__ == "__main__":
    test_all_pages_and_features()
