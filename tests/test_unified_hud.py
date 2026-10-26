"""Source-bound musical demonstrations and stdlib HUD playback payload."""
from fractions import Fraction as F
from pathlib import Path
import sys,unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from backend.structure_analysis.common import read
from backend.musicxml_analysis.store import load_bundle
from backend.musicxml_analysis.live_store import load_live
from backend.musicxml_analysis.hud import load_hud,live_payload,audited_functions


class UnifiedHUDEvidence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base=load_bundle(ROOT,ROOT);cls.live=load_live(ROOT,ROOT,cls.base);cls.overlay=load_hud(ROOT,ROOT,cls.base)
        cls.windows={w['id']:w for w in cls.base['tables']['harmony']['windows']}
        cls.events={e['id']:e for e in cls.base['tables']['events']['events']}
        cls.cases={c['id']:c for c in cls.overlay['cases']['cases']}

    def test_every_demonstration_references_the_actual_window_and_note_ids(self):
        for c in self.cases.values():
            w=self.windows[c['window_id']]
            self.assertEqual(c['event_ids'],w['event_ids']);self.assertEqual(c['start_q'],w['start_q'])
            self.assertEqual(c['end_q'],w['end_q']);self.assertEqual(c['global_bass'],w['sonority']['bass'])
            self.assertTrue(all(id in self.events for id in c['event_ids']))
        self.assertEqual(self.overlay['cases']['human_signoffs'],0)
        self.assertEqual(self.overlay['cases']['expert_signoffs'],0)

    def test_m11_global_and_selected_layer_bass_and_conditional_figures_differ(self):
        w=self.windows[self.cases['m11-layers']['window_id']]
        r=next(r for r in self.live['tables']['harmonic-readings']['readings'][w['id']] if r['kind']=='bass_pitch_class_layer_reduction')
        self.assertEqual(w['sonority']['bass']['name'],'E1');self.assertEqual(r['description']['bass']['name'],'D2')
        self.assertEqual(r['description']['chord']['inversion'],2)
        self.assertEqual({self.events[id]['concert_pitch']['pc'] for id in r['omitted_event_ids']},{4})
        self.assertTrue(all(f['pitch_classes_agree'] for f in audited_functions(r,self.overlay)))
        context=self.overlay['cases']['contexts'][0];e=self.events[context['event_ids'][0]]
        self.assertEqual((context['start_q'],context['end_q']),(e['score_start_q'],e['score_end_q']))

    def test_m58_open_fifth_and_multiple_piano_voices_without_invented_third(self):
        c=self.cases['m58-open-fifth'];events=[self.events[id] for id in c['event_ids']]
        self.assertEqual({e['concert_pitch']['pc'] for e in events},{1,6})
        self.assertEqual({e['part_id'] for e in events},{'P23'})
        self.assertGreater(len({(e['voice'],e['staff']) for e in events}),1)
        self.assertIsNone(self.windows[c['window_id']]['sonority']['chord'])

    def test_m63_m64_are_distinct_time_windows_with_delayed_low_D(self):
        cases=[self.cases[k] for k in ['m63-upbeat','m64-upper-A','m64-low-A','m64-low-D']]
        self.assertEqual([c['global_bass']['name'] for c in cases],['A3','A3','A1','D1'])
        self.assertTrue(all(F(a['end_q'])<=F(b['start_q']) for a,b in zip(cases,cases[1:])))

    def test_m520_entry_is_time_specific_and_bad_roman_is_withheld(self):
        def frame(onset):return next(f for f in self.live['tables']['activation']['frames'] if f['measure_id']=='xml-m0520' and f['onset_q']==onset)
        self.assertEqual({p['part_id'] for p in frame('2')['active_instruments']},{'P23','P30','P32','P35'})
        self.assertIn('P7',{p['part_id'] for p in frame('11/4')['active_instruments']})
        r=self.live['tables']['harmonic-readings']['readings'][frame('2')['harmony_window_id']][0]
        bminor=next(f for f in audited_functions(r,self.overlay) if f['context']=='B小调')
        self.assertEqual(bminor['figure'],'bVI');self.assertFalse(bminor['pitch_classes_agree'])
        self.assertEqual(bminor['reconstructed_pitch_classes'],[1,6,10])
        self.assertEqual(r['functions'][0]['figure'],'bVI','frozen source must remain untouched')

    def test_m7_enharmonic_spelling_and_unpitched_instruments_remain_separate(self):
        w=next(w for w in self.windows.values() if w['measure_id']=='xml-m0007' and {'E1','Fb1'}<=set(w['sonority']['spelled_pitches']))
        pitches=[self.events[id]['concert_pitch'] for id in w['event_ids']]
        self.assertEqual({p['ps'] for p in pitches if p['name'] in {'E1','Fb1'}},{28})
        self.assertTrue(all(self.events[id]['kind']=='pitched' for id in w['event_ids']))
        frame=next(f for f in self.live['tables']['activation']['frames'] if f['harmony_window_id']==w['id'])
        self.assertTrue(any(any(self.events[id]['kind']=='unpitched' for id in p['event_ids']) for p in frame['active_instruments']))

    def test_payload_reuses_existing_frames_and_defers_note_details(self):
        payload=live_payload(self.base,self.live,self.overlay)
        self.assertEqual(len(payload['frames']),6801);self.assertEqual(len(payload['windows']),6660)
        self.assertNotIn('events',payload)
        self.assertTrue(all('event_ids' not in w for w in payload['windows'].values()))
        self.assertTrue(all('event_ids' not in r for rs in payload['readings'].values() for r in rs))
        self.assertLess(len(self.overlay['roman']['checks']),1000,'audit must deduplicate checks, not copy harmony events')


if __name__=='__main__':unittest.main()
