"""Exercise anchor persistence in a workspace-only fixture, never the real project."""
import json
from pathlib import Path
import sys
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request,urlopen

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import serve_review


class AnchorStorageTests(unittest.TestCase):
    def test_anchor_roundtrip_history_and_invalid_order(self):
        fixture=(ROOT/'tmp/review-storage-test').resolve()
        self.assertTrue(fixture.is_relative_to((ROOT/'tmp').resolve()))
        fixture.mkdir(parents=True,exist_ok=True)
        project=json.loads((ROOT/'alignment.json').read_text(encoding='utf-8'))
        project['test_fixture']=True
        (fixture/'alignment.json').write_text(json.dumps(project),encoding='utf-8')
        previous_root=serve_review.ROOT
        serve_review.ROOT=fixture
        server=serve_review.ThreadingHTTPServer(('127.0.0.1',0),serve_review.Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        url=f'http://127.0.0.1:{server.server_port}/api/anchors'
        measure=project['measures'][1]
        anchor={'measure_id':measure['measure_id'],'midi_seconds':measure['midi_start_seconds'],
                'audio_seconds':13.5,'reason':'automated test fixture only','source':'test'}
        def post(anchors):
            request=Request(url,data=json.dumps({'anchors':anchors}).encode(),
                headers={'Content-Type':'application/json'},method='POST')
            with urlopen(request) as response: return json.load(response)
        try:
            self.assertTrue(post([anchor])['saved'])
            anchor={**anchor,'audio_seconds':14.0}
            self.assertTrue(post([anchor])['saved'])
            stored=json.loads((fixture/'review-anchors.json').read_text(encoding='utf-8'))
            self.assertEqual(stored['anchors'][0]['audio_seconds'],14.0)
            self.assertEqual(stored['history'][-1]['old_anchors'][0]['audio_seconds'],13.5)
            wrong={**anchor,'measure_id':project['measures'][2]['measure_id'],
                   'midi_seconds':project['measures'][2]['midi_start_seconds'],'audio_seconds':1}
            with self.assertRaises(HTTPError) as caught: post([anchor,wrong])
            self.assertEqual(caught.exception.code,400)
            caught.exception.close()
            self.assertEqual((fixture/'review-anchors.json').read_text(encoding='utf-8'),
                             json.dumps(stored,ensure_ascii=False,indent=2))
        finally:
            server.shutdown();server.server_close();thread.join();serve_review.ROOT=previous_root


if __name__=='__main__': unittest.main()
