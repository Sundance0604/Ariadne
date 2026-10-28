"""Rebuild this performance's piano timeline from audio-derived note events.

The supplied orchestral reference is tied to the Yundi/Ozawa recording. The
recording hash is checked before any model work. Model files and WAV stems stay
in a local output directory; only the compact alignment is intended for Git.
"""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
import sys


HERE = Path(__file__).resolve().parent
PLAN = HERE / "render-plan.json"


def digest(path: Path) -> str:
    value = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            value.update(block)
    return value.hexdigest()


def executable(value: str, label: str) -> str:
    found = shutil.which(value)
    if found:
        return found
    path = Path(value)
    if path.is_file():
        return str(path.resolve())
    raise FileNotFoundError(f"{label} executable not found: {value}")


def separate(audio: Path, directory: Path, *, separator: str, model_dir: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    result = directory / "piano-stem.wav"
    if result.is_file():
        return result
    before = {p.resolve() for p in directory.glob("*.wav")}
    subprocess.run([
        separator, str(audio), "--model_filename", "BS-Roformer-SW.ckpt",
        "--model_file_dir", str(model_dir), "--single_stem", "piano",
        "--output_format", "WAV", "--output_dir", str(directory),
    ], check=True)
    created = [p for p in directory.glob("*.wav") if p.resolve() not in before]
    if len(created) != 1:
        raise RuntimeError(f"Expected one newly separated piano WAV in {directory}; found {created}")
    created[0].replace(result)
    return result


def transcribe(stem: Path, midi: Path, *, transkun: str, device: str) -> Path:
    if not midi.is_file():
        midi.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run([transkun, str(stem), str(midi), "--device", device], check=True)
    return midi


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True,
                        help="Local scratch directory, e.g. repo/local/prokofiev2-waterfall")
    parser.add_argument("--model-dir", type=Path,
                        help="Directory with BS-Roformer-SW.ckpt and its YAML")
    parser.add_argument("--separator", default="mlx-audio-separator")
    parser.add_argument("--transkun", default="transkun")
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--device", default="mps" if sys.platform == "darwin" else "cpu")
    parser.add_argument("--piano-stem", type=Path,
                        help="Already separated whole-movement piano WAV")
    parser.add_argument("--full-midi", type=Path,
                        help="Already transcribed whole-movement MIDI")
    parser.add_argument("--supplement-midi", type=Path,
                        help="Already transcribed 620–670 second crop MIDI")
    parser.add_argument("--skip-supplement", action="store_true")
    args = parser.parse_args()
    plan = json.loads(PLAN.read_text())
    audio = args.audio.resolve()
    if digest(audio) != plan["source_audio_sha256"]:
        raise ValueError("This recording differs from the Yundi/Ozawa reference timeline")
    work = args.work_dir.resolve()
    work.mkdir(parents=True, exist_ok=True)
    need_separator = not args.full_midi and not args.piano_stem or (
        not args.supplement_midi and not args.skip_supplement)
    separator = executable(args.separator, "separator") if need_separator else None
    if need_separator and args.model_dir is None:
        parser.error("--model-dir is required when separating audio")
    model_dir = args.model_dir.resolve() if args.model_dir else None
    if not args.full_midi:
        stem = args.piano_stem or separate(audio, work / "full-separation",
                                           separator=separator, model_dir=model_dir)
        full_midi = transcribe(stem, work / "movement1-transkun.mid",
                               transkun=executable(args.transkun, "Transkun"), device=args.device)
    else:
        full_midi = args.full_midi
    supplement = args.supplement_midi
    if supplement is None and not args.skip_supplement:
        crop = work / "ending-620-670.wav"
        if not crop.is_file():
            subprocess.run([executable(args.ffmpeg, "FFmpeg"), "-hide_banner", "-loglevel",
                            "error", "-ss", "620", "-t", "50", "-i", str(audio),
                            "-c:a", "pcm_s16le", str(crop)], check=True)
        crop_stem = separate(crop, work / "ending-separation",
                             separator=separator, model_dir=model_dir)
        supplement = transcribe(crop_stem, work / "ending-50s-transkun.mid",
                               transkun=executable(args.transkun, "Transkun"), device=args.device)
    command = [sys.executable, str(HERE / "align_audio_piano.py"),
               "--midi", str(full_midi), "--start", "0", "--end", "672.078367",
               "--output", str(work / "aligned-timeline.json"),
               "--qa", str(work / "alignment-qa.json")]
    if supplement:
        command += ["--supplement-midi", str(supplement), "--supplement-offset", "620"]
    subprocess.run(command, check=True)
    print(work / "aligned-timeline.json")


if __name__ == "__main__":
    main()
