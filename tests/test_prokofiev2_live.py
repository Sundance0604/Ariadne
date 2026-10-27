"""Check source identity, transpose, uncertain activity and tie boundaries."""
from pathlib import Path
from fractions import Fraction as F
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
from backend.prokofiev2 import bundle,endpoint
from build_prokofiev2_live import flow_notes
DATA=ROOT/'works/prokofiev-piano-concerto-2'
def read(p):return json.loads(p.read_text(encoding='utf8'))

class ProkofievLive(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder,cls.manifest=bundle(ROOT,DATA);cls.live=read(cls.folder/'live.json')
        cls.flow=read(cls.folder/'flow.json');cls.evidence=read(cls.folder/'evidence.json')['measures']

    def test_old_snapshot_preserved_and_new_clock_uses_the_same_recording_dtw(self):
        self.assertTrue((ROOT/read(DATA/'sync/history/playback-before-live.json')['path']/'manifest.json').exists())
        from prokofiev2_sync import digest
        self.assertEqual(self.live['projection']['alignment_sha256'],digest(DATA/'alignment.json'))
        self.assertEqual(self.flow['alignment_sha256'],digest(DATA/'alignment.json'))
        self.assertEqual(len(self.evidence),864)

    def test_activity_uses_half_open_note_intervals_not_measure_unions(self):
        m=self.evidence['xml-m0023'];frames=[f for f in self.live['frames'] if f['measure_id']=='xml-m0023']
        self.assertGreater(len({tuple(p['part_id'] for p in f['active_instruments']) for f in frames}),1)
        for f in frames:
            expected={e['id'] for e in m['events'] if F(e['start_q'])<=F(str(f['start_q']))+F(1,10**8)<F(e['end_q'])}
            actual={i for p in f['active_instruments'] for i in p['event_ids']}
            self.assertEqual(expected,actual)

    def test_transposing_instruments_and_percussion_keep_distinct_domains(self):
        events=[e for m in self.evidence.values() for e in m['events']]
        for pid,delta in [('P3',-2),('P6',-7),('P20',-12)]:
            sample=next(e for e in events if e['part_id']==pid)
            self.assertEqual(sample['concert_pitch']['ps']-sample['encoded_pitch']['ps'],delta)
        unpitched=[e for e in events if e['kind']=='unpitched'];self.assertTrue(unpitched)
        self.assertTrue(all(e['concert_pitch'] is None and not e['analysis_eligible'] for e in unpitched))
        self.assertFalse(any(n['part_id']=='P14' for n in self.flow['notes']))

    def test_quarantined_piano_activity_is_unknown_instead_of_reported_as_rest(self):
        bad=set(read(DATA/'sync/reference/written.json')['quarantine']['sequences'])
        for f in self.live['frames']:
            if int(f['measure_id'].removeprefix('xml-m')) in bad:
                self.assertTrue(f['activity_uncertainty'])
                w=self.live['windows'][f['harmony_window_id']]
                self.assertTrue(w['incomplete']);self.assertIsNone(w['chord'])
                self.assertFalse(any(p['part_id']=='P15' for p in f['active_instruments']))

    def test_flow_keeps_ties_contiguous_and_does_not_join_repeated_attacks(self):
        def note(i,a,b,tie):return {'id':i,'kind':'note','part_id':'P15','label':'Piano','staff':'1','voice':'1',
            'movement':1,'ps':60,'concert_pitch':{'name':'C4'},'start_q':str(a),'end_q':str(b),'tie':tie}
        events=[note('a',0,1,['start']),note('b',1,2,['stop']),note('c',2,3,[]),note('d',4,5,['stop'])]
        result=flow_notes(events,{'time_map':[{'midi_seconds':0,'audio_seconds':10},{'midi_seconds':3,'audio_seconds':16}]})
        self.assertEqual([n['event_ids'] for n in result['notes']],[['a','b'],['c'],['d']])
        self.assertEqual((result['notes'][0]['start_seconds'],result['notes'][0]['end_seconds']),(10,12))

    def test_evidence_endpoint_rejects_unknown_measure(self):
        with self.assertRaises(ValueError):endpoint(ROOT,DATA,'/api/musicxml-evidence',{'measure_id':['../../secret']})

if __name__=='__main__':unittest.main()
