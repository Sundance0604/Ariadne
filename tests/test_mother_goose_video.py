"""Ballet source boundaries, written activity and one independent video edition."""
from pathlib import Path
from fractions import Fraction as F
import copy,json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
from backend.mother_goose import bundle,endpoint
from backend.video_export.content import review_events,digest
from backend.video_export.pipeline import validate_config
DATA=ROOT/'works/ravel-mother-goose-video'
def read(p):return json.loads(p.read_text(encoding='utf-8'))

class BalletPlayback(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder,cls.manifest=bundle(ROOT,DATA)
        cls.score=read(DATA/'reference/written.json');cls.align=read(DATA/'alignment.json');cls.mapping=read(DATA/'measure-map.json')
        cls.live=read(cls.folder/'live.json');cls.research=read(cls.folder/'research.json')

    def test_suite_and_ballet_are_separate_editions(self):
        track=next(t for t in read(ROOT/'library.json')['tracks'] if t['id']=='ravel-mother-goose-video')
        self.assertNotIn('score_source',track)
        self.assertEqual(self.mapping['page_count'],98)
        self.assertEqual(self.align['audio']['sha256'],read(DATA/'media-sync.json')['video']['sha256'])
        self.assertEqual(len(self.research['essays']),7)
        self.assertEqual([len([m for m in self.score['measures'] if m['movement']==n]) for n in range(1,8)],[50,121,45,191,79,204,56])
        self.assertIsNone(self.manifest['human_signoff'])

    def test_no_duplicated_lookahead_and_traceable_source_notes(self):
        omitted=read(DATA/'reference/prelude-lookahead-audit.json')
        self.assertEqual(omitted['omitted_source_measure'],51)
        self.assertEqual(omitted['retained_source_measures'],[1,50])
        es=self.score['events'];self.assertEqual(len(es),len({e['id'] for e in es}))
        for e in es:
            self.assertTrue(e.get('source_event_id'));self.assertTrue(e.get('source_note_index'))
            self.assertTrue(e.get('voice'));self.assertTrue(e.get('staff'))
        try:from midi_score import read_midi
        except ImportError:return
        self.assertFalse(read_midi(ROOT/self.align['symbolic_reference']['path'])['anomalies'])

    def test_geometry_and_temporal_projection_are_separate(self):
        self.assertEqual(len(self.mapping['measures']),746)
        for b in self.mapping['measures']:
            self.assertIsNone(b['printed_measure_number'])
            x,y,w,h=b['rect_pt'];self.assertGreater(w,0);self.assertGreater(h,0)
            self.assertGreaterEqual(x,0);self.assertGreaterEqual(y,0)
            self.assertLessEqual(x+w,b['page_width_pt']+.1);self.assertLessEqual(y+h,b['page_height_pt']+.1)
            self.assertEqual(b['alignment_segment'],f"movement-{b['movement']}")
        gaps=[r for r in self.mapping['score_regions'] if r.get('no_symbolic_projection')]
        self.assertEqual(len(gaps),9)
        for g in gaps:
            self.assertNotIn('midi_start_seconds',g)
            self.assertLess(g['audio_start_seconds'],g['audio_end_seconds']);self.assertFalse(g['stable_candidate'])
        for a,b in zip(self.align['time_maps'],self.align['time_maps'][1:]):self.assertLessEqual(a['end_seconds'],b['start_seconds'])
        self.assertGreater(self.align['time_maps'][5]['start_seconds']-self.align['time_maps'][4]['end_seconds'],90)

    def test_realtime_events_are_active_in_the_claimed_written_interval(self):
        es={e['id']:e for e in self.score['events']}
        for frame in self.live['frames']:
            self.assertLess(frame['start_q'],frame['end_q'])
            active={id for p in frame['active_instruments'] for id in p['event_ids']}
            if frame['harmony_window_id']:self.assertEqual(active,set(self.live['windows'][frame['harmony_window_id']]['event_ids']))
            for id in active:
                e=es[id]
                self.assertLessEqual(float(F(e['start_q'])),frame['start_q']+1e-8)
                self.assertGreaterEqual(float(F(e['end_q'])),frame['end_q']-1e-8)

    def test_video_json_is_independent_readable_and_continuous(self):
        config=read(DATA/'video-export/full-profile.json');validate_config(config)
        editable=read(DATA/'video-export/captions-optimized.json');reviewed=read(DATA/'video-export/captions-reviewed.json')
        accepted,bad=review_events(reviewed,config,ROOT)
        self.assertFalse(bad);self.assertEqual(len(accepted),267)
        original=[e for e in editable['字幕'] if not e.get('实时帧')]
        archived=editable['分段和声配器底稿']
        self.assertTrue(all(e['显示'] is False for e in archived))
        current={e['编号']:e for e in original+archived}
        self.assertEqual(len(current),len(original)+len(archived))
        self.assertEqual(set(current),{e['id'] for e in accepted})
        self.assertEqual(len(config['chapters']),7)
        self.assertEqual(len(config['segments']),1)
        self.assertEqual(reviewed['alignment_sha256'],digest(DATA/'alignment.json'))
        # The later editable story revision preserves clocks and identities,
        # while its new prose is not the frozen earlier reviewed text.
        for event in accepted:
            row=current[event['id']]
            self.assertEqual((float(row['开始秒']),float(row['结束秒'])),
                             (event['video_start'],event['video_end']))
        self.assertTrue(editable['童话扩写']['sources'].endswith('story-sources.json'))
        changed=copy.deepcopy(config);changed['chapters'][2]['start']=changed['chapters'][1]['start']
        with self.assertRaises(ValueError):validate_config(changed)
        changed=copy.deepcopy(config);changed['music_start_confirmation']['human_signature']='invented'
        with self.assertRaises(ValueError):validate_config(changed)

    def test_runtime_evidence_exposes_scope_and_source_voices(self):
        evidence=endpoint(ROOT,DATA,'/api/musicxml-evidence',{'measure_id':['ballet-3-m001']})
        self.assertEqual(evidence['measure']['page'],31)
        self.assertTrue(evidence['events']);self.assertIn('休止',evidence['scope_note'])
        self.assertTrue(all(e['source_note_index'] for e in evidence['events']))
        with self.assertRaises(ValueError):endpoint(ROOT,DATA,'/api/musicxml-evidence',{'measure_id':['../../alignment.json']})

if __name__=='__main__':unittest.main()
