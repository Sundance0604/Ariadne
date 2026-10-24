"""Playback smoke tests need only requirements.txt, without processing tools."""
from io import BytesIO
from pathlib import Path
import json
import sys
import threading
import unittest
from urllib.request import Request, urlopen

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import serve_review


class PlaybackInstallTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = serve_review.ReviewServer(('127.0.0.1', 0), serve_review.Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f'http://127.0.0.1:{cls.server.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def test_both_tracks_playback_payload_and_uncached_pdf_renderer(self):
        # Render directly to fresh files so an existing Poppler cache cannot
        # conceal missing playback dependencies in a new checkout.
        import uuid
        from pdf_render import render_page

        temporary = ROOT / 'tmp' / f'playback-render-{uuid.uuid4().hex}'
        for track, pages in [('ravel-left-hand', 100), ('lark-ascending', 35)]:
            with self.subTest(track=track):
                query = f'?track={track}'
                with urlopen(self.url + '/api/project' + query) as response:
                    project = json.load(response)
                with urlopen(self.url + '/api/analysis' + query) as response:
                    analysis = json.load(response)
                self.assertEqual(project['page_count'], pages)
                self.assertEqual(analysis['coverage']['pdf_pages'], pages)
                audio = ROOT / project['alignment']['audio']['path']
                request = Request(self.url + '/audio' + query, headers={'Range': 'bytes=0-1023'})
                with urlopen(request) as response:
                    self.assertEqual(response.status, 206)
                    with audio.open('rb') as source:
                        self.assertEqual(response.read(), source.read(1024))
                for page in [1, pages]:
                    output = temporary / f'{track}-{page}.png'
                    render_page(ROOT / project['mapping']['pdf_path'], page, output)
                    with Image.open(output) as picture:
                        self.assertGreater(picture.width, 500)
                        self.assertGreater(picture.height, 500)

    def test_server_delivers_rendered_page(self):
        with urlopen(self.url + '/page/1.png?track=lark-ascending') as response:
            self.assertEqual(response.headers.get_content_type(), 'image/png')
            with Image.open(BytesIO(response.read())) as picture:
                self.assertGreater(picture.width, 500)


if __name__ == '__main__':
    unittest.main()
