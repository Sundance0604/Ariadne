"""One-command, bounded-memory render of review clips or the whole movement.

Review clips are rendered sequentially. A full movement is divided into exact
frame-count video-only segments and the original WAV is muxed once at the end.
Frames stream directly into FFmpeg; there is never a PNG sequence on disk.
Successful full renders discard their segment cache by default.
"""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

import build_render_plan as plan_builder


ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
RENDERER = HERE / "gpu-vfx-flow"
DEFAULT_NODE = Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node"


def digest(path):
    h = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def executable(explicit, standard, fallback=None):
    if explicit:
        candidate = Path(explicit)
        if candidate.is_file():
            return str(candidate.resolve())
        match = shutil.which(explicit)
        if match:
            return match
        raise FileNotFoundError(explicit)
    match = shutil.which(standard)
    if match:
        return match
    if fallback and fallback.is_file():
        return str(fallback)
    raise FileNotFoundError(f"Install {standard} or supply --{standard}")


def ensure_bundle(node):
    bundle = RENDERER / "dist/waterfall.js"
    inputs = (list((RENDERER / "src").glob("**/*.js")) +
              list((RENDERER / "assets").glob("**/*.png")) +
              list((RENDERER / "assets").glob("**/*.jpg")) +
              [RENDERER / "package.json"])
    if bundle.is_file() and all(path.stat().st_mtime <= bundle.stat().st_mtime
                                for path in inputs):
        return
    subprocess.run([node, "node_modules/esbuild/bin/esbuild", "src/main.js", "--bundle",
                    "--format=esm", "--target=es2022", "--loader:.png=dataurl",
                    "--loader:.jpg=dataurl",
                    "--outfile=dist/waterfall.js"], cwd=RENDERER, check=True)


def run_export(timeline, audio, output, *, node, ffmpeg, fps, width, height, style,
               video_only=False, force=False, audio_sha256=None,
               renderer_sha256=None):
    manifest = output.with_suffix(".render.json")
    fingerprint = {
        "timeline_sha256": digest(timeline),
        "audio_sha256": audio_sha256 or digest(audio),
        "fps": fps, "width": width, "height": height,
        "video_only": video_only, "encoder": "libx264-fast-crf12-threads4",
        "renderer_sha256": renderer_sha256 or digest(RENDERER / "dist/waterfall.js"),
        "visual_style_sha256": digest(style),
    }
    if not force and output.is_file() and manifest.is_file():
        previous = json.loads(manifest.read_text())
        if (previous.get("inputs") == fingerprint and
                previous.get("output_sha256") == digest(output)):
            print(f"reuse {output.name}", flush=True)
            return
    temporary = output.with_name(output.stem + ".partial.mp4")
    if temporary.exists():
        temporary.unlink()
    env = os.environ.copy()
    env.update(FFMPEG_BINARY=ffmpeg, WATERFALL_WIDTH=str(width),
               WATERFALL_HEIGHT=str(height),
               WATERFALL_GPU_BACKEND=("metal" if sys.platform == "darwin" else "default"),
               WATERFALL_ENCODING_PRESET="fast", WATERFALL_CRF="12",
               WATERFALL_ENCODER_THREADS="4", WATERFALL_VIDEO_ONLY="1" if video_only else "0",
               WATERFALL_VERIFIED_AUDIO_SHA256=fingerprint["audio_sha256"],
               WATERFALL_STYLE_FILE=str(style.resolve()))
    started = time.monotonic()
    try:
        subprocess.run([node, "export.mjs", str(timeline), str(audio),
                        str(temporary), str(fps)], cwd=RENDERER, env=env, check=True)
        if not temporary.is_file() or temporary.stat().st_size < 1000:
            raise RuntimeError("FFmpeg did not produce a complete video")
        temporary.replace(output)
        record = {"inputs": fingerprint, "output_sha256": digest(output),
                  "bytes": output.stat().st_size,
                  "elapsed_seconds": round(time.monotonic() - started, 2)}
        manifest.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
        print(f"finished {output.name}: {record['elapsed_seconds']}s, "
              f"{record['bytes'] / 1048576:.1f} MiB", flush=True)
    finally:
        if temporary.exists():
            temporary.unlink()


def full_clips(source_duration, fps, chunk_seconds, intro=None):
    lead = intro["lead_in_seconds"] if intro else 0
    frames = round((source_duration + lead) * fps)
    chunk_frames = round(chunk_seconds * fps)
    for index, begin in enumerate(range(0, frames, chunk_frames)):
        count = min(chunk_frames, frames - begin)
        clip = {"start_seconds": max(0, begin / fps - lead),
                "duration_seconds": count / fps}
        if index == 0 and intro:
            clip["intro"] = intro
        yield index, clip


def mux_full(segments, audio, output, ffmpeg, duration, intro_lead=0):
    list_path = output.with_suffix(".concat.txt")
    temporary = output.with_name(output.stem + ".partial.mp4")
    if temporary.exists():
        temporary.unlink()
    try:
        list_path.write_text("ffconcat version 1.0\n" + "".join(
            f"file '{path.resolve()}'\n" for path in segments))
        subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
                        "-safe", "0", "-f", "concat", "-i", str(list_path),
                        "-i", str(audio), "-map", "0:v:0", "-map", "1:a:0",
                        "-c:v", "copy",
                        *(["-af", f"adelay={round(intro_lead * 1000)}:all=1,"
                                   f"apad=whole_dur={duration}"] if intro_lead else []),
                        "-c:a", "aac", "-b:a", "192k",
                        "-t", str(duration), "-movflags", "+faststart", str(temporary)],
                       check=True)
        temporary.replace(output)
    finally:
        if list_path.exists():
            list_path.unlink()
        if temporary.exists():
            temporary.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scene", default="all")
    parser.add_argument("--plan", type=Path, default=plan_builder.PLAN)
    parser.add_argument("--audio", type=Path)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "outputs")
    parser.add_argument("--node")
    parser.add_argument("--ffmpeg")
    parser.add_argument("--style", type=Path, default=RENDERER / "visual-style.json")
    parser.add_argument("--width", type=int)
    parser.add_argument("--height", type=int)
    parser.add_argument("--fps", type=int)
    parser.add_argument("--segment-seconds", type=int, default=30)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--keep-cache", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    args.style = args.style.resolve()
    if not args.style.is_file():
        raise FileNotFoundError(args.style)
    plan = json.loads(args.plan.read_text())
    if args.scene not in ("all", "full", *plan["clips"]):
        raise ValueError(f"Unknown scene {args.scene}")
    source = json.loads((ROOT / plan["source_timeline"]).read_text())
    match = re.search(r"-v(\d+)(?:\.|$)", plan["source_timeline"])
    version = plan.get("local_review_revision") or (f"v{match.group(1)}" if match else "v4")
    audio = args.audio or ROOT / plan["source_audio"]
    if not audio.is_file():
        raise FileNotFoundError(audio)
    fps = args.fps or plan["fps"]
    width = args.width or plan["output_width"]
    height = args.height or plan["output_height"]
    if fps not in (30, 60) or width < 640 or height < 360 or args.segment_seconds < 5:
        raise ValueError("Use 30/60 fps, a reasonable frame size and segments of at least 5 seconds")
    # export.mjs runs from the renderer directory; timelines and outputs must
    # remain addressable there even when the caller supplied a relative path.
    args.output_dir = args.output_dir.resolve()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(args.output_dir).free < 2 * 1024 ** 3:
        raise RuntimeError("At least 2 GiB of free space is needed for safe MP4 export")
    node = executable(args.node, "node", DEFAULT_NODE)
    ffmpeg = executable(args.ffmpeg, "ffmpeg")
    ensure_bundle(node)
    audio_sha256 = digest(audio)
    if plan.get("source_audio_sha256") and audio_sha256 != plan["source_audio_sha256"]:
        raise ValueError("Recording SHA-256 differs from this performance-specific render plan")
    renderer_sha256 = digest(RENDERER / "dist/waterfall.js")
    if args.scene == "full":
        source_duration = source["render_interval"]["duration_seconds"]
        last_visible = max(note["audio_end"] for note in source["notes"])
        if source_duration - last_visible > 8.0:
            raise RuntimeError(
                f"The visual timeline ends {source_duration - last_visible:.1f}s "
                "before the recording. Repair the ending alignment before "
                "exporting the full movement.")
        intro = plan["clips"].get("opening-title", {}).get("intro")
        intro_lead = intro["lead_in_seconds"] if intro else 0
        duration = round((source_duration + intro_lead) * fps) / fps
        output = args.output_dir / f"prokofiev2-movement1-{version}-full-{width}x{height}-{fps}fps.mp4"
        final_manifest = output.with_suffix(".render.json")
        full_inputs = {"source_timeline_sha256": digest(ROOT / plan["source_timeline"]),
                       "plan_sha256": digest(args.plan),
                       "visual_style_sha256": digest(args.style),
                       "audio_sha256": audio_sha256,
                       "renderer_sha256": renderer_sha256,
                       "width": width, "height": height, "fps": fps,
                       "duration_seconds": duration, "intro_seconds": intro_lead,
                       "segment_seconds": args.segment_seconds}
        if not args.force and output.is_file() and final_manifest.is_file():
            previous = json.loads(final_manifest.read_text())
            if previous.get("inputs") == full_inputs and previous.get("output_sha256") == digest(output):
                print(f"reuse complete {output}", flush=True)
                return
        cache = args.output_dir / "prokofiev2-render-cache-v1"
        cache.mkdir(exist_ok=True)
        segments = []
        for index, clip in full_clips(source_duration, fps, args.segment_seconds, intro):
            name = f"full-segment-{index:03}"
            timeline = plan_builder.build_scene(name, clip, plan, source, audio, cache,
                                                audio_sha256=audio_sha256)
            segment = cache / f"{name}-{width}x{height}-{fps}fps.mp4"
            segments.append(segment)
            if not args.dry_run:
                run_export(timeline, audio, segment, node=node, ffmpeg=ffmpeg,
                           fps=fps, width=width, height=height, style=args.style,
                           video_only=True, force=args.force,
                           audio_sha256=audio_sha256, renderer_sha256=renderer_sha256)
        if not args.dry_run:
            mux_full(segments, audio, output, ffmpeg, duration, intro_lead)
            final_manifest.write_text(json.dumps({"inputs": full_inputs,
                "output_sha256": digest(output), "bytes": output.stat().st_size,
                "segments": len(segments)}, ensure_ascii=False, indent=2) + "\n")
            if not args.keep_cache:
                shutil.rmtree(cache)
            print(f"complete {output}", flush=True)
    else:
        clips = plan["clips"] if args.scene == "all" else {args.scene: plan["clips"][args.scene]}
        for name, clip in clips.items():
            timeline = plan_builder.build_scene(name, clip, plan, source, audio, args.output_dir,
                                                audio_sha256=audio_sha256)
            seconds = f"{clip['duration_seconds']:g}"
            output = args.output_dir / f"prokofiev2-{name}-{version}-{seconds}s-{width}x{height}-{fps}fps.mp4"
            if not args.dry_run:
                run_export(timeline, audio, output, node=node, ffmpeg=ffmpeg,
                           fps=fps, width=width, height=height, style=args.style,
                           force=args.force,
                           audio_sha256=audio_sha256, renderer_sha256=renderer_sha256)


if __name__ == "__main__":
    main()
