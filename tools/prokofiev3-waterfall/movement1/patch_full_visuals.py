"""Replace selected 20-second chunks without rerendering the movement.

Every replacement is sampled at absolute presentation time. Unchanged video
is copied from the approved full file, and its AAC audio is copied unchanged.
The source file is replaced only after the assembled file passes frame-count
and duration checks. Use --render-only to review the local replacements first.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from hashlib import sha256
from math import ceil
from pathlib import Path

from render_full import AUDIO, FFMPEG, FINAL, NODE, PARTS, RENDERER, ROOT, SHA

# Include the following 160–180 s chunk: the restored F attacks near video
# 2:38 can still have particles alive immediately after the 160 s boundary.
PATCH_STARTS = (140, 160, 260, 280)
PATCHES = ROOT / "local-visual-patch"


def run(command, *, env=None, capture=False):
    return subprocess.run(command, cwd=RENDERER, env=env, check=True,
                          stdout=subprocess.PIPE if capture else None,
                          stderr=subprocess.STDOUT if capture else None,
                          text=capture)


def current_signature():
    digest = sha256()
    for path in (ROOT / "prokofiev3-full-render.timeline.json",
                 RENDERER / "dist/waterfall.js",
                 RENDERER / "visual-preset.json",
                 RENDERER / "visual-style.json"):
        digest.update(path.read_bytes())
    digest.update(str(PATCH_STARTS).encode())
    digest.update(b"3840x2160/60fps/crf16/ultrafast")
    return digest.hexdigest()


def render_patches(duration):
    env = os.environ.copy()
    env.update(WATERFALL_WIDTH="3840", WATERFALL_HEIGHT="2160",
               WATERFALL_VIDEO_ONLY="1", WATERFALL_CRF="16",
               WATERFALL_ENCODING_PRESET="ultrafast",
               WATERFALL_ENCODER_THREADS="4",
               WATERFALL_VERIFIED_AUDIO_SHA256=SHA,
               FFMPEG_BINARY=str(FFMPEG))
    for start in PATCH_STARTS:
        if start + 20 > duration:
            raise ValueError(f"Patch {start} is beyond the final duration")
        source = PARTS / f"part-{start:03d}.json"
        if not source.exists():
            raise FileNotFoundError(f"Run prepare_full_chunks.py first: {source}")
        output = PATCHES / f"patch-{start:03d}.mp4"
        if output.exists() and output.stat().st_size > 100_000:
            print(f"reuse {output.name}", flush=True)
            continue
        temp = output.with_suffix(".incomplete.mp4")
        env["WATERFALL_START"] = str(start)
        env["WATERFALL_DURATION"] = "20"
        print(f"render patch {start:03d}-{start+20:03d}", flush=True)
        try:
            run([str(NODE), "export.mjs", str(source), str(AUDIO),
                 str(temp), "60"], env=env)
            temp.replace(output)
        finally:
            temp.unlink(missing_ok=True)


def segments(duration):
    cursor = 0.0
    for start in PATCH_STARTS:
        if cursor < start:
            yield "copy", cursor, float(start)
        yield "patch", float(start), float(start + 20)
        cursor = float(start + 20)
    if cursor < duration:
        yield "copy", cursor, duration


def assemble(duration):
    inputs = []
    for kind, start, end in segments(duration):
        if kind == "patch":
            path = PATCHES / f"patch-{int(start):03d}.mp4"
            if not path.exists():
                raise FileNotFoundError(path)
        else:
            label = f"copy-{int(start):03d}-{str(end).replace('.', 'p')}"
            path = PATCHES / f"{label}.mp4"
            if not path.exists():
                print(f"copy approved {start:g}-{end:g}", flush=True)
                run([str(FFMPEG), "-hide_banner", "-loglevel", "error",
                     "-nostdin", "-y", "-ss", str(start), "-i", str(FINAL),
                     "-t", str(end - start), "-map", "0:v:0",
                     "-c", "copy", "-an", str(path)])
        inputs.append(path)
    concat = PATCHES / "concat.txt"
    concat.write_text("".join(f"file '{p.resolve()}'\n" for p in inputs))
    temp = PATCHES / "full.incomplete.mp4"
    print("assemble replacement video with original audio", flush=True)
    run([str(FFMPEG), "-hide_banner", "-loglevel", "error", "-nostdin",
         "-y", "-f", "concat", "-safe", "0", "-i", str(concat),
         "-i", str(FINAL), "-map", "0:v:0", "-map", "1:a:0",
         "-c", "copy", "-t", str(duration), "-movflags", "+faststart",
         str(temp)])
    report = run([str(FFMPEG), "-hide_banner", "-loglevel", "info",
                  "-i", str(temp), "-map", "0:v:0", "-c", "copy",
                  "-f", "null", "-"], capture=True).stdout
    counts = re.findall(r"frame=\s*(\d+)", report)
    expected = round(duration * 60)
    if not counts or int(counts[-1]) != expected:
        raise RuntimeError(f"Expected {expected} frames, got {counts[-1:]}")
    if "3840x2160" not in report or "60 fps" not in report or "Audio: aac" not in report:
        raise RuntimeError("Final resolution, frame rate or audio stream changed")
    print(f"verified {expected} frames, 4K/60 fps and AAC audio", flush=True)
    temp.replace(FINAL)
    print(f"Complete: {FINAL}", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--render-only", action="store_true")
    args = parser.parse_args()
    duration = float(json.loads((ROOT / "prokofiev3-full-render.timeline.json")
                                .read_text())["render_interval"]["duration_seconds"])
    if ceil(duration) != 593:
        raise ValueError("Unexpected movement duration")
    PATCHES.mkdir(exist_ok=True)
    signature_file = PATCHES / "render-signature.sha256"
    signature = current_signature()
    if signature_file.exists() and signature_file.read_text() != signature:
        raise RuntimeError("Render inputs changed; clear the old local patch before resuming")
    signature_file.write_text(signature)
    render_patches(duration)
    if not args.render_only:
        assemble(duration)


if __name__ == "__main__":
    main()
