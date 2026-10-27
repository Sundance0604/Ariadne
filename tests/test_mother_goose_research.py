"""Check musical evidence integrity, source differences and isolation from playback."""
from collections import Counter
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.compare_mother_goose_sources import xml_events


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


class SourceSemantics(unittest.TestCase):
    def test_missing_divisions_does_not_invent_a_score_clock(self):
        xml = '''<score-partwise><part-list><score-part id="P1"><part-name>Test</part-name></score-part></part-list>
        <part id="P1"><measure number="1"><note><pitch><step>C</step><octave>4</octave></pitch>
        <duration>48</duration><type>eighth</type></note></measure></part></score-partwise>'''
        with patch('scripts.compare_mother_goose_sources.xml_root', return_value=(ET.fromstring(xml), xml.encode())), \
             patch('scripts.compare_mother_goose_sources.file_record', return_value={'path':'fixture'}):
            data = xml_events(ROOT / 'tmp/fixture.musicxml')
        self.assertIsNone(data['events'][0]['duration_q'])
        self.assertEqual(data['events'][0]['duration_source_units'], '48')
        self.assertFalse(data['events'][0]['eligible'])
        self.assertEqual(data['anomalies'][0]['kind'], 'missing_divisions')

    def test_chords_backup_and_staff_transposition(self):
        xml = '''<score-partwise><part-list><score-part id="P1"><part-name>Test</part-name></score-part></part-list>
        <part id="P1"><measure number="1"><attributes><divisions>12</divisions>
        <transpose><chromatic>-2</chromatic></transpose>
        <transpose number="2"><chromatic>0</chromatic><octave-change>1</octave-change></transpose></attributes>
        <note><pitch><step>C</step><octave>5</octave></pitch><duration>12</duration><voice>1</voice></note>
        <note><chord/><pitch><step>E</step><octave>5</octave></pitch><duration>12</duration><voice>1</voice></note>
        <backup><duration>12</duration></backup>
        <note><pitch><step>C</step><octave>4</octave></pitch><duration>12</duration><voice>2</voice><staff>2</staff></note>
        </measure></part></score-partwise>'''
        with patch('scripts.compare_mother_goose_sources.xml_root', return_value=(ET.fromstring(xml), xml.encode())), \
             patch('scripts.compare_mother_goose_sources.file_record', return_value={'path':'fixture'}):
            rows = xml_events(ROOT / 'tmp/fixture.musicxml')['events']
        self.assertEqual([e['onset_q'] for e in rows], ['0','0','0'])
        self.assertEqual([e['concert_ps'] for e in rows], ['70','74','72'])
        self.assertEqual([e['voice'] for e in rows], ['1','1','2'])


class MotherGooseEvidence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = ROOT / read(ROOT / 'works/ravel-mother-goose/analysis/current.json')['path']
        cls.manifest = read(cls.base / 'manifest.json')
        cls.events = {e['id']:e for e in read(cls.base / 'events.json')['events']}
        cls.measures = read(cls.base / 'measures.json')['measures']
        cls.guide = read(cls.base / 'sections.json')['sections']

    def test_frozen_files_sources_and_protected_inputs(self):
        pointer = read(ROOT / 'works/ravel-mother-goose/analysis/current.json')
        self.assertEqual(hashlib.sha256((self.base/'manifest.json').read_bytes()).hexdigest(), pointer['manifest_sha256'])
        for rel, meta in self.manifest['files'].items():
            with self.subTest(rel=rel):
                p = self.base / rel
                self.assertEqual(p.stat().st_size, meta['bytes'])
                self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(), meta['sha256'])
        for rel, expected in self.manifest['protected_inputs'].items():
            if rel=='library.json':
                # Later authorized ballet-video and Prokofiev tasks add two
                # independent tracks; the frozen score-only audit stays intact.
                catalog=read(ROOT/rel)
                catalog['tracks']=[t for t in catalog['tracks'] if t['id'] not in {'ravel-mother-goose-video','prokofiev-piano-concerto-2'}]
                self.assertEqual(hashlib.sha256((json.dumps(catalog,ensure_ascii=False,indent=2)+'\n').encode()).hexdigest(),expected)
                continue
            self.assertEqual(hashlib.sha256((ROOT/rel).read_bytes()).hexdigest(), expected)
        for item in self.manifest['inputs']:
            self.assertEqual(hashlib.sha256((ROOT/item['path']).read_bytes()).hexdigest(), item['sha256'])

    def test_continuous_score_clock_and_section_coverage(self):
        for a,b in zip(self.measures,self.measures[1:]):
            self.assertEqual(F(a['start_q'])+F(a['duration_q']), F(b['start_q']))
        coverage = Counter()
        for s in self.guide:
            lo = int(s['first_measure_id'].split('m')[-1]); hi = int(s['last_measure_id'].split('m')[-1])
            coverage.update(range(lo,hi+1))
            self.assertIsNone(s['human_signoff']); self.assertIsNone(s['expert_review'])
            for eid in s['evidence_event_ids']:
                self.assertTrue(lo <= self.events[eid]['measure_sequence'] <= hi)
                self.assertIn(self.events[eid]['part_id'], s['evidence_parts'])
        self.assertEqual(dict(coverage), {i:1 for i in range(1,532)})
        self.assertTrue(all('page' not in m and 'xml_layout_page' in m for m in self.measures))

    def test_vertical_witnesses_are_active_at_the_stated_time(self):
        for w in read(self.base / 'verticals.json')['windows']:
            start,end = F(w['start_q']),F(w['end_q'])
            self.assertLess(start,end)
            for eid in w['event_ids']:
                e = self.events[eid]
                self.assertLessEqual(F(e['score_start_q']), start)
                self.assertGreaterEqual(F(e['score_end_q']), end)
                self.assertIsNone(e['exclusion_reason'])
            self.assertEqual(w['active_part_ids'], sorted({self.events[eid]['part_id'] for eid in w['event_ids']}))

    def test_local_relations_do_not_erase_rhythm_changes(self):
        rows = {c['id']:c for c in read(self.base / 'comparisons.json')['comparisons']}
        for id,offset in [('pavane-return',0),('pavane-inner-line',0),('pavane-doubling',0),
                          ('poucet-octaves',-24),('pagodes-octaves',0),('beast-transposition',2)]:
            self.assertEqual(rows[id]['paired_pitch_offsets_semitones'], [offset])
            self.assertTrue(rows[id]['same_notated_onsets_and_durations'])
        self.assertEqual(rows['beast-prince']['paired_pitch_offsets_semitones'], [60])
        self.assertFalse(rows['beast-prince']['same_notated_onsets_and_durations'])
        studies = read(self.base / 'score-studies.json')['cases']
        self.assertEqual(len(studies),4)
        for case in studies:
            for w in case['windows']:
                chosen,other = set(w['selected_event_ids']),set(w['other_active_event_ids'])
                self.assertFalse(chosen & other)
                at = F(next(m['start_q'] for m in self.measures if m['measure_id']==w['measure_id']))+F(w['offset_q'])
                active = {e['id'] for e in self.events.values() if e['analysis_eligible'] and F(e['score_start_q'])<=at<F(e['score_end_q'])}
                self.assertEqual(chosen | other,active)
        ending = next(c for c in studies if c['id']=='V-first-bar-extension')
        self.assertEqual(ending['windows'][0]['selected_pitches'],['C2','C4','E3'])
        self.assertEqual(ending['windows'][1]['selected_pitches'],['B3','C2','D4','E3'])

    def test_alternate_edition_remains_separate(self):
        audit = read(self.base / 'editorial/alternate-source-audit.json')
        self.assertEqual(len(audit['candidates']),5)
        self.assertEqual(audit['decision'],'retain_original_suite_basis; use_new_as_ballet_comparison')
        self.assertTrue(any(c['differences'] for c in audit['family_comparisons']))
        self.assertIsNone(self.manifest['audio']); self.assertIsNone(self.manifest['recording_projection'])
        self.assertNotIn('ravel-mother-goose',[t['id'] for t in read(ROOT/'library.json')['tracks']])


if __name__ == '__main__':
    unittest.main()
