"""Real MP4 range/provenance checks plus rejected manual-sync inputs."""
import json
import math
from pathlib import Path
import sys
import subprocess
from contextlib import contextmanager
import uuid
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request,urlopen

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import serve_review
from media_sync import validate_anchors


@contextmanager
def workspace_fixture():
    # Windows managed workspaces reject tempfile's owner-only mkdir mode.
    path=ROOT/'tmp'/('video-test-'+uuid.uuid4().hex)
    path.mkdir(parents=True)
    yield path


class MappingValidationTests(unittest.TestCase):
    def test_rejects_nonfinite_reversed_and_outside_times(self):
        good=[{'masterTime':0,'videoTime':5},{'masterTime':10,'videoTime':15}]
        self.assertEqual(validate_anchors(good,30,30),good)
        for bad in [[],good[:1],[good[1],good[0]],
            [good[0],{'masterTime':True,'videoTime':20}],
            [good[0],{'masterTime':math.inf,'videoTime':20}],
            [good[0],{'masterTime':31,'videoTime':20}]]:
            with self.subTest(bad=bad),self.assertRaises(ValueError):validate_anchors(bad,30,30)

    def test_actual_silent_mp4_is_manual_only(self):
        try:
            from prepare_video import prepare
            from audio_io import find_ffmpeg
            ffmpeg=find_ffmpeg()
        except (ImportError,RuntimeError) as error:
            self.skipTest(f'Optional media processing dependency unavailable: {error}')
        directory=ROOT/'resource/.video-tests';directory.mkdir(parents=True,exist_ok=True)
        video=directory/'silent.mp4'
        subprocess.run([ffmpeg,'-nostdin','-hide_banner','-loglevel','error','-f','lavfi',
            '-i','color=c=black:s=64x64:r=5','-t','1','-an','-c:v','libx264','-y',str(video)],check=True,capture_output=True)
        with workspace_fixture() as temporary:
            manifest=prepare(video,temporary)
            self.assertFalse(manifest['hasAudio']);self.assertIsNone(manifest['analysisAudio'])
            self.assertEqual(manifest['matchStatus'],'manual_only')


class RealVideoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=serve_review.ReviewServer(('127.0.0.1',0),serve_review.Handler)
        cls.worker=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.worker.start()
        cls.base=f'http://127.0.0.1:{cls.server.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.worker.join()

    def test_real_video_payload_and_byte_ranges(self):
        with urlopen(self.base+'/api/project?track=mahler-4') as response:data=json.load(response)
        self.assertEqual(data['page_count'],127);self.assertEqual(data['media']['masterClock'],'video')
        self.assertEqual(data['alignment']['audio']['sha256'],data['media']['video']['sha256'])
        self.assertEqual(len(data['alignment']['measures']),1244)
        self.assertEqual(data['mapping']['measures'],[])
        video=ROOT/data['media']['video']['path']
        if not video.is_file():self.skipTest('Local Mahler performance videos are intentionally excluded from Git')
        length=video.stat().st_size
        for header,start,end in [('bytes=0-1023',0,1023),('bytes=800000000-800000127',800000000,800000127),('bytes=-128',length-128,length-1)]:
            with urlopen(Request(self.base+'/video?track=mahler-4',headers={'Range':header})) as response:
                self.assertEqual(response.status,206);self.assertEqual(response.headers['Content-Type'],'video/mp4')
                self.assertEqual(response.headers['Content-Range'],f'bytes {start}-{end}/{length}')
                with video.open('rb') as source:source.seek(start);self.assertEqual(response.read(),source.read(end-start+1))
        for header in ['bytes=99999999999-','bytes=2-1','bytes=0-1,4-5']:
            with self.assertRaises(HTTPError) as error:urlopen(Request(self.base+'/video?track=mahler-4',headers={'Range':header}))
            self.assertEqual(error.exception.code,416);error.exception.close()

    def test_old_tracks_have_no_video_and_analysis_is_independent(self):
        for track in ['ravel-left-hand','lark-ascending']:
            with urlopen(self.base+f'/api/project?track={track}') as response:self.assertIsNone(json.load(response)['media'])
            with self.assertRaises(HTTPError) as error:urlopen(self.base+f'/video?track={track}')
            self.assertEqual(error.exception.code,404);error.exception.close()
        with urlopen(self.base+'/api/analysis?track=mahler-4') as response:data=json.load(response)
        self.assertEqual(len(data['annotations']),38);self.assertGreaterEqual(len(data['references']),9)
        self.assertEqual(data['coverage']['guide_sections'],38)
        self.assertEqual(data['coverage']['movement_sections'],4)
        by_id={ref['source_id']:ref for ref in data['references']}
        self.assertEqual(by_id['mahler4-ref-8']['reading_status'],'abstract_checked')
        self.assertEqual(by_id['mahler4-ref-9']['reading_status'],'abstract_checked')


class ManualSyncAPITests(unittest.TestCase):
    def test_score_region_correction_history_and_wrong_media_rejection(self):
        with workspace_fixture() as temporary:
            fixture=Path(temporary)
            (fixture/'library.json').write_text(json.dumps({'default_track':'fixture','tracks':[{'id':'fixture','title':'Fixture','data_root':'.'}]}))
            (fixture/'alignment.json').write_text(json.dumps({'audio':{'sha256':'master','duration_seconds':60}}))
            (fixture/'measure-map.json').write_text(json.dumps({'pdf_sha256':'pdf','score_regions':[{'region_id':'r1'},{'region_id':'r2'}]}))
            previous=serve_review.ROOT;serve_review.ROOT=fixture
            server=serve_review.ReviewServer(('127.0.0.1',0),serve_review.Handler)
            worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
            url=f'http://127.0.0.1:{server.server_port}/api/score-region-anchor?track=fixture'
            request={'track_id':'fixture','audio_sha256':'master','pdf_sha256':'pdf','region_id':'r1',
                'start_seconds':12,'end_seconds':20,'reason':'test fixture only','confirmed':True}
            def post(body):return urlopen(Request(url,data=json.dumps(body).encode(),headers={'Content-Type':'application/json'},method='POST'))
            try:
                with post(request) as response:self.assertTrue(json.load(response)['saved'])
                with post({**request,'start_seconds':13}) as response:self.assertTrue(json.load(response)['saved'])
                path=fixture/'score-region-anchors.json';saved=json.loads(path.read_text())
                self.assertEqual(len(saved['history']),2);self.assertEqual(saved['anchors'][0]['start_seconds'],13)
                before=path.read_bytes()
                for bad in [{**request,'audio_sha256':'other'},{**request,'confirmed':False},
                            {**request,'end_seconds':10},{**request,'start_seconds':math.nan},
                            {**request,'region_id':'r2'}]:
                    with self.assertRaises(HTTPError) as error:post(bad)
                    self.assertEqual(error.exception.code,400);error.exception.close();self.assertEqual(path.read_bytes(),before)
            finally:
                server.shutdown();server.server_close();worker.join();serve_review.ROOT=previous

    def test_save_is_bound_to_track_and_fingerprints_with_history(self):
        with workspace_fixture() as temporary:
            fixture=Path(temporary);(fixture/'resource').mkdir()
            (fixture/'library.json').write_text(json.dumps({'default_track':'fixture','tracks':[{'id':'fixture','title':'Fixture','data_root':'.'}]}))
            (fixture/'alignment.json').write_text(json.dumps({'audio':{'sha256':'master','duration_seconds':30}}))
            media={'masterClock':'audio','video':{'sha256':'video','duration_seconds':40},'anchors':[]}
            path=fixture/'media-sync.json';path.write_text(json.dumps(media))
            previous=serve_review.ROOT;serve_review.ROOT=fixture
            server=serve_review.ReviewServer(('127.0.0.1',0),serve_review.Handler)
            worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
            url=f'http://127.0.0.1:{server.server_port}/api/media-sync?track=fixture'
            request={'track_id':'fixture','master_sha256':'master','video_sha256':'video',
                'same_performance_confirmed':True,'reason':'fixture evidence',
                'anchors':[{'masterTime':0,'videoTime':5},{'masterTime':30,'videoTime':35}]}
            def post(body):
                return urlopen(Request(url,data=json.dumps(body).encode(),headers={'Content-Type':'application/json'},method='POST'))
            try:
                with post(request) as response:self.assertTrue(json.load(response)['saved'])
                saved=json.loads(path.read_text());self.assertEqual(saved['matchStatus'],'manual_reviewed');self.assertEqual(len(saved['history']),1)
                before=path.read_bytes()
                for bad in [{**request,'video_sha256':'other'},{**request,'same_performance_confirmed':False},
                            {**request,'anchors':list(reversed(request['anchors']))}]:
                    with self.assertRaises(HTTPError) as error:post(bad)
                    self.assertEqual(error.exception.code,400);error.exception.close();self.assertEqual(path.read_bytes(),before)
            finally:
                server.shutdown();server.server_close();worker.join();serve_review.ROOT=previous


if __name__=='__main__':unittest.main()
