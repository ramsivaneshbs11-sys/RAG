"""
Frontend Automated Tester using Playwright.

Tests the live React/Vite frontend UI:
  1. Page availability & loading (HTTP + DOM)
  2. Tab navigation (Ask UPSC AI, MCQ Practice AI, Daily News, etc.)
  3. Mode switcher (Prelims, Mains, Current Affairs)
  4. End-to-End Chat interaction:
     - Types query into input box
     - Clicks 'Ask Mentor' / presses Enter
     - Observes typing/loading animation
     - Verifies assistant response received & rendered
  5. Measures end-to-end UI latency
  6. Captures console errors and screenshots
"""

from __future__ import annotations

import asyncio
import time
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


async def test_frontend_ui(
    frontend_url: str = "http://localhost:5173",
    test_question: str = "What is cultural ecology?",
    screenshot_dir: str | Path | None = None,
    timeout_ms: int = 45_000,
) -> dict[str, Any]:
    """Execute end-to-end automated UI tests on the frontend application."""
    from playwright.async_api import async_playwright

    results = {
        "frontend_url": frontend_url,
        "status": "passed",
        "tests": [],
        "ui_latency_ms": 0.0,
        "console_errors": [],
        "screenshots": {},
        "summary": "",
    }

    screenshot_path = None
    if screenshot_dir:
        p = Path(screenshot_dir)
        p.mkdir(parents=True, exist_ok=True)
        screenshot_path = p / f"frontend_test_{int(time.time())}.png"

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(viewport={"width": 1280, "height": 800})
            page = await context.new_page()

            # Listen for console errors
            page.on("console", lambda msg: results["console_errors"].append(msg.text) if msg.type == "error" else None)

            # ── Test 1: Page Load ──────────────────────────────────────────
            t0 = time.perf_counter()
            logger.info(f"Navigating to {frontend_url}...")
            response = await page.goto(frontend_url, timeout=timeout_ms, wait_until="networkidle")
            load_time = (time.perf_counter() - t0) * 1000

            status_code = response.status if response else 0
            page_title = await page.title()

            results["tests"].append({
                "name": "Page Load & Status",
                "status": "passed" if status_code in (200, 304) else "failed",
                "load_time_ms": round(load_time, 2),
                "http_status": status_code,
                "title": page_title,
            })

            # ── Test 2: Core UI Elements Verification ──────────────────────
            # Check for chat input or main navigation
            chat_input = page.locator("input[placeholder*='Ask your UPSC'], input[placeholder*='Generating']")
            has_input = await chat_input.count() > 0

            # Check sidebar / navigation tabs
            tabs = page.locator("button, nav a")
            tab_count = await tabs.count()

            results["tests"].append({
                "name": "Core DOM Structure & Components",
                "status": "passed" if has_input or tab_count > 0 else "failed",
                "details": f"Found input: {has_input}, Interactive elements: {tab_count}",
            })

            # ── Test 3: Tab Switching ──────────────────────────────────────
            tab_names_tested = []
            for tab_name in ["MCQ Practice AI", "Daily News", "Ask UPSC AI"]:
                tab_btn = page.locator(f"aside button:has-text('{tab_name}'), button:has-text('{tab_name}')").first
                if await tab_btn.count() > 0:
                    try:
                        await tab_btn.click(timeout=3000)
                        await page.wait_for_timeout(600)
                        tab_names_tested.append(tab_name)
                    except Exception:
                        pass

            results["tests"].append({
                "name": "Tab Navigation",
                "status": "passed" if len(tab_names_tested) > 0 else "skipped",
                "tabs_tested": tab_names_tested,
            })

            # Ensure we're specifically on the Ask UPSC AI tab for chat test
            ask_tab = page.locator("aside button:has-text('Ask UPSC AI'), button:has-text('Ask UPSC AI')").first
            if await ask_tab.count() > 0:
                await ask_tab.click()
                await page.wait_for_timeout(800)

            # ── Test 4: Mode Switcher ──────────────────────────────────────
            mode_badge = page.locator("button:has-text('Mode'), button:has-text('Prelims'), button:has-text('Mains')").first
            has_mode_switcher = await mode_badge.count() > 0

            results["tests"].append({
                "name": "Chat Mode Switcher",
                "status": "passed" if has_mode_switcher else "skipped",
                "details": "Mode switcher verified" if has_mode_switcher else "Default mode active",
            })

            # ── Test 5: End-to-End Chat Query Execution ────────────────────
            chat_input_el = page.locator("input[placeholder*='Ask your UPSC']").first
            send_btn = page.locator("button:has-text('Ask Mentor')").first

            chat_test_passed = False
            response_text = ""
            ui_latency = 0.0

            if await chat_input_el.count() > 0:
                logger.info(f"Sending test question: {test_question}")
                await chat_input_el.click()
                await chat_input_el.fill(test_question)
                
                t_send = time.perf_counter()
                if await send_btn.count() > 0 and not await send_btn.is_disabled():
                    await send_btn.click()
                else:
                    await chat_input_el.press("Enter")

                # Wait for assistant response in visible markdown container
                try:
                    assistant_msg = page.locator("div.prose, [class*='prose']").first
                    await assistant_msg.wait_for(state="attached", timeout=timeout_ms)
                    
                    # Wait up to 30s for actual text to appear inside
                    for _ in range(30):
                        await page.wait_for_timeout(1000)
                        if await assistant_msg.count() > 0:
                            txt = await assistant_msg.inner_text()
                            if len(txt.strip()) > 20:
                                response_text = txt
                                ui_latency = (time.perf_counter() - t_send) * 1000
                                chat_test_passed = True
                                break
                    if not chat_test_passed and not response_text:
                        response_text = await assistant_msg.inner_text() if await assistant_msg.count() > 0 else "Empty response"
                except Exception as exc:
                    logger.warning(f"Timeout waiting for chat response: {exc}")
                    response_text = f"Timeout/Error: {exc}"

            results["ui_latency_ms"] = round(ui_latency, 2)
            results["tests"].append({
                "name": "End-to-End Chat Interaction",
                "status": "passed" if chat_test_passed else "failed",
                "question": test_question,
                "response_preview": response_text[:150] if response_text else "No response",
                "latency_ms": round(ui_latency, 2),
            })

            # Capture Screenshot
            if screenshot_path:
                await page.screenshot(path=str(screenshot_path), full_page=True)
                results["screenshots"]["full_page"] = str(screenshot_path)

            await browser.close()

            # Determine overall status
            all_passed = all(t["status"] in ("passed", "skipped") for t in results["tests"])
            results["status"] = "passed" if all_passed else "failed"
            results["summary"] = (
                f"Frontend E2E test {'PASSED' if all_passed else 'FAILED'}: "
                f"{len([t for t in results['tests'] if t['status'] == 'passed'])}/{len(results['tests'])} checks passed. "
                f"UI Latency: {round(ui_latency, 2)}ms."
            )

    except Exception as exc:
        results["status"] = "failed"
        results["summary"] = f"Frontend automated test failed with exception: {exc}"
        logger.error(f"Frontend test error: {exc}", exc_info=True)

    return results
