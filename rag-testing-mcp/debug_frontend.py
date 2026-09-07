import asyncio
from playwright.async_api import async_playwright

async def inspect():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1280, "height": 800})
        
        page.on("console", lambda msg: print(f"[CONSOLE {msg.type}] {msg.text}"))
        
        print("Navigating to http://localhost:5173/home...")
        await page.goto("http://localhost:5173/home", wait_until="networkidle")
        
        input_loc = page.locator("input[placeholder*='Ask your UPSC']").first
        await input_loc.click()
        await input_loc.fill("What is cultural ecology?")
        
        btn = page.locator("button:has-text('Ask Mentor')").first
        await btn.click()
        print("Clicked Ask Mentor button! Waiting up to 15s...")
        
        for i in range(15):
            await page.wait_for_timeout(1000)
            messages = page.locator("div.prose")
            if await messages.count() > 0:
                text = await messages.first.inner_text()
                print(f"\n[SUCCESS at {i+1}s] Assistant message rendered:")
                print("="*60)
                print(text[:250] + "...")
                print("="*60)
                break
            else:
                user_msgs = page.locator("div:has-text('What is cultural ecology?')")
                print(f"  Sec {i+1}: user_msg_count={await user_msgs.count()}, prose_count={await messages.count()}")
                
        await browser.close()

asyncio.run(inspect())
