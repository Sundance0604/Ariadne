"""Shared score sources, isolated performance clocks and actual video delivery."""
import copy
import json
from pathlib import Path
import sys
import threading
import unittest
import uuid
from urllib.request import Request,urlopen

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from review_library import score_directory,track_context
from backend.structure_analysis.common import read,write,digest


class SharedScoreTests(unittest.TestCase):
    def setUp(self):
        self.root=ROOT/'tmp'/('shared-score-'+uuid.uuid4().hex)
        self.shared=self.root/'score';self.video=self.root/'video'
        write(self.root/'library.json',{'default_track':'score','tracks':[
            {'id':'score','data_root':'score'},
            {'id':'video','data_root':'video','score_source':'score'}]})
        for folder in [self.shared,self.video]:
            write(folder/'measure-map.json',{'pdf_sha256':'same-pdf'})
            write(folder/'alignment.json',{'symbolic_reference':{'sha256':'same-midi'}})
            write(folder/'metadata/recording.json',{'work':{'work_id':'same-work'}})

    def test_shared_sources_are_explicit_and_same_edition(self):
        self.assertEqual(score_directory(self.root,self.video),self.shared)
        self.assertEqual(score_directory(self.root,self.shared),self.shared)

    def test_rejects_different_pdf_midi_and_work(self):
        for name,document in [('measure-map.json',{'pdf_sha256':'other'}),
                ('alignment.json',{'symbolic_reference':{'sha256':'other'}}),
                ('metadata/recording.json',{'work':{'work_id':'other'}})]:
            with self.subTest(name=name):
                old=read(self.video/name);write(self.video/name,document)
                with self.assertRaises(ValueError):score_directory(self.root,self.video)
                write(self.video/name,old)

    def test_rejects_unknown_sources_chains_and_directory_escape(self):
        catalog=read(self.root/'library.json')
        for source in ['unknown','video']:
            changed=copy.deepcopy(catalog);changed['tracks'][1]['score_source']=source
            write(self.root/'library.json',changed)
            with self.assertRaises(ValueError):score_directory(self.root,self.video)
        changed=copy.deepcopy(catalog);changed['tracks'][0]['score_source']='video'
        write(self.root/'library.json',changed)
        with self.assertRaises(ValueError):score_directory(self.root,self.video)
        with self.assertRaises(ValueError):score_directory(self.root,self.root.parent)


class RealRavelVideoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import serve_review
        cls.directory=ROOT/'works/ravel-left-hand-video'
        if not (cls.directory/'project.json').exists():raise unittest.SkipTest('Video edition not prepared')
        cls.media=read(cls.directory/'media-sync.json')
        cls.server=serve_review.ReviewServer(('127.0.0.1',0),serve_review.Handler)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.url=f'http://127.0.0.1:{cls.server.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join()

    def get(self,path):
        with urlopen(self.url+path,timeout=60) as response:return json.load(response)

    def test_preserves_original_and_uses_own_video_audio(self):
        preservation=read(self.directory/'reports/source-preservation.json')
        self.assertTrue(preservation['unchanged'])
        self.assertEqual(preservation['before'],{p:digest(ROOT/p) for p in preservation['before']})
        video=self.get('/api/project?track=ravel-left-hand-video')
        old=self.get('/api/project?track=ravel-left-hand')
        self.assertIsNone(old['media']);self.assertEqual(video['media']['masterClock'],'video')
        self.assertNotEqual(old['alignment']['audio']['sha256'],video['alignment']['audio']['sha256'])
        self.assertEqual(video['alignment']['audio']['sha256'],self.media['video']['sha256'])
        self.assertEqual(len(video['alignment']['measures']),535)
        self.assertEqual(video['mapping'],old['mapping'])
        self.assertEqual(len(video['symbolic_pdf_regions'] or []),535)
        coverage=video['alignment']['score_time_coverage']
        self.assertEqual(coverage['start_seconds'],27.5);self.assertEqual(coverage['end_seconds'],1162.5)
        self.assertGreaterEqual(video['alignment']['measures'][0]['start_seconds'],27.5)
        self.assertLessEqual(video['alignment']['measures'][-1]['end_seconds'],1162.5)
        self.assertNotEqual(video['alignment']['measures'][63]['start_seconds'],old['alignment']['measures'][63]['start_seconds'])
        raw=read(self.directory/'alignment.music.raw.json')
        self.assertAlmostEqual(video['alignment']['measures'][63]['start_seconds'],raw['measures'][63]['start_seconds']+27.5)
        self.assertEqual(video['alignment']['alignment_transform']['raw_alignment_sha256'],digest(self.directory/'alignment.music.raw.json'))

    def test_reuses_essays_guides_and_correct_video_recording_identity(self):
        video=self.get('/api/research?track=ravel-left-hand-video')
        old=self.get('/api/research?track=ravel-left-hand')
        self.assertEqual([e['html'] for e in video['essays']],[e['html'] for e in old['essays']])
        self.assertEqual(len(video['events']),len(old['events']))
        self.assertFalse(any(k.endswith('error') for k in video))
        xml=next(e for e in video['events'] if e.get('analysis_origin')=='musicxml_analysis')
        self.assertIn('track=ravel-left-hand-video&',xml['evidence_url'])
        guide=self.get('/api/analysis?track=ravel-left-hand-video')
        original=self.get('/api/analysis?track=ravel-left-hand')
        self.assertEqual(guide['full_html'],original['full_html'])
        self.assertEqual(guide['recording']['soloists'][0]['original_name'],'Pierre-Laurent Aimard')
        self.assertEqual(guide['recording']['conductor']['original_name'],'Marko Letonja')
        self.assertEqual(guide['recording']['audio_sha256'],self.media['video']['sha256'])

    def test_shared_live_evidence_has_separate_projection_and_rejects_old_clock(self):
        if not (ROOT/self.media['video']['path']).is_file():self.skipTest('Local video is not published')
        from backend.musicxml_analysis.store import load_bundle
        from backend.musicxml_analysis.live_store import load_live
        from backend.musicxml_analysis.projection import rebind_projection
        bundle=load_bundle(ROOT,ROOT);old=load_live(ROOT,ROOT,bundle)
        live=load_live(ROOT,self.directory,bundle,score_work=ROOT)
        self.assertIs(live['tables']['activation'],old['tables']['activation'])
        self.assertIs(live['tables']['harmonic-readings'],old['tables']['harmonic-readings'])
        projection=live['tables']['recording-projection']
        self.assertNotEqual(projection['audio_sha256'],old['tables']['recording-projection']['audio_sha256'])
        self.assertEqual(projection['alignment_sha256'],digest(self.directory/'alignment.json'))
        self.assertTrue(all(c['start_agrees'] for c in projection['measure_checks']))
        wrong=copy.deepcopy(old['tables']['recording-projection']);wrong['midi_sha256']='other'
        with self.assertRaises(ValueError):rebind_projection(ROOT,self.directory/'alignment.json',bundle,wrong)
        from backend.musicxml_analysis.projection import load_projection
        fixture=ROOT/'tmp'/('stale-video-clock-'+uuid.uuid4().hex)
        changed=read(self.directory/'alignment.json');changed['time_map'][1]['audio_seconds']+=.01
        write(fixture/'alignment.json',changed);write(fixture/'projection.json',projection)
        write(fixture/'project.json',{'files':{'musicxml_recording_projection':{
            'path':(fixture/'projection.json').relative_to(ROOT).as_posix(),'sha256':digest(fixture/'projection.json')}}})
        with self.assertRaisesRegex(ValueError,'changed alignment'):
            load_projection(ROOT,fixture,bundle,old['tables']['recording-projection'])
        result=self.get('/api/musicxml-live?track=ravel-left-hand-video')
        self.assertTrue(result['available']);self.assertEqual(len(result['frames']),6801)
        self.assertEqual(result['projection']['audio_sha256'],self.media['video']['sha256'])

    def test_video_byte_range_delivers_new_file(self):
        video=ROOT/self.media['video']['path']
        if not video.is_file():self.skipTest('Local video is not published')
        with urlopen(Request(self.url+'/video?track=ravel-left-hand-video',headers={'Range':'bytes=0-127'}),timeout=30) as response:
            self.assertEqual(response.status,206)
            self.assertEqual(response.headers['Content-Type'],'video/mp4')
            with video.open('rb') as source:self.assertEqual(response.read(),source.read(128))


if __name__=='__main__':unittest.main()
