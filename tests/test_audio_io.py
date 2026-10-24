from pathlib import Path
import sys
import os
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from audio_io import audio_info,playback_audio


@unittest.skipUnless(os.environ.get('RUN_MEDIA_EXPERIMENTS')=='1','M4A experiments suspended by user')
class M4ADecodeTests(unittest.TestCase):
    def test_aac_full_recording_decodes_and_has_browser_playback_file(self):
        path=ROOT/'tmp/media-tests/aac-full.m4a'
        if not path.exists(): self.skipTest('Generated AAC fixture is not present')
        info=audio_info(path)
        self.assertAlmostEqual(info.duration,1096,delta=.05)
        decoded,mime=playback_audio(path)
        self.assertEqual(mime,'audio/wav')
        self.assertEqual(decoded.suffix,'.wav')
        self.assertEqual(info.channels,2)

    def test_alac_short_fixture_decodes(self):
        path=ROOT/'tmp/media-tests/alac-short.m4a'
        if not path.exists(): self.skipTest('Generated ALAC fixture is not present')
        info=audio_info(path)
        self.assertAlmostEqual(info.duration,12,places=3)
        self.assertEqual(info.samplerate,44100)


if __name__=='__main__': unittest.main()
