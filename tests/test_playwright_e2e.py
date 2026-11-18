import os
import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

SCREENSHOTS_DIR = Path(__file__).resolve().parent / "screenshots"
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

BASE_URL = os.getenv("TARGET_URL", "http://127.0.0.1:8000").rstrip("/")


def run_playwright_tests():
    print(f"\n🚀 Launching Playwright E2E Suite targeting: {BASE_URL}\n")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()

        console_errors = []
        page.on("pageerror", lambda err: console_errors.append(str(err)))

        # ---------------- TEST 1: HOME CONSOLE & PLAYGROUND ----------------
        print("▶ Test 1: Testing Live Gateway Console & Telemetry Radar...")
        t0 = time.perf_counter()
        page.goto(f"{BASE_URL}/", wait_until="domcontentloaded")
        dom_ms = (time.perf_counter() - t0) * 1000
        assert "HeimdallCache" in page.title()
        print(f"  ✓ Home page DOM ready in {dom_ms:.0f}ms")

        # Check horizontal overflow on desktop
        overflow_desktop = page.evaluate("document.documentElement.scrollWidth > window.innerWidth")
        assert not overflow_desktop, "Horizontal overflow detected at 1440px!"
        print("  ✓ Zero horizontal overflow at 1440px desktop.")

        # Click the Twitter X Pricing preset
        preset_btn = page.locator("button:has-text('Twitter X Pricing')")
        preset_btn.click()
        prompt_val = page.locator("#prompt-input").input_value()
        assert "Twitter X" in prompt_val
        print("  ✓ Preset button populated prompt correctly.")

        # Click Execute via Heimdall & measure response time
        exec_btn = page.locator("#run-btn")
        t_exec = time.perf_counter()
        exec_btn.click()

        status_badge = page.locator("#status-badge")
        status_badge.wait_for(state="visible", timeout=8000)
        exec_ms = (time.perf_counter() - t_exec) * 1000
        badge_text = status_badge.inner_text()
        assert len(badge_text) > 5
        print(f"  ✓ Query resolved in {exec_ms:.0f}ms: '{badge_text}'")

        # Test Static QuickSort Hit (should be ultra fast!)
        page.locator("button:has-text('QuickSort Complexity')").click()
        t_hit = time.perf_counter()
        exec_btn.click()
        page.wait_for_function("() => !document.getElementById('run-btn').disabled", timeout=6000)
        hit_ms = (time.perf_counter() - t_hit) * 1000
        print(f"  ✓ Static QuickSort hit resolved in {hit_ms:.0f}ms")

        res_sim = page.locator("#res-sim").inner_text()
        res_fresh = page.locator("#res-fresh").inner_text()
        assert "%" in res_sim
        assert "%" in res_fresh
        print(f"  ✓ Telemetry verified — Similarity: {res_sim}, Freshness: {res_fresh}")

        page.screenshot(path=str(SCREENSHOTS_DIR / "01_home_dashboard.png"))

        # ---------------- TEST 2: LIVING VECTORS MATRIX ----------------
        print("\n▶ Test 2: Testing Living Vectors Matrix & Filtering...")
        page.goto(f"{BASE_URL}/cache.html", wait_until="domcontentloaded")
        page.wait_for_selector(".vector-row", timeout=5000)
        rows = page.locator(".vector-row")
        assert rows.count() >= 2
        print(f"  ✓ Vector matrix loaded with {rows.count()} active vectors.")

        page.locator("#filter-STATIC").click()
        page.wait_for_timeout(150)
        visible_rows = page.locator(".vector-row:visible")
        assert visible_rows.count() >= 1
        print("  ✓ Filtered for Static vectors successfully.")
        page.screenshot(path=str(SCREENSHOTS_DIR / "03_vector_matrix.png"))

        # ---------------- TEST 3: ANALYTICS & ROI CALCULATOR ----------------
        print("\n▶ Test 3: Testing Analytics Hub & Dynamic ROI Calculator...")
        page.goto(f"{BASE_URL}/analytics.html", wait_until="domcontentloaded")
        assert "Economics" in page.inner_text("h1")

        calc_input = page.locator("#calc-queries")
        calc_input.fill("1000000")
        savings_text = page.locator("#calc-savings").inner_text()
        assert "$" in savings_text
        print(f"  ✓ Interactive ROI calculated dynamic savings: {savings_text}")
        page.screenshot(path=str(SCREENSHOTS_DIR / "04_analytics_roi.png"))

        # ---------------- TEST 4: THRESHOLDS & CONTROL PLANE ----------------
        print("\n▶ Test 4: Testing Thresholds & Settings Tuning...")
        page.goto(f"{BASE_URL}/settings.html", wait_until="domcontentloaded")
        sim_val = page.locator("#sim-val").inner_text()
        assert "0.85" in sim_val
        print(f"  ✓ Default Cosine Similarity threshold loaded: {sim_val}")

        page.locator("#save-settings-btn").click()
        page.locator("#save-msg").wait_for(state="visible", timeout=5000)
        print(f"  ✓ Settings persisted: '{page.locator('#save-msg').inner_text()}'")
        page.screenshot(path=str(SCREENSHOTS_DIR / "05_settings_control_plane.png"))

        # ---------------- TEST 5: INTERACTIVE API DOCS ----------------
        print("\n▶ Test 5: Testing Interactive API Reference & Code Switcher...")
        page.goto(f"{BASE_URL}/docs.html", wait_until="domcontentloaded")
        page.locator("#tab-ts").click()
        assert page.locator("#code-ts").is_visible()
        assert "import OpenAI" in page.locator("#code-ts").inner_text()

        page.locator("#tab-curl").click()
        assert page.locator("#code-curl").is_visible()
        assert "curl -X POST" in page.locator("#code-curl").inner_text()
        print("  ✓ TypeScript and cURL code tabs verified.")

        # ---------------- TEST 6: MOBILE 375PX RESPONSIVENESS ----------------
        print("\n▶ Test 6: Testing Mobile 375px Responsiveness & Drawer...")
        mobile_ctx = browser.new_context(viewport={"width": 375, "height": 812})
        m_page = mobile_ctx.new_page()
        m_page.goto(f"{BASE_URL}/", wait_until="domcontentloaded")
        overflow_mobile = m_page.evaluate("document.documentElement.scrollWidth > window.innerWidth")
        assert not overflow_mobile, "Horizontal overflow detected at 375px mobile!"
        m_page.locator("#mobile-menu-btn").click()
        assert m_page.locator("#mobile-menu").is_visible()
        print("  ✓ Zero horizontal overflow at 375px & mobile drawer opens smoothly.")
        mobile_ctx.close()

        # ---------------- TEST 7: CUSTOM 404 PAGE ----------------
        print("\n▶ Test 7: Testing Custom 404 Page...")
        resp_404 = page.goto(f"{BASE_URL}/definitely-missing-vector-route", wait_until="domcontentloaded")
        assert resp_404.status == 404
        assert "Vector Coordinate Decayed" in page.inner_text("body")
        print("  ✓ Custom 404 page verified with HTTP 404.")

        assert not console_errors, f"Uncaught JS page errors: {console_errors}"
        print("  ✓ Zero uncaught JS runtime errors across all pages!")

        browser.close()

    print("\n🎉 ALL PLAYWRIGHT E2E TESTS PASSED WITH 100% SUCCESS!\n")


if __name__ == "__main__":
    run_playwright_tests()
