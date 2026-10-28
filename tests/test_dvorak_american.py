"""Cross-layer checks for the source-bound quartet; not listening certification."""
from collections import Counter
from pathlib import Path
import unittest
from backend.video_export.content import read,review_events
from backend.video_export.editor import prepare
from backend.video_export.presentation import display_events
from backend.video_export.pipeline import validate_config
from backend.score_snapshot import bundle

ROOT=Path(__file__).resolve().parents[1]
WORK=ROOT/'works/dvorak-american'

class American(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder,cls.manifest=bundle(ROOT,WORK)
        cls.alignment=read(WORK/'alignment.json')

    def test_repeat_route_and_observed_geometry_are_separate(self):
        measures=self.alignment['measures'];geometry=read(WORK/'measure-map.json')
        self.assertEqual(Counter(m['movement'] for m in measures),{1:239,2:97,3:244,4:382})
        self.assertEqual(len({m['source_measure_id'] for m in measures}),853)
        self.assertEqual(len({m['measure_id'] for m in measures}),962)
        for m in measures:self.assertGreater(m['end_seconds'],m['start_seconds'])
        bars={m['source_sequence']:m for m in geometry['bar_regions']}
        self.assertEqual(len(bars),853)
        for b in bars.values():
            x,y,w,h=b['rect_pt']
            self.assertGreater(min(w,h),0);self.assertGreaterEqual(min(x,y),0)
            self.assertLessEqual(x+w,b['page_width_pt']+.1);self.assertLessEqual(y+h,b['page_height_pt']+.1)
            self.assertIsNone(b['printed_measure_number'])
        for i,seq in [(63,3),(532,276)]:
            self.assertEqual(measures[i]['source_sequence'],seq);self.assertEqual(measures[i]['visit'],2)

    def test_sustains_and_activity_do_not_cross_movement_pauses(self):
        ranges=self.alignment['score_time_coverage']['segments']
        flow=read(self.folder/'flow.json');registry=read(WORK/'metadata/visual-parts.json')
        self.assertEqual([p['id'] for p in registry['parts']],['P1','P2','P3','P4'])
        self.assertEqual(len(registry['harmony_groups']),4)
        self.assertTrue(all(p['family']=='弦乐' for p in registry['parts']))
        for n in flow['notes']:
            r=ranges[n['movement']-1]
            self.assertGreaterEqual(n['start_seconds'],r['start_seconds']-1e-7)
            self.assertLessEqual(n['end_seconds'],r['end_seconds']+1e-7)
        for w in read(self.folder/'live.json')['windows'].values():
            if w.get('display_label','').startswith('含震音'):
                self.assertIsNone(w['chord'])

    def test_captions_preserve_music_scopes_and_publishable_review(self):
        data=WORK/'video-export';config=read(data/'full-profile.json')
        validate_config(config)
        accepted,excluded=review_events(read(data/'annotations-source.json'),config,ROOT)
        self.assertEqual(len(accepted),253);self.assertEqual(excluded,[])
        rows=read(data/'captions-editable.json')['字幕']
        self.assertEqual(Counter(r['栏目'] for r in rows),{'和弦':49,'配器':49,'声部关系与复调':49,'曲式与主题发展':49,'导聆':49,'诠释':8})
        for r in rows:
            self.assertGreaterEqual(float(r['开始秒']),r['音乐范围'][0]-.001)
            self.assertLessEqual(float(r['结束秒']),r['音乐范围'][1]+.001)
        package=ROOT/'output/video-export/dvorak-american-full-001'
        if package.exists():
            cfg,events,excluded=prepare(read(data/'captions-editable.json'),package)
            for e in display_events(events,cfg):
                self.assertTrue(any(s['start_seconds']<=e['output_start']<e['output_end']<=s['end_seconds']
                    for s in self.alignment['score_time_coverage']['segments']))

    def test_new_track_preserves_previous_library_entries(self):
        before=read(WORK/'sync/history/library-before-sync.json');now=read(ROOT/'library.json')
        self.assertEqual(now['default_track'],before['default_track'])
        current={t['id']:t for t in now['tracks']}
        for t in before['tracks']:self.assertEqual(current[t['id']],t)

    def test_local_export_retains_source_frames_and_shared_score_plan(self):
        package=ROOT/'output/video-export/dvorak-american-full-001'
        if not package.exists():self.skipTest('Local media package not present')
        from backend.video_export.pipeline import verify_bindings
        from backend.video_export.visual_full import stage_visuals
        verify_bindings(package)
        self.assertTrue(read(package/'review-report.json')['checks']['no_unexpected_page_regression'])
        self.assertEqual(len(list((package/'score').glob('page-*.png'))),34)
        ready=read(WORK/'video-export/package-ready.json');revision=ROOT/ready['prepared_revision']
        cfg=read(revision/'config.json');grid=stage_visuals(package,revision,cfg)
        self.assertEqual(grid['frame_count'],50775);self.assertEqual(grid['fps'],30)
        plan=read(revision/'score-plan.json')['events']
        at=lambda t:next(e for e in plan if e['start']<=t<e['end'])
        for t in [600,1080,1360,1690,21,679,1208,1519]:self.assertFalse(at(t)['visible'])
        self.assertEqual(at(158.1)['page'],1);self.assertEqual(at(1292)['page'],18)
        self.assertTrue(at(35.9)['visible']);self.assertTrue(at(699.7)['visible'])

    def test_backward_page_requires_explicit_repeat_route(self):
        from backend.video_export.pipeline import expected_repeat_return
        project={'alignment':self.alignment}
        self.assertTrue(expected_repeat_return(project,'visit-0063','visit-0064',4,1))
        self.assertTrue(expected_repeat_return(project,'visit-0532','visit-0533',23,18))
        self.assertFalse(expected_repeat_return(project,'visit-0063','visit-0064',4,2))
        self.assertFalse(expected_repeat_return(project,'visit-0001','visit-0003',4,1))
        self.assertFalse(expected_repeat_return(project,'visit-0064','visit-0063',1,4))

if __name__=='__main__':unittest.main()
