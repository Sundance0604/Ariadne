"""Resumeable 4K60 export; concatenate video first, then add one audio track.

Each 20-second part samples the same absolute timeline, so replacing a part
later does not reset particle motion or colour transitions at the join.
"""
from __future__ import annotations

import os
import shutil
import json
import subprocess
from hashlib import sha256
from math import ceil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RENDERER = ROOT.parents[1] / "prokofiev2-waterfall/gpu-vfx-flow"
PARTS = ROOT / "full-render-parts"
NODE = Path(os.environ.get("PROK3_NODE") or shutil.which("node") or "node")
FFMPEG = Path(os.environ.get("PROK3_FFMPEG") or shutil.which("ffmpeg") or "ffmpeg")
AUDIO = Path(os.environ.get("PROK3_AUDIO_PATH", str(ROOT / "inputs/audio.mp3")))
SHA = "55b26a3b8e26090f97a1248f1fab020c1096f1a42b10652520d95afbb7db00d1"
FINAL = ROOT / "prokofiev3-movement1-full-4k60.mp4"


def run(command, *, env=None):
    subprocess.run(command, cwd=RENDERER, env=env, check=True)


def main():
    PARTS.mkdir(exist_ok=True)
    timeline = json.loads((ROOT / "prokofiev3-full-render.timeline.json").read_text())
    duration = float(timeline["render_interval"]["duration_seconds"])
    intro_lead = float(timeline.get("intro", {}).get("lead_in_seconds", 0))
    # A resumed export may reuse a part only when both the scene data and the
    # renderer are exactly the same as when that part was first produced.
    signature = sha256()
    for path in (ROOT / "prokofiev3-full-render.timeline.json",
                 RENDERER / "dist/waterfall.js",
                 RENDERER / "visual-preset.json",
                 RENDERER / "visual-style.json"):
        signature.update(path.read_bytes())
    signature.update(b"3840x2160/60fps/crf16/ultrafast")
    signature_file = PARTS / "render-signature.sha256"
    current_signature = signature.hexdigest()
    if signature_file.exists() and signature_file.read_text() != current_signature:
        raise RuntimeError("Render inputs changed; archive or clear the old parts before resuming")
    signature_file.write_text(current_signature)
    env = os.environ.copy()
    env.update(WATERFALL_WIDTH="3840", WATERFALL_HEIGHT="2160",
               WATERFALL_VIDEO_ONLY="1", WATERFALL_CRF="16",
               WATERFALL_ENCODING_PRESET="ultrafast",
               WATERFALL_ENCODER_THREADS="4",
               WATERFALL_VERIFIED_AUDIO_SHA256=SHA,
               FFMPEG_BINARY=str(FFMPEG))
    outputs = []
    for start in range(0, ceil(duration), 20):
        part_duration = min(20, duration - start)
        output = PARTS / f"part-{start:03d}.mp4"
        outputs.append(output)
        if output.exists() and output.stat().st_size > 100_000:
            print(f"skip {output.name}", flush=True)
            continue
        env["WATERFALL_START"] = str(start)
        env["WATERFALL_DURATION"] = str(part_duration)
        print(f"render {start:03d}-{start+part_duration:06.1f}", flush=True)
        temp = output.with_suffix(".incomplete.mp4")
        try:
            run([str(NODE), "export.mjs", str(PARTS / f"part-{start:03d}.json"),
                 str(AUDIO), str(temp), "60"], env=env)
            temp.replace(output)
        finally:
            temp.unlink(missing_ok=True)
    concat = PARTS / "concat.txt"
    concat.write_text("".join(f"file '{p.resolve()}'\n" for p in outputs))
    final_temp = PARTS / "final.incomplete.mp4"
    run([str(FFMPEG), "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
         "-f", "concat", "-safe", "0", "-i", str(concat),
         "-i", str(AUDIO), "-filter_complex",
         f"[1:a]adelay={round(intro_lead*1000)}:all=1,apad=whole_dur={duration}[a]",
         "-map", "0:v:0", "-map", "[a]",
         "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-t", str(duration),
         "-movflags", "+faststart", str(final_temp)])
    final_temp.replace(FINAL)
    print(f"Complete: {FINAL}", flush=True)


if __name__ == "__main__":
    main()
