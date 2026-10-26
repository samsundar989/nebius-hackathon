#!/usr/bin/env python3
"""Fallback narration (review #14 order 4): speak each caption at its start time.

video/tts.py -> video/narration_tts.wav, then `bash video/mux.sh video/narration_tts.wav
video/leakproof_tts.mp4`.

Uses the speech synthesizer built into Windows (System.Speech, offline, no download), voice
Microsoft Zira. These are the legacy desktop voices and sound clearly synthetic; this track is
insurance only, for the case that no human narration exists by Tue 18:00 CDT (NOTE 0016).
"""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from pathlib import Path

import imageio_ffmpeg

VIDEO = Path(__file__).resolve().parent
VOICE = "Microsoft Zira Desktop"


def cues(srt: str) -> list[tuple[float, str]]:
    """(start seconds, text) per caption."""
    out = []
    for block in srt.strip().split("\n\n"):
        lines = block.strip().splitlines()
        m = re.match(r"(\d+):(\d+):(\d+),(\d+) -->", lines[1]) if len(lines) >= 3 else None
        if m:
            h, mi, s, ms = (int(x) for x in m.groups())
            out.append((h * 3600 + mi * 60 + s + ms / 1000, " ".join(lines[2:])))
    return out


def speak(text: str, wav: Path) -> None:
    ps = (
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        f"$s.SelectVoice('{VOICE}'); $s.Rate = 0; "
        f"$s.SetOutputToWaveFile('{wav}'); $s.Speak([Console]::In.ReadToEnd()); $s.Dispose()"
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], input=text, text=True, check=True)


def main() -> int:
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    items = cues((VIDEO / "captions.srt").read_text(encoding="utf-8"))
    out = VIDEO / "narration_tts.wav"
    with tempfile.TemporaryDirectory() as tmp:
        args, chains = [], []
        for i, (start, text) in enumerate(items):
            wav = Path(tmp) / f"c{i}.wav"
            speak(text.replace("’", "'"), wav)
            args += ["-i", str(wav)]
            chains.append(f"[{i}:a]adelay={int(start * 1000) + 300}:all=1[a{i}]")
        mix = "".join(f"[a{i}]" for i in range(len(items)))
        graph = ";".join(chains) + f";{mix}amix=inputs={len(items)}:normalize=0[out]"
        subprocess.run(
            [
                ff,
                "-y",
                "-loglevel",
                "error",
                *args,
                "-filter_complex",
                graph,
                "-map",
                "[out]",
                str(out),
            ],
            check=True,
        )
    print(f"wrote {out} ({len(items)} captions spoken)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
