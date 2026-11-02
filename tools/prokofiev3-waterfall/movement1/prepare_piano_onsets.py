"""Regenerate the small, score-filtered piano onset input for the review clip.

Install mlx-audio-separator 0.1.20 and Transkun 2.0.1 in separate environments,
then point this command at their executables and the BS-Roformer-SW model.
The large crop and stem live in a caller-chosen scratch directory; the only
preserved project artifact is the compact 125-second onset MIDI.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess
import tempfile
import sys

from prepare_preview import AUDIO, EXPECTED_AUDIO_SHA256, FFMPEG, HERE, digest


def executable(value: str) -> str:
    found=shutil.which(value)
    if found:return found
    path=Path(value)
    if path.is_file():return str(path.resolve())
    raise FileNotFoundError(value)


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-dir",type=Path,required=True)
    parser.add_argument("--separator",default="mlx-audio-separator")
    parser.add_argument("--transkun",default="transkun")
    parser.add_argument("--device",default="mps" if sys.platform=="darwin" else "cpu")
    parser.add_argument("--scratch",type=Path,default=Path(tempfile.gettempdir())/"prokofiev3-piano-onsets")
    parser.add_argument("--start",type=float,default=0.)
    parser.add_argument("--seconds",type=float,default=125.)
    parser.add_argument("--output",type=Path,default=HERE/"piano-audio125-transkun.mid")
    parser.add_argument("--force",action="store_true")
    args=parser.parse_args()
    if digest(AUDIO)!=EXPECTED_AUDIO_SHA256:raise ValueError("Recording fingerprint changed")
    if args.start<0 or args.seconds<=0:raise ValueError("Invalid crop interval")
    output=args.output.resolve()
    if output.is_file() and not args.force:
        print(f"Reusing {output}")
        return
    model=args.model_dir.resolve()
    for name in ("BS-Roformer-SW.ckpt","BS-Roformer-SW.yaml"):
        if not (model/name).exists():raise FileNotFoundError(model/name)
    scratch=args.scratch.resolve();scratch.mkdir(parents=True,exist_ok=True)
    crop=scratch/f"audio{args.start:g}-{args.start+args.seconds:g}.wav"
    if not crop.is_file() or args.force:
        subprocess.run([str(FFMPEG),"-hide_banner","-loglevel","error","-y",
                        "-ss",str(args.start),"-i",str(AUDIO),"-t",str(args.seconds),
                        "-ar","44100","-ac","2",
                        "-c:a","pcm_s16le",str(crop)],check=True)
    stem_dir=scratch/"stems";stem_dir.mkdir(exist_ok=True)
    before={p.resolve() for p in stem_dir.glob("*.wav")}
    subprocess.run([executable(args.separator),str(crop),"--model_filename",
                    "BS-Roformer-SW.ckpt","--model_file_dir",str(model),
                    "--single_stem","piano","--output_format","WAV",
                    "--output_dir",str(stem_dir)],check=True)
    created=[p for p in stem_dir.glob("*.wav") if p.resolve() not in before]
    if not created:
        created=[p for p in stem_dir.glob("*.wav") if "piano" in p.name.lower()]
    if len(created)!=1:raise RuntimeError(f"Expected one piano stem, found {created}")
    temporary=scratch/f"piano-audio{args.start:g}-{args.start+args.seconds:g}-transkun.mid"
    subprocess.run([executable(args.transkun),str(created[0]),str(temporary),
                    "--device",args.device],check=True)
    if not temporary.is_file() or temporary.stat().st_size<100:
        raise RuntimeError("Piano onset transcription did not produce MIDI")
    shutil.copy2(temporary,output)
    print(output)


if __name__=="__main__":main()
