import asyncio
import sys
sys.path.insert(0, 'src')
from rag_testing_mcp.evaluators.frontend import test_frontend_ui

async def main():
    print("Running automated Playwright Frontend Test against http://localhost:5173...")
    res = await test_frontend_ui(
        frontend_url="http://localhost:5173/home",
        test_question="What is cultural ecology?",
        screenshot_dir="evaluation/results/screenshots",
        timeout_ms=30000
    )
    print("\n=== FRONTEND TEST RESULTS ===")
    print(f"Overall Status: {res['status']}")
    print(f"Summary: {res['summary']}")
    print("\nDetailed Tests:")
    for t in res['tests']:
        print(f"  [{t['status'].upper()}] {t['name']}")
        for k, v in t.items():
            if k not in ('name', 'status'):
                print(f"      {k}: {v}")
    if res.get('console_errors'):
        print(f"\nConsole Errors ({len(res['console_errors'])}):")
        for err in res['console_errors'][:5]:
            print(f"  - {err}")
    if res.get('screenshots'):
        print(f"\nScreenshot saved: {res['screenshots']}")

asyncio.run(main())
