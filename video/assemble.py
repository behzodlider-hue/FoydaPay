"""Mix the recorded screen video with the narration and burned-in subtitles -> FoydaPay_demo.mp4."""
import json
import re
import subprocess
from pathlib import Path

import imageio_ffmpeg

HERE = Path(__file__).parent
BUILD = HERE / "build"
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
OUT = HERE / "FoydaPay_demo.mp4"


def ts(sec: float) -> str:
    ms = int(round(sec * 1000))
    return f"{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02},{ms % 1000:03}"


def main() -> None:
    scenes = {s["key"]: s for s in json.loads((BUILD / "audio" / "scenes.json").read_text(encoding="utf-8"))}
    timeline = json.loads((BUILD / "timeline.json").read_text(encoding="utf-8"))

    # Subtitles: split each narration into sentences, timed by their share of characters.
    srt, n = [], 1
    for item in timeline["scenes"]:
        sc = scenes[item["key"]]
        parts = [p for p in re.split(r"(?<=[.:!?])\s+", sc["text"]) if p]
        total = sum(len(p) for p in parts)
        t = item["start"]
        for p in parts:
            d = sc["duration"] * len(p) / total
            srt.append(f"{n}\n{ts(t)} --> {ts(t + d)}\n{p}\n")
            n += 1
            t += d
    (BUILD / "subs.srt").write_text("\n".join(srt), encoding="utf-8")

    # Audio: each clip delayed to its scene start, then mixed.
    cmd = [FFMPEG, "-y", "-v", "error", "-i", str(BUILD / "raw.webm")]
    filters, labels = [], []
    for i, item in enumerate(timeline["scenes"], start=1):
        cmd += ["-i", scenes[item["key"]]["file"]]
        ms = int(item["start"] * 1000)
        filters.append(f"[{i}:a]adelay={ms}|{ms}[a{i}]")
        labels.append(f"[a{i}]")
    filters.append(f"{''.join(labels)}amix=inputs={len(labels)}:normalize=0[aout]")
    style = "FontName=Segoe UI,FontSize=13,PrimaryColour=&H00FFFFFF,BackColour=&H99000000,BorderStyle=3,Outline=1,Shadow=0,MarginV=18"
    filters.append(f"[0:v]subtitles=subs.srt:force_style='{style}'[vout]")
    cmd += ["-filter_complex", ";".join(filters), "-map", "[vout]", "-map", "[aout]",
            "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(OUT)]
    subprocess.run(cmd, check=True, cwd=BUILD)  # cwd so the subtitles path needs no escaping
    print("wrote", OUT, f"{OUT.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
