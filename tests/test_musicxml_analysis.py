import copy
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import uuid
import threading
from urllib.request import urlopen
from urllib.error import HTTPError
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
try:
    import music21
except ImportError:music21=None


@unittest.skipUnless(music21,'Optional MusicXML processing dependency unavailable')
class MusicalSemantics(unittest.TestCase):
    def test_actual_bass_controls_major_chord_inversion(self):
        from backend.musicxml_analysis.analyze import chord_description
        from backend.musicxml_analysis.ingest import pitch_record
        def describe(names):return chord_description([{'concert_pitch':pitch_record(music21.pitch.Pitch(n))} for n in names])
        for bass,expected in [('D3',0),('F#2',1),('A2',2)]:
            with self.subTest(bass=bass):
                result=describe([bass,'D4','F#4','A4'])
                self.assertEqual(result['chord']['root'],'D');self.assertEqual(result['chord']['inversion'],expected)
        result=describe(['G2','B3','D4','F4'])
        self.assertEqual(result['chord']['quality'],'dominant seventh chord')
        self.assertEqual(describe(['F2','G3','B3','D4'])['chord']['inversion'],3)
        self.assertIsNone(describe(['E1','A1','D2','G2'])['chord'])
        self.assertIn('quartal',describe(['E1','A1','D2','G2'])['structures'])

    def test_ottava_keeps_accidental_spelling(self):
        from backend.musicxml_analysis.ingest import refresh_written_octaves,pitch_record
        e={'encoded_pitch':pitch_record(music21.pitch.Pitch('D#6')),'octave_shift_notation':[{'type':'down','size':'8'}]}
        refresh_written_octaves([e]);self.assertEqual(e['written_pitch']['name'],'D#5')
        self.assertEqual(e['written_pitch']['pc'],3)

    def test_musicxml_transposition_ottava_and_hidden_note_are_separate(self):
        from backend.musicxml_analysis.ingest import ingest
        xml='''<score-partwise version="4.0"><part-list><score-part id="P1"><part-name>Horn</part-name></score-part></part-list>
        <part id="P1"><measure number="1"><attributes><divisions>6</divisions><time><beats>3</beats><beat-type>4</beat-type></time>
        <clef><sign>G</sign><line>2</line></clef><transpose><diatonic>-4</diatonic><chromatic>-7</chromatic></transpose></attributes>
        <direction><direction-type><octave-shift type="down" size="8"/></direction-type></direction>
        <note><pitch><step>E</step><octave>5</octave></pitch><duration>6</duration><voice>1</voice><type>quarter</type></note>
        <direction><direction-type><octave-shift type="stop" size="8"/></direction-type></direction>
        <note><pitch><step>D</step><octave>4</octave></pitch><duration>6</duration><voice>1</voice><type>quarter</type><notehead>none</notehead></note>
        <note><rest/><duration>6</duration><voice>1</voice><type>quarter</type></note></measure></part></score-partwise>'''
        folder=ROOT/'tmp/musicxml/tests'/uuid.uuid4().hex
        folder.mkdir(parents=True,exist_ok=True)
        p=folder/'fixture.musicxml';p.write_text(xml,encoding='utf-8');result=ingest(p)
        first,hidden,rest=result['events']
        self.assertEqual(first['encoded_pitch']['name'],'E5')
        self.assertEqual(first['written_pitch']['name'],'E4')
        self.assertEqual(first['concert_pitch']['name'],'A4')
        self.assertTrue(first['analysis_eligible']);self.assertFalse(hidden['analysis_eligible'])
        self.assertEqual(hidden['written_pitch']['name'],'D4');self.assertEqual(rest['kind'],'rest')
        self.assertEqual(result['measures'][0]['duration_q'],'3')


class PrecomputedXML(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from backend.musicxml_analysis.store import load_bundle
        cls.bundle=load_bundle(ROOT,ROOT)
        if cls.bundle is None:raise unittest.SkipTest('Production MusicXML build unavailable')

    def test_full_score_and_all_original_event_records_are_preserved(self):
        b=self.bundle;t=b['tables'];self.assertEqual(len(t['parts']['parts']),37)
        self.assertEqual(len(t['measures']['measures']),535);self.assertEqual(len(t['events']['events']),47907)
        self.assertEqual(len({e['id'] for e in t['events']['events']}),47907)
        self.assertTrue(all(e['music21_stream_audit']=='paired' for e in t['events']['events']))
        self.assertEqual(t['pdf-map']['edition_audit']['layout_difference_count'],0)
        self.assertTrue(all(c['status']=='agrees' for c in t['pdf-map']['edition_audit']['score_window_checks']))

    def test_opening_ghost_notes_do_not_pollute_harmony_or_orchestration(self):
        from backend.musicxml_analysis.store import measure_evidence
        d=measure_evidence(self.bundle,'xml-m0001')
        self.assertTrue(all(w['sonority']['pitch_classes']==[2,4,7,9] for w in d['harmony']))
        self.assertEqual(set(d['orchestration'][0]['active_part_ids']),{'P32','P35','P36'})
        self.assertTrue(any(e['notehead']=='none' for e in d['events']))
        self.assertTrue(all(e['concert_pitch']['name'] in {'D2','G2','E1','A1'} or e['part_id']=='P35' for e in d['events'] if e['analysis_eligible']))

    def test_xml_derived_cadenza_boxes_do_not_copy_old_midi_regions(self):
        pdf=self.bundle['indices']['pdf']
        self.assertEqual(pdf['xml-m0033'][0]['page_number'],10)
        self.assertEqual(pdf['xml-m0034'][0]['page_number'],11)
        self.assertEqual(pdf['xml-m0035'][0]['page_number'],11)
        self.assertEqual(pdf['xml-m0037'][0]['system_index'],2)
        self.assertNotEqual(pdf['xml-m0034'][0]['rect_pt'],pdf['xml-m0035'][0]['rect_pt'])
        self.assertEqual(len(self.bundle['tables']['pdf-map']['note_links']),47907)

    def test_canonical_clocks_preserve_free_meter_instead_of_inventing_3_4(self):
        ms=self.bundle['tables']['measures']['measures']
        self.assertEqual(ms[32]['duration_q'],'17/2');self.assertEqual(ms[33]['duration_q'],'15/2')
        self.assertTrue(all(F(a['start_q'])+F(a['duration_q'])==F(b['start_q']) for a,b in zip(ms,ms[1:])))
        self.assertEqual(self.bundle['tables']['parse-audit']['counts']['music21_duration_difference'],56)
        self.assertGreater(self.bundle['tables']['parse-audit']['counts']['music21_part_clock_difference'],0)

    def test_every_derived_event_reference_is_real_and_function_is_conditional(self):
        ids={e['id'] for e in self.bundle['tables']['events']['events']}
        for w in self.bundle['tables']['harmony']['windows']:
            self.assertTrue(set(w['event_ids'])<=ids)
            self.assertLess(F(w['start_q']),F(w['end_q']))
            self.assertTrue(all(k['status']=='conditional_on_unverified_local_key' for k in w['roman_hypotheses']))
        for r in self.bundle['tables']['counterpoint']['intervals']:
            self.assertTrue(set(r['event_ids'])<=ids)

    def test_musicxml_loader_and_evidence_do_not_require_midi_candidate_engine(self):
        from backend.musicxml_analysis.store import load_bundle,measure_evidence
        with patch('backend.structure_analysis.store.load_bundle',side_effect=AssertionError('No MIDI correspondence allowed')):
            bundle=load_bundle(ROOT,ROOT);self.assertTrue(measure_evidence(bundle,'xml-m0064')['events'])

    def test_original_playback_inputs_unchanged(self):
        for name,expected in self.bundle['manifest']['protected_inputs'].items():
            self.assertEqual(hashlib.sha256((ROOT/name).read_bytes()).hexdigest(),expected,name)

    def test_instrument_changes_preserve_the_actual_note_instrument_reference(self):
        from backend.musicxml_analysis.store import measure_evidence
        a=next(e for e in measure_evidence(self.bundle,'xml-m0126')['events'] if e['part_id']=='P6' and e['analysis_eligible'])
        b=next(e for e in measure_evidence(self.bundle,'xml-m0251')['events'] if e['part_id']=='P6' and e['analysis_eligible'])
        self.assertNotEqual(a['instrument_ref'],b['instrument_ref'])
        self.assertEqual(a['transpose']['semitones'],-2);self.assertEqual(b['transpose']['semitones'],-3)
        self.assertEqual(b['concert_pitch']['name'],'C#4')
        self.assertTrue('beams' in a and 'stem' in a and 'accidental_display' in a)

    def test_independent_musicxml_HTTP_and_artifact_allowlist(self):
        import sys
        sys.path.insert(0,str(ROOT/'scripts'))
        import serve_review
        server=serve_review.ReviewServer(('127.0.0.1',0),serve_review.Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        base=f'http://127.0.0.1:{server.server_port}'
        try:
            with patch('backend.structure_analysis.store.load_bundle',side_effect=AssertionError('No MIDI dependency')):
                with urlopen(base+'/api/musicxml?track=ravel-left-hand') as response:
                    result=json.load(response);self.assertEqual(result['summary']['measures'],535)
                with urlopen(base+'/api/musicxml-evidence?track=ravel-left-hand&measure_id=xml-m0034') as response:
                    self.assertEqual(json.load(response)['pdf'][0]['page_number'],11)
            with self.assertRaises(HTTPError) as error:urlopen(base+'/api/musicxml-artifact?track=ravel-left-hand&name=../../alignment.json')
            self.assertEqual(error.exception.code,404);error.exception.close()
            with urlopen(base+'/api/musicxml?track=lark-ascending') as response:self.assertFalse(json.load(response)['available'])
        finally:server.shutdown();server.server_close();thread.join()


class EvidenceCacheIntegrity(unittest.TestCase):
    def test_cached_evidence_cannot_hide_a_changed_file_or_changed_source(self):
        from backend.structure_analysis.common import write,digest
        from backend.musicxml_analysis.store import load_bundle
        root=ROOT/'tmp/musicxml/tests'/uuid.uuid4().hex;run=root/'analysis/musicxml/run';run.mkdir(parents=True)
        (root/'source.mxl').write_bytes(b'test source, not actual MusicXML')
        (root/'score.pdf').write_bytes(b'test PDF, never displayed')
        write(root/'measure-map.json',{'measures':[]})
        tables={'events':{'events':[]},'parts':{'parts':[]},'measures':{'measures':[]},'notation':{'notation':[]},
            'harmony':{'windows':[],'layer_reductions':[],'key_contexts':[]},'orchestration':{'measures':[]},
            'counterpoint':{'intervals':[],'motions':[],'chordal_intervals':[]},'form':{'landmarks':[],'cadence_candidates':[]},
            'pdf-map':{'measures':[]},'summary':{}}
        for name,value in tables.items():write(run/(name+'.json'),value)
        manifest={'source':{'path':'source.mxl','sha256':digest(root/'source.mxl')},
            'pdf':{'path':'score.pdf','sha256':digest(root/'score.pdf')},'geometry_sha256':digest(root/'measure-map.json'),
            'files':{name+'.json':{'sha256':digest(run/(name+'.json'))} for name in tables}}
        write(run/'manifest.json',manifest)
        write(root/'analysis/musicxml/current.json',{'path':'analysis/musicxml/run','manifest_sha256':digest(run/'manifest.json')})
        self.assertIsNotNone(load_bundle(root,root))
        write(run/'events.json',{'events':['changed']})
        with self.assertRaisesRegex(ValueError,'evidence fingerprint'):load_bundle(root,root)
        write(run/'events.json',tables['events']);(root/'source.mxl').write_bytes(b'changed source')
        with self.assertRaisesRegex(ValueError,'input fingerprint'):load_bundle(root,root)


if __name__=='__main__':unittest.main()
