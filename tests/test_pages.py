import sys
from pathlib import Path
from starlette.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from heimdall.app import app

def test_all_pages():
    client = TestClient(app)
    
    pages = [
        ("/", "Console"),
        ("/cache", "Living Vector Memory"),
        ("/analytics", "The Economics of"),
        ("/settings", "Thresholds & Control Plane"),
        ("/docs", "OpenAI"),
    ]

    for path, expected_text in pages:
        response = client.get(path)
        assert response.status_code == 200, f"Failed on {path}: {response.status_code}"
        assert expected_text in response.text, f"Text '{expected_text}' not found in {path}"
        print(f"✓ Page {path} rendered with 200 OK")

    print("\nAll 5 application pages verified with zero errors!")

if __name__ == "__main__":
    test_all_pages()
