"""Cross-track isolation tests use tiny workspace fixtures, never real anchors."""
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
from review_library import track_context


class TrackIsolationTests(unittest.TestCase):
    def test_routes_audio_bounds_and_anchors_stay_with_the_selected_track(self):
        fixture=ROOT/'tmp/library-isolation-test'
        fixture.mkdir(parents=True,exist_ok=True)
        (fixture/'resource').mkdir(exist_ok=True)
        tracks=[{'id':'first','title':'First','data_root':'.'},
                {'id':'second','title':'Second','data_root':'works/second'}]
        (fixture/'library.json').write_text(json.dumps({'default_track':'first','tracks':tracks}),encoding='utf-8')
        for i,track in enumerate(tracks):
            directory=fixture/track['data_root'];directory.mkdir(parents=True,exist_ok=True)
            audio=fixture/f'resource/{i}.mp3';audio.write_bytes(bytes([i])*20)
            project={'audio':{'path':f'resource/{i}.mp3','sha256':f'audio{i}','duration_seconds':60},
                'symbolic_reference':{'sha256':f'midi{i}'},'measures':[
                    {'measure_id':'m1','midi_start_seconds':0},
                    {'measure_id':'m2','midi_start_seconds':10}]}
            (directory/'alignment.json').write_text(json.dumps(project),encoding='utf-8')
            (directory/'measure-map.json').write_text(json.dumps({'page_count':35+i,
                'pdf_sha256':f'pdf{i}','measures':[{'page_number':1}]}),encoding='utf-8')
            # Repeated test runs keep old fixture history, with matching input fingerprints.
        previous=serve_review.ROOT;serve_review.ROOT=fixture
        server=serve_review.ReviewServer(('127.0.0.1',0),serve_review.Handler)
        worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        base=f'http://127.0.0.1:{server.server_port}'
        def get(path):
            with urlopen(base+path) as response:return json.load(response)
        def post(track,audio_hash='audio1'):
            body={'track_id':track,'audio_sha256':audio_hash,'score_sha256':'midi1',
                  'anchors':[{'measure_id':'m2','midi_seconds':10,'audio_seconds':12,'reason':'fixture'}]}
            with urlopen(Request(base+f'/api/anchors?track={track}',data=json.dumps(body).encode(),
                    headers={'Content-Type':'application/json'},method='POST')) as response:return json.load(response)
        try:
            self.assertEqual(len(get('/api/library')['tracks']),2)
            self.assertEqual(get('/api/project')['track']['id'],'first')
            self.assertEqual(get('/api/project?track=second')['page_count'],36)
            with self.assertRaises(HTTPError) as error:get('/api/project?track=../../')
            self.assertEqual(error.exception.code,404);error.exception.close()
            with self.assertRaises(HTTPError) as error:get('/page/37.png?track=second')
            self.assertEqual(error.exception.code,404);error.exception.close()
            request=Request(base+'/audio?track=second',headers={'Range':'bytes=3-6'})
            with urlopen(request) as response:
                self.assertEqual(response.status,206)
                self.assertEqual(response.headers['Content-Range'],'bytes 3-6/20')
                self.assertEqual(response.read(),bytes([1])*4)
            self.assertTrue(post('second')['saved'])
            self.assertFalse((fixture/'review-anchors.json').exists())
            anchor_path=fixture/'works/second/review-anchors.json'
            before=anchor_path.read_bytes()
            with self.assertRaises(HTTPError) as error:post('second','audio0')
            self.assertEqual(error.exception.code,400);error.exception.close()
            self.assertEqual(anchor_path.read_bytes(),before)
        finally:
            server.shutdown();server.server_close();worker.join();serve_review.ROOT=previous

    def test_catalog_rejects_a_configured_path_outside_the_workspace(self):
        fixture=ROOT/'tmp/library-path-test';fixture.mkdir(parents=True,exist_ok=True)
        (fixture/'library.json').write_text(json.dumps({'default_track':'escape',
            'tracks':[{'id':'escape','title':'Escape','data_root':'../../..'}]}),encoding='utf-8')
        with self.assertRaises(ValueError):track_context(fixture,'escape')


if __name__=='__main__':unittest.main()
