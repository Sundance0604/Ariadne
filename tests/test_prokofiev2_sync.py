"""Source identities, observed geometry and independent movement-clock review."""
from pathlib import Path
from fractions import Fraction as F
from collections import Counter
import copy,json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
from backend.prokofiev2 import bundle,endpoint
from prokofiev2_sync import digest
DATA=ROOT/'works/prokofiev-piano-concerto-2'
def read(path):return json.loads(path.read_text(encoding='utf8'))

class ProkofievSynchronization(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.alignment=read(DATA/'alignment.json');cls.mapping=read(DATA/'measure-map.json')
        cls.reference=read(DATA/'sync/reference/written.json');cls.folder,cls.manifest=bundle(ROOT,DATA)

    def test_new_video_and_scan_fingerprints_are_bound_without_reusing_swiss_video(self):
        media=read(DATA/'media-sync.json');metadata=read(DATA/'metadata/recording.json')
        old=read(DATA/'metadata/recording-bringuier-tonhalle.json')
        self.assertEqual(self.alignment['audio']['sha256'],media['video']['sha256'])
        self.assertEqual(media['video']['sha256'],metadata['recording']['media']['sha256'])
        self.assertNotEqual(media['video']['sha256'],old['recording']['media']['sha256'])
        self.assertEqual(digest(ROOT/media['video']['path']),media['video']['sha256'])
        self.assertEqual(digest(ROOT/self.mapping['pdf_path']),self.mapping['pdf_sha256'])
        self.assertIsNone(self.manifest['human_signoff'])

    def test_all_source_intervals_have_positive_monotonic_times_and_pdf_regions(self):
        ms=self.alignment['measures'];boxes=self.mapping['measures']
        self.assertEqual(len(ms),864);self.assertEqual([m['measure_id'] for m in ms],[b['measure_id'] for b in boxes])
        self.assertEqual([sum(m['movement']==n for m in ms) for n in range(1,5)],[200,187,159,318])
        self.assertEqual(sum(m['local_number']=='X1' for m in ms),1)
        for m,b in zip(ms,boxes):
            self.assertLess(m['start_seconds'],m['end_seconds']);self.assertIsNone(b['printed_measure_number'])
            x,y,w,h=b['rect_pt'];self.assertGreater(w,0);self.assertGreater(h,0)
            self.assertGreaterEqual(x,0);self.assertGreaterEqual(y,0)
            self.assertLessEqual(x+w,b['page_width_pt']+.01);self.assertLessEqual(y+h,b['page_height_pt']+.01)
            self.assertEqual(b['alignment_segment'],f"movement-{m['movement']}")
        for a,b in zip(ms,ms[1:]):self.assertLessEqual(a['end_seconds'],b['start_seconds']+.001)

    def test_pauses_and_encore_are_outside_segmented_score_coverage(self):
        maps=self.alignment['time_maps'];coverage=self.alignment['score_time_coverage']
        self.assertEqual(len(maps),4);self.assertEqual(len(coverage['segments']),4)
        for a,b in zip(maps,maps[1:]):self.assertLess(a['end_seconds'],b['start_seconds'])
        for segment in maps:
            points=segment['time_map']
            for a,b in zip(points,points[1:]):
                self.assertLess(a['midi_seconds'],b['midi_seconds'])
                self.assertLessEqual(a['audio_seconds'],b['audio_seconds'])
            self.assertGreaterEqual(points[0]['audio_seconds'],segment['start_seconds'])
            self.assertLessEqual(points[-1]['audio_seconds'],segment['end_seconds'])
        self.assertLess(coverage['end_seconds'],self.alignment['audio']['duration_seconds']-300)

    def test_cadenza_shares_observed_system_instead_of_nine_guessed_boxes(self):
        shared=[b for b in self.mapping['measures'] if b['page_number']==140 and b['system_index']==0]
        self.assertEqual(len(shared),9)
        self.assertEqual(len({tuple(b['rect_pt']) for b in shared}),1)
        self.assertTrue(all(b['suppress_playhead'] for b in shared))
        ids={b['measure_id'] for b in shared}
        self.assertFalse(any(b['measure_id'] in ids for b in self.mapping['bar_regions']))
        self.assertEqual(len(self.mapping['score_regions']),294)
        self.assertEqual({b['page_number'] for b in self.mapping['measures']},set(range(1,169)))

    def test_reference_filters_known_piano_errors_without_rewriting_research(self):
        bad=set(self.reference['quarantine']['sequences'])
        for e in self.reference['events']:
            self.assertFalse(e['part_id']=='P15' and e['sequence'] in bad)
            self.assertNotEqual(e['part_id'],'P14');self.assertTrue(e['eligible'])
            self.assertLess(F(e['start_q']),F(e['end_q']))
        for seq,extent in [(811,'13'),(812,'25/2')]:
            self.assertEqual(F(self.reference['measures'][seq-1]['duration_q']),F(extent))
        self.assertIsNone(read(DATA/'analysis/symbolic-source-summary.json')['global_score_time'])

    def test_prose_and_hud_stay_attributed_with_separate_written_activity(self):
        a=endpoint(ROOT,DATA,'/api/analysis',{});r=endpoint(ROOT,DATA,'/api/research',{})
        self.assertEqual(len(a['annotations']),38);self.assertEqual(len(r['essays']),4)
        self.assertEqual(Counter(e['dimension'] for e in r['events']),{'harmony':38,'orchestration':38,'counterpoint':38,'form':38})
        live=endpoint(ROOT,DATA,'/api/musicxml-live',{})
        self.assertTrue(live['available']);self.assertEqual(live['readings'],{})
        self.assertEqual(a['pdf_sha256'],self.mapping['pdf_sha256'])
        for note in a['annotations']:
            self.assertLess(note['start_seconds'],note['end_seconds'])
            self.assertTrue(note['html']);self.assertGreaterEqual(note['start_pdf_page'],1)

    def test_prior_editions_and_local_only_video_are_preserved(self):
        history=read(DATA/'sync/history/library-before-sync.json');current=read(ROOT/'library.json')
        current['tracks']=[t for t in current['tracks'] if t['id']!='prokofiev-piano-concerto-2']
        self.assertEqual(history,current)
        for c in read(DATA/'sync/source-preservation.json')['checks']:
            if c['path']!='library.json':self.assertEqual(digest(ROOT/c['path']),c['sha256'])
        self.assertFalse(read(DATA/'sync/source-preservation.json')['video_generated'])
        # The later user-authorized full export preparation may add JSON here;
        # the source and generated videos stay in ignored local directories.
        self.assertFalse(list((DATA/'video-export').glob('*.mp4')))

if __name__=='__main__':unittest.main()
