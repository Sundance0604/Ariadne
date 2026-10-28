"""Reuse an unchanged full-video prefix and render only changed final segments.

The plans may differ in the late eclipse and particle treatment. The cut must
precede the first changed frame. The original aligned audio is muxed once.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

if os.name == "nt":
    import msvcrt
else:
    import fcntl

import build_render_plan as builder
import render_movement as movement


def normalized_plan(plan):
    normalized = deepcopy(plan)
    normalized.pop("local_review_revision", None)
    normalized.pop("eclipse_fade", None)
    normalized.pop("eclipse_lane_cleanup_start_seconds", None)
    normalized.pop("tail_particle_bloom", None)
    normalized["filament_silence_intervals"] = [
        interval for interval in normalized.get("filament_silence_intervals", [])
        if interval[0] < 640]
    for cue in normalized["sections"]:
        appearance = cue.get("appearance_overrides", {})
        if appearance.get("eclipse_image") == "photo":
            appearance.pop("corona_tint", None)
            appearance.pop("eclipse_gold_mix", None)
    return normalized


def probe_duration(ffmpeg, path):
    result = subprocess.run([ffmpeg, "-hide_banner", "-i", str(path)],
                            capture_output=True, text=True)
    match = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", result.stderr)
    if not match:
        raise RuntimeError(f"Cannot read duration of {path}")
    return int(match[1]) * 3600 + int(match[2]) * 60 + float(match[3])


def frame_rgb(ffmpeg, path, seconds):
    result = subprocess.run([
        ffmpeg, "-hide_banner", "-loglevel", "error", "-ss", str(seconds),
        "-i", str(path), "-frames:v", "1", "-vf", "scale=960:540",
        "-pix_fmt", "rgb24", "-f", "rawvideo", "pipe:1"],
        capture_output=True, check=True)
    if len(result.stdout) != 960 * 540 * 3:
        raise RuntimeError(f"Could not decode boundary frame from {path}")
    return result.stdout


def verify_unchanged_join(ffmpeg, base_video, new_segment, cut_seconds):
    # Compare frames inside the retained part of the original video with the
    # corresponding frames in the newly generated suffix. No edited effect is
    # active at these times, so any particle jump shows up as a mismatch.
    for offset in (0, 10):
        old = frame_rgb(ffmpeg, base_video, cut_seconds + offset)
        new = frame_rgb(ffmpeg, new_segment, offset)
        mean_difference = sum(abs(a - b) for a, b in zip(old, new)) / len(old)
        print(f"join check +{offset}s: mean pixel difference "
              f"{mean_difference:.4f}/255", flush=True)
        if mean_difference > 1.0:
            raise RuntimeError("Re-rendered suffix differs before the eclipse; "
                               "do not join without investigating")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-plan", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--base-video", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--first-changed-segment", type=int, required=True)
    parser.add_argument("--segment-seconds", type=int, default=30)
    parser.add_argument("--ffmpeg", required=True)
    parser.add_argument("--keep-cache", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    old = json.loads(args.base_plan.read_text())
    plan = json.loads(args.plan.read_text())
    plan_hash = movement.digest(args.plan)
    if normalized_plan(old) != normalized_plan(plan):
        raise ValueError("Plans differ beyond permitted late visual settings")
    if args.first_changed_segment < 1 or args.segment_seconds < 5:
        raise ValueError("Choose a positive segment index and at least 5 seconds")
    if not args.base_video.is_file():
        raise FileNotFoundError(args.base_video)
    old_manifest = args.base_video.with_suffix(".render.json")
    if old_manifest.is_file():
        ancestor = json.loads(old_manifest.read_text())
        if movement.digest(args.base_video) != ancestor["output_sha256"]:
            raise ValueError("Base video checksum differs from its manifest")
        while "inputs" not in ancestor:
            ancestor_video = Path(ancestor["base_video"])
            if movement.digest(ancestor_video) != ancestor["base_video_sha256"]:
                raise ValueError("Base video ancestry checksum differs")
            ancestor = json.loads(ancestor_video.with_suffix(".render.json").read_text())
        base_inputs = ancestor["inputs"]
    else:
        # The approved v21 video remains local while its small portable
        # provenance record is committed. Earlier draft videos were removed.
        approved = json.loads((movement.HERE / "data/final-video.json").read_text())
        if movement.digest(args.base_video) != approved["video_sha256"]:
            raise ValueError("Base video differs from the approved v21 artifact")
        base_inputs = {
            "width": approved["video_width"],
            "height": approved["video_height"],
            "fps": approved["fps"],
            "segment_seconds": 30,
            "source_timeline_sha256": approved["packaged_timeline_sha256"],
            "audio_sha256": approved["source_audio_sha256"],
            "intro_seconds": 5,
            "duration_seconds": approved["video_duration_seconds"],
        }
    width, height, fps = (base_inputs[key] for key in ("width", "height", "fps"))
    if base_inputs["segment_seconds"] != args.segment_seconds:
        raise ValueError("Base video segment length differs")

    source_path = movement.ROOT / plan["source_timeline"]
    audio = movement.ROOT / plan["source_audio"]
    source = json.loads(source_path.read_text())
    if base_inputs["source_timeline_sha256"] != movement.digest(source_path):
        raise ValueError("Aligned source differs from base video")
    if plan.get("source_audio_sha256") and movement.digest(audio) != plan["source_audio_sha256"]:
        raise ValueError("Recording SHA-256 differs from this performance-specific render plan")
    if base_inputs["audio_sha256"] != movement.digest(audio):
        raise ValueError("Recording differs from base video")
    intro = plan["clips"].get("opening-title", {}).get("intro")
    intro_lead = intro["lead_in_seconds"] if intro else 0
    if base_inputs["intro_seconds"] != intro_lead:
        raise ValueError("Title lead-in differs from base video")
    duration = round((source["render_interval"]["duration_seconds"] +
                      intro_lead) * fps) / fps
    cut_seconds = args.first_changed_segment * args.segment_seconds
    cut_score_time = cut_seconds - intro_lead
    first_visible_photo = min(cue["at"] for cue in plan["sections"]
                              if cue.get("appearance_overrides", {}).get(
                                  "corona_opacity", 0) > 0 and
                              cue.get("appearance_overrides", {}).get(
                                  "eclipse_image") == "photo")
    eclipse_changed = (old.get("eclipse_fade") != plan.get("eclipse_fade") or
                       any(a.get("appearance_overrides", {}).get("corona_tint") !=
                           b.get("appearance_overrides", {}).get("corona_tint") or
                           a.get("appearance_overrides", {}).get("eclipse_gold_mix") !=
                           b.get("appearance_overrides", {}).get("eclipse_gold_mix")
                           for a, b in zip(old["sections"], plan["sections"])))
    changes = []
    if eclipse_changed:
        changes.append(first_visible_photo)
    if old.get("eclipse_lane_cleanup_start_seconds") != plan.get(
            "eclipse_lane_cleanup_start_seconds"):
        changes.append(plan["eclipse_lane_cleanup_start_seconds"])
    if old.get("tail_particle_bloom") != plan.get("tail_particle_bloom"):
        changes.append(plan["tail_particle_bloom"]["start_seconds"])
    if not changes:
        raise ValueError("No late visual effect changed")
    first_changed_time = min(changes)
    if cut_score_time >= first_changed_time:
        raise ValueError("Cut must precede the first changed visual effect")
    if abs(base_inputs["duration_seconds"] - duration) > 1 / fps:
        raise ValueError("Base video duration differs")

    clips = list(movement.full_clips(source["render_interval"]["duration_seconds"],
                                    fps, args.segment_seconds, intro))
    if args.first_changed_segment >= len(clips):
        raise ValueError("Cut lies past the last segment")
    print(f"retain 0–{cut_seconds:g}s; render segments "
          f"{args.first_changed_segment}–{len(clips)-1}; output {duration:g}s",
          flush=True)
    if args.dry_run:
        return

    args.output_dir = args.output_dir.resolve()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    lock_file = (args.output_dir / ".suffix-render.lock").open("a+")
    try:
        if os.name == "nt":
            if lock_file.tell() == 0:
                lock_file.write("0")
                lock_file.flush()
            lock_file.seek(0)
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (BlockingIOError, OSError) as error:
        raise RuntimeError("Another export is using this output directory") from error
    if shutil.disk_usage(args.output_dir).free < 3 * 1024 ** 3:
        raise RuntimeError("At least 3 GiB free space is required")
    node = movement.executable(None, "node", movement.DEFAULT_NODE)
    ffmpeg = movement.executable(args.ffmpeg, "ffmpeg")
    movement.ensure_bundle(node)
    renderer_hash = movement.digest(movement.RENDERER / "dist/waterfall.js")
    style = movement.RENDERER / "visual-style.json"
    audio_hash = movement.digest(audio)
    cache = args.output_dir / "suffix-render-cache"
    cache.mkdir(exist_ok=True)

    prefix = cache / "unchanged-prefix.mp4"
    if not prefix.is_file():
        subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin",
                        "-y", "-i", str(args.base_video.resolve()),
                        "-map", "0:v:0", "-frames:v", str(round(cut_seconds * fps)),
                        "-c:v", "copy", "-an", "-movflags", "+faststart",
                        str(prefix)], check=True)
    if abs(probe_duration(ffmpeg, prefix) - cut_seconds) > .02:
        raise RuntimeError("Video prefix was not cut at the exact segment boundary")
    print(f"retained prefix: {prefix.stat().st_size / 1048576:.1f} MiB", flush=True)

    pieces = [prefix]
    for index, clip in clips[args.first_changed_segment:]:
        if movement.digest(args.plan) != plan_hash or movement.digest(
                movement.RENDERER / "dist/waterfall.js") != renderer_hash:
            raise RuntimeError("Plan or renderer changed during export")
        name = f"full-segment-{index:03}"
        timeline = builder.build_scene(name, clip, plan, source, audio, cache,
                                       audio_sha256=audio_hash)
        segment = cache / f"{name}-{width}x{height}-{fps}fps.mp4"
        movement.run_export(timeline, audio, segment, node=node, ffmpeg=ffmpeg,
                            fps=fps, width=width, height=height, style=style,
                            video_only=True, audio_sha256=audio_hash,
                            renderer_sha256=renderer_hash)
        if index == args.first_changed_segment:
            verify_unchanged_join(ffmpeg, args.base_video, segment, cut_seconds)
        pieces.append(segment)

    version = plan["local_review_revision"]
    if movement.digest(args.plan) != plan_hash or movement.digest(
            movement.RENDERER / "dist/waterfall.js") != renderer_hash:
        raise RuntimeError("Plan or renderer changed during export")
    output = args.output_dir / f"prokofiev2-movement1-{version}-full-{width}x{height}-{fps}fps.mp4"
    movement.mux_full(pieces, audio, output, ffmpeg, duration, intro_lead)
    record = {"base_video": str(args.base_video.resolve()),
              "base_video_sha256": movement.digest(args.base_video),
              "plan_sha256": plan_hash,
              "renderer_sha256": renderer_hash,
              "first_changed_segment": args.first_changed_segment,
              "cut_seconds": cut_seconds, "duration_seconds": duration,
              "output_sha256": movement.digest(output), "bytes": output.stat().st_size}
    output.with_suffix(".render.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n")
    if not args.keep_cache:
        shutil.rmtree(cache)
    print(f"complete {output}", flush=True)


if __name__ == "__main__":
    main()
