#!/usr/bin/env bash
# Mix a narration onto the silent cut: video/mux.sh narration.wav -> video/leakproof_final.mp4
#
# The voice is loudness-normalised (EBU R128, -16 LUFS, the usual target for online video).
# The output is as long as the longer of the two; if the narration runs past the video, the last
# frame (the end card) is held. Fails when the result would be over 2:59 (the 3-minute limit).
# Uses $FFMPEG, or ffmpeg on PATH, or the one bundled with imageio-ffmpeg in the project venv.
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
voice="${1:?usage: video/mux.sh narration.wav}"
video="$here/leakproof_draft.mp4"
out="$here/leakproof_final.mp4"
[ -f "$voice" ] || { echo "no such file: $voice" >&2; exit 1; }
[ -f "$video" ] || { echo "no silent cut at $video: run video/record.py first" >&2; exit 1; }

ff="${FFMPEG:-$(command -v ffmpeg || true)}"
if [ -z "$ff" ]; then
  ff="$(cd "$here/.." && uv run python -c 'import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())')"
fi

duration() {  # seconds, from ffmpeg's "Duration: HH:MM:SS.xx" line (ffmpeg -i alone exits 1)
  { "$ff" -i "$1" 2>&1 || true; } | sed -n 's/.*Duration: \([0-9]*\):\([0-9]*\):\([0-9.]*\).*/\1 \2 \3/p' \
    | awk '{ printf "%.2f", $1 * 3600 + $2 * 60 + $3 }'
}
vd="$(duration "$video")"
ad="$(duration "$voice")"
total="$(awk -v a="$vd" -v b="$ad" 'BEGIN { print (a > b ? a : b) }')"
echo "video ${vd}s, narration ${ad}s -> ${total}s"
if awk -v t="$total" 'BEGIN { exit !(t > 179) }'; then
  echo "too long: ${total}s is over 2:59; trim the narration (or a scene in video/record.py)" >&2
  exit 1
fi
hold="$(awk -v a="$vd" -v b="$ad" 'BEGIN { d = b - a; print (d > 0 ? d : 0) }')"

"$ff" -y -loglevel error -i "$video" -i "$voice" \
  -filter_complex "[0:v]tpad=stop_mode=clone:stop_duration=${hold}[v];[1:a]loudnorm=I=-16:TP=-1.5:LRA=11,apad[a]" \
  -map "[v]" -map "[a]" -t "$total" \
  -c:v libx264 -preset medium -crf 20 -pix_fmt yuv420p -c:a aac -b:a 160k "$out"
echo "wrote $out ($(duration "$out")s)"
