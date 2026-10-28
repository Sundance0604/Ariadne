"""Make local transparent flame flipbooks from a licensed Fire Torch 012 ZIP.

The input ZIP is streamed into FFmpeg, so no full-size ProRes extraction is
left on disk. Download the free clip yourself from the FX Elements page.
"""

import argparse
import subprocess
import zipfile
from pathlib import Path


def build_atlas(archive, member, ffmpeg, start, output):
    filters = (
        f"trim=start={start}:duration=2.67,setpts=PTS-STARTPTS,"
        "crop=2160:2400:0:0,scale=128:128,format=rgba,"
        "colorchannelmixer=rr=1.38:gg=1.48:bb=1.5:aa=1.2,tile=8x8"
    )
    command = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", "pipe:0",
               "-vf", filters, "-frames:v", "1", str(output)]
    with archive.open(member) as source:
        process = subprocess.Popen(command, stdin=subprocess.PIPE,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        try:
            while chunk := source.read(1 << 20):
                try:
                    process.stdin.write(chunk)
                except BrokenPipeError:
                    break  # FFmpeg has read the frames it needs.
        finally:
            try:
                process.stdin.close()
            except BrokenPipeError:
                pass
        diagnostics = process.stderr.read().decode("utf-8", errors="replace")
        if process.wait() != 0:
            output.unlink(missing_ok=True)
            raise RuntimeError(f"FFmpeg failed for {output.name}: {diagnostics}")


def interpolate_atlas(ffmpeg, source, output):
    # Decode the 8x8 atlas as 64 consecutive frames at 24 fps, synthesize
    # motion-compensated intermediate frames, and pack 256 frames at 96 fps.
    filters = (
        "untile=8x8,setpts=N/(24*TB),"
        "minterpolate=fps=96:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1,"
        "format=rgba,tile=8x32"
    )
    command = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
               "-loop", "1", "-framerate", "1", "-i", str(source),
               "-vf", filters, "-frames:v", "1", str(output)]
    completed = subprocess.run(command, capture_output=True, text=True)
    if completed.returncode != 0:
        output.unlink(missing_ok=True)
        raise RuntimeError(f"Interpolation failed for {output.name}: {completed.stderr}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_zip", type=Path, help="Downloaded FireTorch-012-ProRes.zip")
    parser.add_argument("--ffmpeg", default="ffmpeg", help="FFmpeg executable")
    parser.add_argument("--output-dir", type=Path,
                        default=Path(__file__).resolve().parent / "assets" / "real-fire")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.source_zip) as archive:
        members = [name for name in archive.namelist()
                   if name.endswith("/FireTorch-012.mov") and not name.startswith("__MACOSX/")]
        if len(members) != 1:
            raise ValueError("The ZIP must contain exactly one FireTorch-012.mov")
        for letter, start in (("a", 0), ("b", 5), ("c", 10)):
            target = args.output_dir / f"flame-{letter}.png"
            build_atlas(archive, members[0], args.ffmpeg, start, target)
            print(target)
            smooth_target = args.output_dir / f"flame-smooth-{letter}.png"
            interpolate_atlas(args.ffmpeg, target, smooth_target)
            print(smooth_target)


if __name__ == "__main__":
    main()
