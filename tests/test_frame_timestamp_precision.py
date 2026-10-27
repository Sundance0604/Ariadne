import unittest
from unittest.mock import patch
from types import SimpleNamespace
from backend.video_export.media import inspect_frames

class IntegerPTS(unittest.TestCase):
    def test_showinfo_integer_pts_preserve_precision_after_long_playback(self):
        log=('config in time_base: 1/16000, frame_rate: 30/1\n'
            'n: 0 pts: 16000001 pts_time:1000 duration:533 duration_time:0.0333125 s:640x480\n'
            'n: 1 pts: 16000534 pts_time:1000.03 duration:533 duration_time:0.0333125 s:640x480\n')
        with patch('backend.video_export.media.shutil.which',return_value=None),patch.dict('os.environ',{},clear=True),patch('backend.video_export.media.run',return_value=SimpleNamespace(stderr=log)):
            result=inspect_frames('ffmpeg','example.mp4',1000,1)
        self.assertAlmostEqual(result['first_pts'],16000001/16000,places=10)
        self.assertNotEqual(result['first_pts'],1000)
        self.assertEqual(result['stream']['time_base'],'1/16000')

if __name__=='__main__':unittest.main()
