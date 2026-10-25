import sys
from pathlib import Path
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from check_publish import is_video


class PublishGuardTests(unittest.TestCase):
    def test_video_extensions_and_renamed_container_headers_are_blocked(self):
        for path in ['resource/mahler No.4/local.MP4','resource/mahler No.7/local.webm','resource/local.ts']:
            self.assertTrue(is_video(path,b''))
        self.assertTrue(is_video('renamed.bin',b'\x00\x00\x00\x18ftypisom'))
        self.assertTrue(is_video('renamed.bin',b'\x1aE\xdf\xa3'))
        self.assertTrue(is_video('renamed.bin',b'RIFF1234AVI '))

    def test_source_and_nonvideo_materials_remain_allowed(self):
        self.assertFalse(is_video('review/example.ts',b'export const value=1;'))
        self.assertFalse(is_video('score.pdf',b'%PDF-1.7'))
        self.assertFalse(is_video('audio.wav',b'RIFF1234WAVE'))
        self.assertFalse(is_video('audio.m4a',b'\x00\x00\x00\x18ftypM4A '))


if __name__=='__main__':unittest.main()
