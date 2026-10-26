"""Compatibility entry point; implementation lives in scripts/video_export/."""
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.video_export.export_video import main

if __name__=='__main__':main()
