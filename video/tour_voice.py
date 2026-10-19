"""Voice-over for the mobile app's guided tour: one MP3 per step and language, male voices (edge-tts).

Reads backend/app/static/tour/script.json (the same text the app shows as captions) and writes
backend/app/static/tour/<lang>/<step>.mp3.
"""
import asyncio
import json
from pathlib import Path

import edge_tts

TOUR = Path(__file__).parent.parent / "backend" / "app" / "static" / "tour"
VOICES = {"en": "en-US-AndrewNeural", "ru": "ru-RU-DmitryNeural", "uz": "uz-UZ-SardorNeural"}


async def main() -> None:
    script = json.loads((TOUR / "script.json").read_text(encoding="utf-8"))
    for lang, voice in VOICES.items():
        (TOUR / lang).mkdir(parents=True, exist_ok=True)
        for step in script["steps"]:
            out = TOUR / lang / f"{step}.mp3"
            if out.exists() and out.stat().st_size > 1000:
                continue
            for attempt in range(8):  # the TTS service sometimes drops a request
                try:
                    await edge_tts.Communicate(script[lang][step], voice, rate="+2%").save(str(out))
                    break
                except edge_tts.exceptions.NoAudioReceived:
                    await asyncio.sleep(5 + attempt * 10)
            else:
                raise SystemExit(f"no audio for {lang}/{step}")
            print(lang, step, out.stat().st_size // 1024, "KB")


if __name__ == "__main__":
    asyncio.run(main())
