"""Narration for the FoydaPay demo video: one entry per scene, voiced by edge-tts (en-US-AndrewNeural)."""
import asyncio
import json
import subprocess
from pathlib import Path

import edge_tts
import imageio_ffmpeg

VOICE = "en-US-AndrewNeural"
RATE = "+4%"
OUT = Path(__file__).parent / "build" / "audio"

SCENES = [
    ("title", "In Uzbekistan, sixty-one percent of borrowers struggle to repay on time, and card fraud has taken almost one hundred and fifty million dollars in four years. People in debt are the easiest targets for scammers. This is FoydaPay."),
    ("intro", "FoydaPay is an AI agent for borrowers. Meet Jasur, a synthetic user: six million sum of income, three loans, and a debt load of fifty-two percent."),
    ("rescue", "Jasur writes one sentence: I can't pay my loans this month. The agent calls its tools, finds the gap, and builds a plan: cut spending, earn with checked side jobs, and an optional restructuring with its real cost."),
    ("cancel", "Nothing happens without Jasur. Cancelling unused subscriptions becomes a confirmation card. The model cannot press this button. Only the user can."),
    ("jobs", "Side jobs are matched to his free time. Offers that ask for money up front are rejected automatically, and booking again waits for his confirmation."),
    ("uzbek", "People here write in Uzbek and Russian, so FoydaPay understands them and answers in their language."),
    ("collector", "Now the attacks. A fake debt collector demands a transfer to a personal card. FoydaPay flags it as a scam, and transfers to unknown cards are blocked in code, not just in the prompt."),
    ("injection", "A prompt injection tries to take control. It is refused, and nothing leaves the account."),
    ("audit", "Every tool call, decision and confirmation goes into a hash-chained audit log. This is our execution evidence."),
    ("outro", "Sixty automated tests. Twenty out of twenty live scenarios passed. FoydaPay: find the money, keep it safe."),
]


def duration(path: Path) -> float:
    out = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-i", str(path)], capture_output=True, text=True).stderr
    h, m, s = out.split("Duration: ")[1].split(",")[0].split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


async def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    meta = []
    for key, text in SCENES:
        path = OUT / f"{key}.mp3"
        await edge_tts.Communicate(text, VOICE, rate=RATE).save(str(path))
        meta.append({"key": key, "text": text, "file": str(path), "duration": round(duration(path), 2)})
        print(f"{key}: {meta[-1]['duration']} s")
    (OUT / "scenes.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    print("total voice:", round(sum(m["duration"] for m in meta), 1), "s")


if __name__ == "__main__":
    asyncio.run(main())
