"""Create small, restartable render inputs from the full visual timeline."""
import json
from math import ceil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "prokofiev3-full-render.timeline.json"
PARTS = ROOT / "full-render-parts"
LENGTH = 20


def main():
    full = json.loads(SOURCE.read_text())
    PARTS.mkdir(exist_ok=True)
    duration = float(full["render_interval"]["duration_seconds"])
    lead = float(full.get("intro", {}).get("lead_in_seconds", 0))
    for start in range(0, ceil(duration), LENGTH):
        end = min(start + LENGTH, duration)
        part = full.copy()
        part["render_interval"] = dict(start_seconds=start,
                                       duration_seconds=end-start,
                                       lookahead_seconds=5)
        part["notes"] = [n for n in full["notes"]
                         if n["audio_start"] + lead < end + 5.5 and
                         n["audio_end"] + lead > start - 8]
        (PARTS / f"part-{start:03d}.json").write_text(json.dumps(
            part, ensure_ascii=False, separators=(",", ":")))
        print(f"{start:03d}-{end:05.1f}: {len(part['notes'])} notes")


if __name__ == "__main__":
    main()
