from fractions import Fraction as F
from pathlib import Path
import json,re,sys,threading,unittest
from urllib.parse import urljoin,urlparse
from urllib.request import urlopen
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))


class CompletionEvidence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from backend.musicxml_analysis.store import load_bundle
        from backend.musicxml_analysis.live_store import load_live
        cls.base=load_bundle(ROOT,ROOT);cls.live=load_live(ROOT,ROOT,cls.base)
        if not cls.live:raise unittest.SkipTest('No completion evidence')
        cls.notes={e['id']:e for e in cls.base['tables']['events']['events']}

    def frame(self,measure,onset):
        m=next(m for m in self.base['tables']['measures']['measures'] if m['measure_id']==measure)
        at=float(F(m['start_q'])+F(onset))
        return next(f for f in self.live['tables']['activation']['frames'] if f['start_q']<=at<f['end_q'])

    def test_two_readings_keep_bass_doubling_and_upper_E_chord_evidence_separate(self):
        f=self.frame('xml-m0064','0');readings=self.live['tables']['harmonic-readings']['readings'][f['harmony_window_id']]
        self.assertEqual(len(readings),2)
        layer=next(r for r in readings if r['kind']=='bass_pitch_class_layer_reduction')
        self.assertEqual(layer['description']['chord']['root'],'E')
        self.assertEqual(layer['functions'][0]['figure'],'II64')
        self.assertEqual({self.notes[id]['concert_pitch']['pc'] for id in layer['bass_event_ids']},{9})
        self.assertTrue(any(self.notes[id]['concert_pitch']['name']=='A4' for id in layer['bass_event_ids']))
        literal=next(w for w in self.base['tables']['harmony']['windows'] if w['id']==f['harmony_window_id'])
        self.assertEqual(set(layer['event_ids'])|set(layer['omitted_event_ids']),set(literal['event_ids']))

    def test_every_active_instrument_is_backed_by_current_source_events(self):
        for frame in self.live['tables']['activation']['frames']:
            self.assertLess(frame['start_q'],frame['end_q'])
            for p in frame['active_instruments']:
                for id in p['event_ids']:
                    e=self.notes[id]
                    self.assertEqual(e['part_id'],p['part_id'])
                    self.assertLessEqual(float(F(e['score_start_q'])),frame['start_q']+1e-9)
                    self.assertGreater(float(F(e['score_end_q'])),frame['start_q']-1e-9)
                    self.assertIsNone(e['exclusion_reason'])

    def test_bass_clarinet_does_not_appear_before_its_actual_upbeat(self):
        before=self.frame('xml-m0520','2');after=self.frame('xml-m0520','11/4')
        self.assertEqual({p['part_id'] for p in before['active_instruments']},{'P23','P30','P32','P35'})
        self.assertEqual({p['part_id'] for p in after['active_instruments']},{'P23','P30','P32','P35','P7'})

    def test_projection_is_structural_and_does_not_extend_truncated_last_measure(self):
        p=self.live['tables']['recording-projection']
        self.assertEqual(len(p['measure_checks']),535);self.assertTrue(all(c['start_agrees'] for c in p['measure_checks']))
        self.assertEqual(sum(c['duration_agrees'] for c in p['measure_checks']),534)
        self.assertEqual(p['reference_end_quarter'],1558.6)

    def test_form_boundaries_keep_the_upbeat_and_orchestral_overlap(self):
        f=self.live['tables']['form-synthesis'];sections={s['id']:s for s in f['sections']}
        self.assertEqual(sections['cadenza-1']['end_q'],sections['orchestral-return']['start_q'])
        self.assertLess(F(sections['reconstruction']['start_q']),F(sections['cadenza-2']['end_q']))
        self.assertEqual(len(f['models']),2)

    def test_browser_import_graph_is_actually_served_over_HTTP(self):
        import serve_review
        server=serve_review.ReviewServer(('127.0.0.1',0),serve_review.Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        base=f'http://127.0.0.1:{server.server_port}';queue=['/app.mjs'];seen=set()
        try:
            while queue:
                path=queue.pop()
                if path in seen:continue
                seen.add(path)
                with urlopen(base+path) as response:
                    self.assertIn('javascript',response.headers['Content-Type']);source=response.read().decode()
                for name in re.findall(r"(?:from\s*|import\s*)['\"]([^'\"]+\.mjs)['\"]",source):
                    queue.append(urlparse(urljoin(base+path,name)).path)
            self.assertIn('/musicxml-evidence.mjs',seen);self.assertIn('/musicxml-live.mjs',seen)
            self.assertIn('/score-analysis-model.mjs',seen)
        finally:server.shutdown();server.server_close();thread.join()


if __name__=='__main__':unittest.main()
