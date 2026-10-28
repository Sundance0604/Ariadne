"""Integration check for the frozen audio-derived piano alignment."""

import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest


HERE = Path(__file__).resolve().parents[1]


class RebuildTest(unittest.TestCase):
    def test_bundled_transcription_recreates_all_final_notes(self):
        with TemporaryDirectory() as folder:
            timeline = Path(folder) / "aligned.json"
            qa = Path(folder) / "qa.json"
            subprocess.run([
                sys.executable, str(HERE / "align_audio_piano.py"),
                "--midi", str(HERE / "data/movement1-transkun.mid"),
                "--supplement-midi", str(HERE / "data/ending-50s-transkun.mid"),
                "--supplement-offset", "620", "--start", "0",
                "--end", "672.078367", "--output", str(timeline),
                "--qa", str(qa),
            ], check=True, capture_output=True, text=True)
            expected = json.loads((HERE / "data/aligned-timeline-v9.json").read_text())
            rebuilt = json.loads(timeline.read_text())
            report = json.loads(qa.read_text())
            self.assertEqual(expected, rebuilt)
            self.assertEqual(report["audio_transcribed_piano_notes"], 5698)
            self.assertEqual(report["physical_release_cuts"], {"same_key": 7})
            self.assertEqual(report["score_time_fallback_notes"], 0)
            self.assertEqual(report["physical_violations"], {})


if __name__ == "__main__":
    unittest.main()
