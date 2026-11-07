import os
import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

SCREENSHOTS_DIR = Path(__file__).resolve().parent / "screenshots"
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

BASE_URL = os.getenv("TARGET_URL", "https://sachinn-alt.github.io/heimdall-cache")

def run_playwright_tests():
    print(f"\n🚀 Launching Playwright E2E Suite targeting: {BASE_URL}\n")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()

        # ---------------- TEST 1: HOME CONSOLE & PLAYGROUND ----------------
        print("▶ Test 1: Testing Live Gateway Console & Telemetry Radar...")
        page.goto(f"{BASE_URL}/", wait_until="networkidle")
        assert "HeimdallCache" in page.title()

        page.screenshot(path=str(SCREENSHOTS_DIR / "01_home_dashboard.png"), full_page=True)
        print("  ✓ Page loaded & hero screenshot captured.")

        # Click the Twitter X Pricing Stale Test preset
        preset_btn = page.locator("button:has-text('Twitter X Pricing')")
        preset_btn.click()
        prompt_val = page.locator("#prompt-input").input_value()
        assert "Twitter X" in prompt_val
        print("  ✓ Preset button populated prompt correctly.")

        # Click Execute via Heimdall
        exec_btn = page.locator("#send-btn")
        exec_btn.click()

        # Wait for the status badge to appear with drift detection
        status_badge = page.locator("#status-badge")
        status_badge.wait_for(state="visible", timeout=10000)
        badge_text = status_badge.inner_text()
        assert "STALE DRIFT" in badge_text
        print(f"  ✓ Drift caught successfully: '{badge_text}'")

        # Verify similarity and freshness
        res_sim = page.locator("#res-sim").inner_text()
        res_fresh = page.locator("#res-fresh").inner_text()
        assert "%" in res_sim
        assert "%" in res_fresh
        print(f"  ✓ Telemetry verified — Similarity: {res_sim}, Freshness: {res_fresh}")

        # Verify Tavily source citations
        sources = page.locator("#sources-list a")
        assert sources.count() > 0
        print(f"  ✓ Tavily live citations verified: {sources.count()} sources rendered.")

        page.screenshot(path=str(SCREENSHOTS_DIR / "02_drift_invalidation_radar.png"))
        print("  ✓ Post-execution radar screenshot captured.")

        # ---------------- TEST 2: LIVING VECTORS MATRIX ----------------
        print("\n▶ Test 2: Testing Living Vectors Matrix & Filtering...")
        page.goto(f"{BASE_URL}/cache.html", wait_until="networkidle")
        rows = page.locator(".vector-row")
        assert rows.count() >= 3
        print(f"  ✓ Vector matrix loaded with {rows.count()} active vectors.")

        # Test filter for Static vectors
        static_btn = page.locator("button:has-text('Static (Math/Theory)')")
        static_btn.click()
        page.wait_for_timeout(300)
        visible_rows = page.locator(".vector-row:visible")
        assert visible_rows.count() >= 1
        print("  ✓ Filtered for Static vectors successfully.")

        page.screenshot(path=str(SCREENSHOTS_DIR / "03_vector_matrix.png"), full_page=True)

        # ---------------- TEST 3: ANALYTICS & ROI CALCULATOR ----------------
        print("\n▶ Test 3: Testing Analytics Hub & Dynamic ROI Calculator...")
        page.goto(f"{BASE_URL}/analytics.html", wait_until="networkidle")
        assert "Economics" in page.inner_text("h1")

        # Change ROI calculator queries
        calc_input = page.locator("#calc-queries")
        calc_input.fill("1000000")
        savings_text = page.locator("#calc-savings").inner_text()
        assert "$" in savings_text
        print(f"  ✓ Interactive ROI calculated dynamic savings: {savings_text}")

        page.screenshot(path=str(SCREENSHOTS_DIR / "04_analytics_roi.png"), full_page=True)

        # ---------------- TEST 4: THRESHOLDS & CONTROL PLANE ----------------
        print("\n▶ Test 4: Testing Thresholds & Settings Tuning...")
        page.goto(f"{BASE_URL}/settings.html", wait_until="networkidle")
        sim_val = page.locator("#sim-val").inner_text()
        assert "0.85" in sim_val
        print(f"  ✓ Default Cosine Similarity threshold loaded: {sim_val}")

        # Click Save Configuration
        save_btn = page.locator("button:has-text('Save Configuration')")
        save_btn.click()
        page.locator("#save-status").wait_for(state="visible", timeout=3000)
        print("  ✓ Settings save toast triggered successfully.")

        page.screenshot(path=str(SCREENSHOTS_DIR / "05_settings_control_plane.png"), full_page=True)

        # ---------------- TEST 5: INTERACTIVE API DOCS ----------------
        print("\n▶ Test 5: Testing Interactive API Reference & Code Switcher...")
        page.goto(f"{BASE_URL}/docs.html", wait_until="networkidle")
        
        # Test tab switcher: TypeScript
        page.locator("#tab-ts").click()
        ts_code = page.locator("#code-ts")
        assert ts_code.is_visible()
        assert "import OpenAI" in ts_code.inner_text()
        print("  ✓ TypeScript code tab switched and verified.")

        # Test tab switcher: cURL
        page.locator("#tab-curl").click()
        curl_code = page.locator("#code-curl")
        assert curl_code.is_visible()
        assert "curl -X POST" in curl_code.inner_text()
        print("  ✓ cURL code tab switched and verified.")

        page.screenshot(path=str(SCREENSHOTS_DIR / "06_api_docs.png"), full_page=True)

        browser.close()

    print("\n🎉 ALL PLAYWRIGHT E2E TESTS PASSED WITH 100% SUCCESS!")
    print(f"📁 Verified Screenshots saved to: {SCREENSHOTS_DIR}\n")

if __name__ == "__main__":
    run_playwright_tests()
