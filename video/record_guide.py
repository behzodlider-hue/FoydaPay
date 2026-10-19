"""Record the first-visit video guide for the mobile app (no audio, captions on screen).

Usage: python record_guide.py [site]   (default http://localhost:8000, e.g. a local uvicorn)
Writes backend/app/static/guide.mp4. All numbers typed are made up.
"""
import shutil
import subprocess
import sys
import time
from pathlib import Path

import imageio_ffmpeg
from playwright.sync_api import sync_playwright

SITE = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000").rstrip("/")
HERE = Path(__file__).parent
RAW = HERE / "build" / "guide_raw"
OUT = HERE.parent / "backend" / "app" / "static" / "guide.mp4"
W, H = 390, 844

CAPTION_JS = """t => {
  let c = document.getElementById('rec-cap');
  if (!c) { c = document.createElement('div'); c.id = 'rec-cap';
    c.style.cssText = 'position:fixed;left:12px;right:12px;top:10px;z-index:99;pointer-events:none;background:rgba(10,18,16,.92);color:#fff;' +
      'font:600 17px/1.35 Segoe UI,Arial,sans-serif;padding:12px 14px;border-radius:14px;text-align:center;box-shadow:0 6px 20px rgba(0,0,0,.3)';
    document.body.append(c); }
  c.textContent = t; c.style.display = t ? 'block' : 'none';
}"""


def main() -> None:
    shutil.rmtree(RAW, ignore_errors=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        ctx = browser.new_context(viewport={"width": W, "height": H}, device_scale_factor=2, color_scheme="light",
                                  record_video_dir=str(RAW), record_video_size={"width": W * 2, "height": H * 2})
        ctx.add_init_script("localStorage.setItem('fp_seen_guide','1')")
        ctx.add_init_script("document.addEventListener('DOMContentLoaded',()=>{const s=document.createElement('style');"
                            "s.textContent='#modeBadge{visibility:hidden}';document.head.append(s)})")
        page = ctx.new_page()
        cap = lambda t: page.evaluate(CAPTION_JS, t)
        hold = lambda s: time.sleep(s)

        def typ(locator, text):
            locator.click()
            locator.press_sequentially(text, delay=60)

        page.goto(SITE + "/app")
        page.get_by_role("button", name="Start my check").first.wait_for()
        cap("FoydaPay helps you find the money for your next loan payment")
        hold(3)

        # 1. income
        cap("Step 1 · Your income. Rough numbers are fine")
        page.get_by_role("button", name="Start my check").first.click()
        typ(page.get_by_placeholder("Your name"), "Aziza")
        typ(page.locator("#stepBody input").nth(1), "3500000")
        hold(1)
        page.get_by_role("button", name="Next").click()

        # 2. loans
        cap("Step 2 · Your loans: how much is left and the payment day")
        page.get_by_role("button", name="Microloan").first.click()
        typ(page.get_by_placeholder("e.g. Bank A"), "MFO X")
        inputs = page.locator("#stepBody input")
        typ(inputs.nth(1), "6000000")
        inputs.nth(4).fill("")
        typ(inputs.nth(4), "5")
        hold(1.5)
        page.get_by_role("button", name="Next").click()

        # 3. spending
        cap("Step 3 · Monthly spending and subscriptions, including 'Other'")
        inputs = page.locator("#stepBody input")
        for i, v in enumerate(["1000000", "300000", "900000", "250000", "450000", "200000", "300000"]):
            typ(inputs.nth(i), v)
        page.get_by_role("button", name="Music").click()
        page.get_by_role("button", name="Gym").click()
        page.get_by_role("button", name="Gym · in use").click()
        page.mouse.wheel(0, 500)
        hold(2)
        page.get_by_role("button", name="Next").click()

        # 4. side jobs
        cap("Step 4 · When you can work and what you can do")
        page.get_by_role("button", name="Every other day").click()
        page.get_by_role("button", name="Online (remote)").click()
        page.get_by_role("button", name="Smartphone apps").click()
        page.mouse.wheel(0, 400)
        typ(page.get_by_placeholder("e.g. I repair phones"), "I can teach English")
        hold(1.5)
        page.get_by_role("button", name="Next").click()
        hold(1.5)

        # 5. plan
        cap("Your plan: exact amounts to cut, earn or negotiate")
        page.get_by_role("button", name="Get my plan").click()
        page.get_by_text("1 · Cut").wait_for()
        hold(2.5)
        page.mouse.wheel(0, 380)
        hold(2)
        cap("Nothing happens until you press Confirm")
        page.get_by_role("button", name="Cancel unused subscriptions").click()
        page.get_by_role("button", name="Confirm").wait_for()
        hold(2.5)
        page.get_by_role("button", name="Confirm").click()
        hold(2)
        page.mouse.wheel(0, 600)
        hold(2)

        # 6. home + calendar
        cap("Home: your loans, what is coming up and your security status")
        page.get_by_role("button", name="Home", exact=True).click()
        hold(3)
        page.mouse.wheel(0, 350)
        hold(2)
        cap("Calendar: payment days, payday and side-job shifts, plus your own reminders")
        page.get_by_role("button", name="Calendar", exact=True).click()
        hold(3)
        page.get_by_role("button", name="Timeline").click()
        hold(3)

        # 7. security
        page.get_by_role("button", name="Back to Home").click()
        page.mouse.wheel(0, 900)
        cap("Security: is someone trying to trick you? Check any message")
        page.get_by_role("button", name="Security", exact=False).first.click()
        page.mouse.wheel(0, 500)
        page.get_by_role("button", name="Fake collector").click()
        page.get_by_role("button", name="Check message").click()
        page.get_by_text("This looks like an attack").wait_for()
        page.get_by_text("This looks like an attack").scroll_into_view_if_needed()
        hold(3.5)

        # 8. chat
        cap("Chat: ask the AI agent in Uzbek, Russian or English")
        page.get_by_role("button", name="Chat", exact=True).click()
        hold(2)
        typ(page.get_by_placeholder("Message FoydaPay…"), "Qarzimni qanday tezroq yopaman?")
        hold(2.5)
        cap("Ready? Start your check")
        page.get_by_role("button", name="Home", exact=True).click()
        hold(2.5)

        video = page.video.path()
        ctx.close()
        browser.close()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-i", video, "-vf", "scale=600:-2,fps=24",
                    "-c:v", "libx264", "-preset", "slow", "-crf", "30", "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-an", str(OUT)],
                   check=True, capture_output=True)
    print(f"wrote {OUT} ({OUT.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
